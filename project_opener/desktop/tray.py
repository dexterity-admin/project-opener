"""Tray icon for the v4 shell (``QSystemTrayIcon`` + ``QMenu``, no widget window).  Owner: builder 3.

Left-click: the pill's panel.  Right-click menu, in order: the running activity
(disabled title line), Snapshot now, Add a window, Pause capture, End activity,
Start an activity from what's open, Open an activity >, Show the pill, Search,
Show Project Opener, Quit.  The icon carries a dot in the running activity's colour.
Toasts from ``facade.toast`` show as balloons while the main window is hidden.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject


class TrayController(QObject):
    def __init__(self, facade: Any):
        super().__init__(facade)
        self.facade = facade
        self.icon = None

    def create(self) -> None:
        raise NotImplementedError("TrayController.create")

    def rebuild_menu(self) -> None:
        raise NotImplementedError("TrayController.rebuild_menu")

    def set_activity_dot(self, color: str) -> None:
        """"" removes the dot."""
        raise NotImplementedError("TrayController.set_activity_dot")
