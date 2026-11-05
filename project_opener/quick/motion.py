"""Motion level and render backend (spikes/quick/REPORT.md, "Fallback rule").  Owner: builder 4 (SHELL).

Pure decisions over measured facts; the probing itself (QRhi, adapter name,
SM_REMOTESESSION, SPI_GETCLIENTAREAANIMATION, battery) lives in
``probe_machine`` so the rule is testable without a GPU.

The rule, in short:

1. Backend: software when the GPU probe failed, on the Basic Render Driver, or in a
   remote session; otherwise the GPU (rhi).
2. Level for ``auto``: off in remote desktop; purposeful with software rendering, a
   screen at or below 1366x768, "Show animations" off or on battery; rich otherwise.
   Never above a level the runtime guard reduced it to.
3. Runtime guard: two dock openings in a row over 33 ms mean or 120 ms worst 1 %
   drop one level, saved, said once, never climbing back by itself.
4. Ambient loops only in rich and only while the window is active (QML gates the second).
"""
from __future__ import annotations

import logging
import statistics
import sys
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

LEVELS = ("rich", "purposeful", "off")
SETTINGS = ("auto",) + LEVELS
K = {"rich": 1.0, "purposeful": 0.6, "off": 0.0}     # one number scales every duration in QML
SLOW_MEAN_MS = 33.0
SLOW_WORST1_MS = 120.0
REDUCED_MESSAGE = "Motion was reduced on this PC because frames were being dropped. Change it in Settings."
BASIC_ADAPTERS = ("microsoft basic render driver", "microsoft basic display adapter")


@dataclass
class MachineFacts:
    gpu_ok: bool = True                # QRhi D3D11 created and the adapter is not the Basic Render Driver
    remote_session: bool = False
    screen_w: int = 1920
    screen_h: int = 1080
    animations_off: bool = False       # Windows "Show animations" off
    on_battery: bool = False
    adapter: str = ""


def resolve_backend(setting: str, facts: MachineFacts) -> str:
    """"software" or "rhi".  Software when the GPU probe failed or in a remote session."""
    if setting == "software":
        return "software"
    if setting == "gpu":
        return "rhi"
    return "software" if (not facts.gpu_ok or facts.remote_session) else "rhi"


def auto_level(facts: MachineFacts, backend: str) -> str:
    """The level the machine earns before any runtime reduction."""
    if facts.remote_session:
        return "off"
    if backend == "software" or facts.screen_w <= 1366 or facts.screen_h <= 768 \
            or facts.animations_off or facts.on_battery:
        return "purposeful"
    return "rich"


def resolve_motion(setting: str, reduced_to: str, facts: MachineFacts, backend: str) -> str:
    """The level to run at.  An explicit user choice wins; ``auto`` follows the fallback rule and
    never climbs above a level the runtime guard reduced it to."""
    if setting in LEVELS:
        return setting
    level = auto_level(facts, backend)
    if reduced_to in LEVELS and LEVELS.index(reduced_to) > LEVELS.index(level):
        level = reduced_to
    return level


def next_lower(level: str) -> str:
    i = LEVELS.index(level) if level in LEVELS else 0
    return LEVELS[min(i + 1, len(LEVELS) - 1)]


def dock_frames_too_slow(mean_ms: float, worst1_ms: float) -> bool:
    """One dock opening counts as slow over 33 ms mean or 120 ms worst 1 %; two in a row drop a level."""
    return mean_ms > SLOW_MEAN_MS or worst1_ms > SLOW_WORST1_MS


def frame_stats(stamps: list[float]) -> tuple[float, float]:
    """(mean interval ms, mean of the worst 1 % of intervals ms) from ``perf_counter`` stamps.
    With fewer than 100 intervals the worst 1 % is the single worst frame.  (0, 0) with no interval."""
    gaps = [(b - a) * 1000.0 for a, b in zip(stamps, stamps[1:], strict=False)]
    if not gaps:
        return 0.0, 0.0
    worst = sorted(gaps)[-max(1, len(gaps) // 100):]
    return round(statistics.fmean(gaps), 2), round(statistics.fmean(worst), 2)


@dataclass
class RuntimeGuard:
    """Counts slow dock openings in a row; ``report`` returns the level to drop to, or "" to stay."""
    slow_in_row: int = 0
    history: list[tuple[float, float]] = field(default_factory=list)

    def report(self, level: str, mean_ms: float, worst1_ms: float) -> str:
        self.history.append((mean_ms, worst1_ms))
        if level == "off":                       # nothing animates; the numbers are the launcher's cadence
            self.slow_in_row = 0
            return ""
        if dock_frames_too_slow(mean_ms, worst1_ms):
            self.slow_in_row += 1
        else:
            self.slow_in_row = 0
        if self.slow_in_row >= 2:
            self.slow_in_row = 0
            return next_lower(level)
        return ""


# ------------------------------------------------------------------ probing
def _remote_session() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetSystemMetrics(0x1000))      # SM_REMOTESESSION
    except Exception:  # noqa: BLE001
        return False


def _animations_off() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        val = ctypes.c_int(1)
        ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(val), 0)  # SPI_GETCLIENTAREAANIMATION
        return bool(ok) and not val.value
    except Exception:  # noqa: BLE001
        return False


def _on_battery() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        class SPS(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                        ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                        ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
        s = SPS()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
            return False
        return s.ACLineStatus == 0           # 0 offline (battery), 1 online, 255 unknown
    except Exception:  # noqa: BLE001
        return False


def primary_adapter() -> str:
    """The primary display device's adapter name (EnumDisplayDevicesW); "" when unknown."""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        class DD(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32),
                        ("DeviceString", wintypes.WCHAR * 128), ("StateFlags", wintypes.DWORD),
                        ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]
        i = 0
        first = ""
        while True:
            dd = DD()
            dd.cb = ctypes.sizeof(DD)
            if not ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                break
            if dd.StateFlags & 0x4:              # DISPLAY_DEVICE_PRIMARY_DEVICE
                return dd.DeviceString
            first = first or dd.DeviceString
            i += 1
        return first
    except Exception:  # noqa: BLE001
        return ""


def _rhi_ok() -> bool:
    """Whether a D3D11 QRhi can be created (≈0.5 s; cached per adapter by the caller)."""
    try:
        from PySide6.QtGui import QRhi, QRhiD3D11InitParams
        rhi = QRhi.create(QRhi.Implementation.D3D11, QRhiD3D11InitParams())
        ok = rhi is not None
        del rhi
        return ok
    except Exception as exc:  # noqa: BLE001
        log.info("QRhi probe unavailable (%s); assuming the GPU works", exc)
        return True


def probe_machine(cache: dict[str, str] | None = None, screen: tuple[int, int] | None = None) -> MachineFacts:
    """Measure the facts.  The GPU probe runs once per adapter: ``cache`` (``Settings.gpu_probe``,
    adapter -> "ok" | "failed" | "basic") is read and updated in place.  ``screen`` is the primary
    screen's size in device-independent pixels when the caller knows it."""
    facts = MachineFacts(remote_session=_remote_session(), animations_off=_animations_off(),
                         on_battery=_on_battery())
    if screen:
        facts.screen_w, facts.screen_h = screen
    adapter = primary_adapter()
    facts.adapter = adapter
    if adapter.strip().lower() in BASIC_ADAPTERS:
        verdict = "basic"
    elif cache is not None and adapter in cache:
        verdict = cache[adapter]
    elif sys.platform == "win32":
        verdict = "ok" if _rhi_ok() else "failed"
    else:
        verdict = "ok"
    if cache is not None and adapter:
        cache[adapter] = verdict
    facts.gpu_ok = verdict == "ok"
    return facts
