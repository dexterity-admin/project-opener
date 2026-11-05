"""Motion level and render backend (spikes/quick/REPORT.md, "Fallback rule").  Owner: builder 4 (SHELL).

Pure decisions over measured facts; the probing itself (QRhi, adapter name,
SM_REMOTESESSION, SPI_GETCLIENTAREAANIMATION, battery) lives in
``probe_machine`` so the rule is testable without a GPU.
"""
from __future__ import annotations

from dataclasses import dataclass

LEVELS = ("rich", "purposeful", "off")
K = {"rich": 1.0, "purposeful": 0.6, "off": 0.0}     # one number scales every duration in QML


@dataclass
class MachineFacts:
    gpu_ok: bool = True                # QRhi D3D11 created and the adapter is not the Basic Render Driver
    remote_session: bool = False
    screen_w: int = 1920
    screen_h: int = 1080
    animations_off: bool = False       # Windows "Show animations" off
    on_battery: bool = False


def resolve_backend(setting: str, facts: MachineFacts) -> str:
    """"software" or "rhi".  Software when the GPU probe failed or in a remote session."""
    if setting == "software":
        return "software"
    if setting == "gpu":
        return "rhi"
    return "software" if (not facts.gpu_ok or facts.remote_session) else "rhi"


def resolve_motion(setting: str, reduced_to: str, facts: MachineFacts, backend: str) -> str:
    """The level to run at.  An explicit user choice wins; ``auto`` follows the fallback rule and
    never climbs above a level the runtime guard reduced it to."""
    if setting in LEVELS:
        return setting
    if facts.remote_session:
        level = "off"
    elif backend == "software" or facts.screen_w <= 1366 or facts.screen_h <= 768 \
            or facts.animations_off or facts.on_battery:
        level = "purposeful"
    else:
        level = "rich"
    if reduced_to in LEVELS and LEVELS.index(reduced_to) > LEVELS.index(level):
        level = reduced_to
    return level


def next_lower(level: str) -> str:
    i = LEVELS.index(level) if level in LEVELS else 0
    return LEVELS[min(i + 1, len(LEVELS) - 1)]


def dock_frames_too_slow(mean_ms: float, worst1_ms: float) -> bool:
    """One dock opening counts as slow over 33 ms mean or 120 ms worst 1 %; two in a row drop a level."""
    return mean_ms > 33.0 or worst1_ms > 120.0


def probe_machine() -> MachineFacts:
    """Measure the facts once per adapter (cached in ``Settings.gpu_probe``).  Builder 4 implements."""
    raise NotImplementedError("probe_machine")
