"""Quiet time: hide the pill while a full-screen app, a presentation, a remote session or Do not disturb
is in front.  Owner: builder 3 (DESKTOP).

``SHQueryUserNotificationState`` (QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN,
QUNS_PRESENTATION_MODE, QUNS_QUIET_TIME) plus "the foreground window covers its
monitor" (and is not the desktop/shell), plus ``GetSystemMetrics(SM_REMOTESESSION)``.
Polled on a 1 s QTimer only while the pill would be visible.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


def notification_state() -> int:
    """SHQueryUserNotificationState value (1..7); 0 when unavailable."""
    raise NotImplementedError("notification_state")


def foreground_is_fullscreen() -> bool:
    raise NotImplementedError("foreground_is_fullscreen")


def is_quiet_time() -> bool:
    raise NotImplementedError("is_quiet_time")


class QuietWatcher(QObject):
    changed = Signal(bool)

    def start(self) -> None:
        raise NotImplementedError("QuietWatcher.start")

    def stop(self) -> None:
        raise NotImplementedError("QuietWatcher.stop")
