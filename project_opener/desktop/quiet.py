"""Quiet time: hide the pill while a full-screen app, a presentation, a remote session or Do not disturb
is in front.  Owner: builder 3 (DESKTOP).

``SHQueryUserNotificationState`` (QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN,
QUNS_PRESENTATION_MODE, QUNS_QUIET_TIME, QUNS_APP) plus "the foreground window covers its
monitor" (and is not the desktop/shell or one of ours), plus ``GetSystemMetrics(SM_REMOTESESSION)``.
Polled on a 1 s QTimer only while the pill would be visible.

``decide`` is the pure rule; the probes read Windows.  ``QuietWatcher`` takes a probe so the
tests drive it with fake inputs.
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal

log = logging.getLogger(__name__)

QUNS_NOT_PRESENT = 1            # screen saver, locked, fast user switching
QUNS_BUSY = 2                   # a full-screen application
QUNS_RUNNING_D3D_FULL_SCREEN = 3
QUNS_PRESENTATION_MODE = 4
QUNS_ACCEPTS_NOTIFICATIONS = 5
QUNS_QUIET_TIME = 6             # Windows' quiet time / do not disturb
QUNS_APP = 7                    # a full-screen Store app
SM_REMOTESESSION = 0x1000

_QUIET_STATES = {
    QUNS_NOT_PRESENT: "screen locked",
    QUNS_BUSY: "full-screen app",
    QUNS_RUNNING_D3D_FULL_SCREEN: "full-screen game or video",
    QUNS_PRESENTATION_MODE: "presentation",
    QUNS_QUIET_TIME: "do not disturb",
    QUNS_APP: "full-screen app",
}
# Shell windows that legitimately cover a monitor: the desktop, its workers, the taskbar.
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


@dataclass(frozen=True)
class QuietFacts:
    notification_state: int = 0      # SHQueryUserNotificationState, 0 = unknown
    foreground_fullscreen: bool = False
    remote_session: bool = False


def decide(facts: QuietFacts) -> tuple[bool, str]:
    """(quiet, reason).  Remote desktop first, then what Windows says, then the geometry check."""
    if facts.remote_session:
        return True, "remote desktop session"
    reason = _QUIET_STATES.get(facts.notification_state)
    if reason:
        return True, reason
    if facts.foreground_fullscreen:
        return True, "full-screen window"
    return False, ""


def covers(window: tuple[int, int, int, int], monitor: tuple[int, int, int, int]) -> bool:
    """True when the window rect (l, t, r, b) covers the whole monitor rect."""
    wl, wt, wr, wb = window
    ml, mt, mr, mb = monitor
    return wl <= ml and wt <= mt and wr >= mr and wb >= mb and (mr - ml) > 0 and (mb - mt) > 0


# ------------------------------------------------------------------ probes
def notification_state() -> int:
    """SHQueryUserNotificationState value (1..7); 0 when unavailable."""
    if sys.platform != "win32":
        return 0
    try:
        state = ctypes.c_int(0)
        hr = ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state))
        return int(state.value) if hr == 0 else 0
    except Exception:  # noqa: BLE001
        return 0


def remote_session() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.user32.GetSystemMetrics(SM_REMOTESESSION))
    except Exception:  # noqa: BLE001
        return False


def foreground_is_fullscreen() -> bool:
    """The foreground window (not the shell, not ours) covers the monitor it is on."""
    if sys.platform != "win32":
        return False
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    if pid.value == os.getpid():
        return False
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(wintypes.HWND(hwnd), buf, 256)
    if buf.value in SHELL_CLASSES:
        return False
    rect = wintypes.RECT()
    if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return False

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    mon = user32.MonitorFromWindow(wintypes.HWND(hwnd), 2)  # MONITOR_DEFAULTTONEAREST
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not mon or not user32.GetMonitorInfoW(mon, ctypes.byref(info)):
        return False
    m = info.rcMonitor
    return covers((rect.left, rect.top, rect.right, rect.bottom), (m.left, m.top, m.right, m.bottom))


def read_facts() -> QuietFacts:
    return QuietFacts(notification_state(), foreground_is_fullscreen(), remote_session())


def is_quiet_time() -> bool:
    return decide(read_facts())[0]


class QuietWatcher(QObject):
    """Polls ``probe`` every ``interval_ms`` while started; emits ``changed(quiet)`` on a change only."""

    changed = Signal(bool)

    def __init__(self, probe: Callable[[], QuietFacts] | None = None, interval_ms: int = 1000,
                 parent: QObject | None = None):
        super().__init__(parent)
        self._probe = probe or read_facts
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.check)
        self.quiet = False
        self.reason = ""

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def check(self) -> bool:
        try:
            quiet, reason = decide(self._probe())
        except Exception:  # noqa: BLE001
            log.exception("quiet-time probe failed")
            quiet, reason = False, ""
        self.reason = reason
        if quiet != self.quiet:
            self.quiet = quiet
            log.debug("quiet time %s (%s)", "on" if quiet else "off", reason)
            self.changed.emit(quiet)
        return quiet

    def start(self) -> None:
        if not self._timer.isActive():
            self.check()
            self._timer.start()

    def stop(self) -> None:
        """Stop polling; quiet time ends (nothing is hidden by it while the pill is off anyway)."""
        self._timer.stop()
        if self.quiet:
            self.quiet = False
            self.reason = ""
            self.changed.emit(False)
