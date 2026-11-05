"""Tray icon for the v4 shell (``QSystemTrayIcon`` + ``QMenu``, no widget window).  Owner: builder 3.

Left-click: the pill's panel.  Right-click menu, in order: the running activity
(disabled title line), Snapshot now, Add a window, Pause capture, End activity,
Start an activity from what's open, Open an activity >, Show the pill, Search,
Show Project Opener, Quit.  The icon carries a dot in the running activity's colour.
Toasts from ``facade.toast`` show as balloons while the main window is hidden.
"""
from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap

from project_opener import constants as C

log = logging.getLogger(__name__)

MAX_ACTIVITIES = 12


def menu_spec(running: bool, title: str, paused: bool, keys: dict[str, str]) -> list[tuple[str, str, bool, str]]:
    """The menu as (action id, text, enabled, shortcut text); "-" is a separator.  Pure, for the tests."""
    rows: list[tuple[str, str, bool, str]] = [
        ("title", title if running else "No activity running", False, ""),
        ("snapshot", "Snapshot now", running, keys.get("snapshot", "")),
        ("add_window", "Add a window…", running, keys.get("add_window", "")),
        ("pause", "Resume capture" if paused else "Pause capture", running, ""),
        ("end", "End activity…", running, ""),
        ("-", "", True, ""),
        ("start_from_open", "Start an activity from what's open…", True, ""),
        ("open_activity", "Open an activity", True, ""),
        ("-", "", True, ""),
        ("show_pill", "Show the pill", True, keys.get("panel", "")),
        ("search", "Search…", True, keys.get("palette", "")),
        ("show_window", "Show Project Opener", True, ""),
        ("-", "", True, ""),
        ("quit", "Quit", True, ""),
    ]
    return rows


def title_line(label: str, open_count: int, state: str) -> str:
    """"Lot 7 check · 12 open · capture on"."""
    capture = "capture paused" if state == "paused" else "capture on"
    return f"{label} · {open_count} open · {capture}"


def icon_with_dot(base: QIcon, color: str, size: int = 32) -> QIcon:
    """The app icon with a dot in ``color`` at the bottom right ("" -> the plain icon)."""
    if not color:
        return base
    out = QIcon()
    for s in (16, 20, 24, 32, 48):
        pm = base.pixmap(s, s)
        if pm.isNull():
            pm = QPixmap(s, s)
            pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = max(6.0, s * 0.42)
        c = QPointF(s - d / 2 - 0.5, s - d / 2 - 0.5)
        p.setPen(QPen(QColor("#1A1F24"), max(1.0, s / 16)))
        p.setBrush(QColor(color))
        p.drawEllipse(c, d / 2, d / 2)
        p.end()
        out.addPixmap(pm)
    return out


class TrayController(QObject):
    def __init__(self, facade: Any, desktop: Any = None):
        super().__init__(facade)
        self.facade = facade
        self.desktop = desktop          # DesktopApi (togglePanel, startPicker)
        self.icon = None
        self.menu = None
        self._base_icon = QIcon()
        self._dot = ""
        self.main_window = None

    # ------------------------------------------------------------ build
    def create(self) -> None:
        from PySide6.QtWidgets import QMenu, QSystemTrayIcon
        if self.icon is not None:
            return
        base = QIcon()
        for s in (16, 20, 24, 32, 40, 48, 64):
            p = C.resource_path("icon", f"app-{s}.png")
            if p.exists():
                base.addFile(str(p))
        self._base_icon = base
        self.icon = QSystemTrayIcon(base, self)
        self.icon.setToolTip(C.APP_NAME)
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self.rebuild_menu)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        self.icon.messageClicked.connect(self.facade.showWindowRequested.emit)
        self.facade.toast.connect(self._toast)
        cap = getattr(self.facade, "capture", None)
        if cap is not None and hasattr(cap, "stateChanged"):
            cap.stateChanged.connect(self.refresh)
        self.rebuild_menu()
        self.refresh()
        self.icon.show()

    def close(self) -> None:
        if self.icon is not None:
            self.icon.hide()
            self.icon.deleteLater()
            self.icon = None
        if self.menu is not None:
            self.menu.deleteLater()
            self.menu = None

    # ------------------------------------------------------------ state
    def _cap(self, name: str, default: Any) -> Any:
        cap = getattr(self.facade, "capture", None)
        v = cap.property(name) if cap is not None else None
        return default if v is None else v

    def _keys(self) -> dict[str, str]:
        status = {}
        if self.desktop is not None:
            status = self.desktop.property("hotkeyStatus") or {}
        return {k: str(v.get("keys", "")) for k, v in status.items() if isinstance(v, dict) and v.get("ok")}

    def refresh(self) -> None:
        running = bool(self._cap("runningId", ""))
        color = str(self._cap("runningColor", "") or "") if running else ""
        if running and not color:
            color = "#4F7DFF"
        self.set_activity_dot(color)
        if self.icon is not None:
            label = str(self._cap("runningLabel", "") or self._cap("runningName", ""))
            self.icon.setToolTip(f"{C.APP_NAME} · {label}" if running and label else C.APP_NAME)

    def rebuild_menu(self) -> None:
        if self.menu is None:
            return
        from PySide6.QtWidgets import QMenu
        m = self.menu
        m.clear()
        running = bool(self._cap("runningId", ""))
        state = str(self._cap("state", "idle"))
        label = str(self._cap("runningLabel", "") or self._cap("runningName", ""))
        title = title_line(label, int(self._cap("openCount", 0) or 0), state)
        for action_id, text, enabled, keys in menu_spec(running, title, state == "paused", self._keys()):
            if action_id == "-":
                m.addSeparator()
                continue
            if action_id == "open_activity":
                sub = QMenu(text, m)
                self._fill_activities(sub)
                m.addMenu(sub)
                continue
            act = QAction(f"{text}\t{keys}" if keys else text, m)
            act.setEnabled(enabled)
            act.triggered.connect(lambda _=False, a=action_id: self.trigger(a))
            m.addAction(act)

    def _fill_activities(self, sub: Any) -> None:
        try:
            acts = self.facade.ctx.store.sorted_activities()[:MAX_ACTIVITIES]
        except Exception:  # noqa: BLE001
            log.exception("tray: cannot list activities")
            acts = []
        if not acts:
            a = sub.addAction("No activities yet")
            a.setEnabled(False)
        for act in acts:
            name = getattr(act, "name", "") or getattr(act, "id", "")
            a = QAction(name, sub)
            a.triggered.connect(lambda _=False, aid=act.id: self.open_activity(aid))
            sub.addAction(a)

    def set_activity_dot(self, color: str) -> None:
        """"" removes the dot."""
        if color == self._dot and self.icon is not None:
            return
        self._dot = color
        if self.icon is not None:
            self.icon.setIcon(icon_with_dot(self._base_icon, color))

    # ---------------------------------------------------------- actions
    def trigger(self, action: str) -> None:
        f = self.facade
        try:
            if action == "snapshot":
                f.capture.snapshotNow()
            elif action == "add_window":
                if self.desktop is not None:
                    self.desktop.startPicker()
            elif action == "pause":
                if str(self._cap("state", "")) == "paused":
                    f.capture.resume()
                else:
                    f.capture.pause()
            elif action == "end":
                f.capture.endActivity()
            elif action == "start_from_open":
                f.handle_command({"cmd": "start-from-open"})
            elif action == "show_pill":
                if self.desktop is not None:
                    self.desktop.showPanel()
            elif action == "search":
                f.paletteRequested.emit()
            elif action == "show_window":
                f.showWindowRequested.emit()
            elif action == "quit":
                from PySide6.QtWidgets import QApplication
                QApplication.quit()
        except Exception:  # noqa: BLE001
            log.exception("tray: %s failed", action)

    def open_activity(self, activity_id: str) -> None:
        self.facade.ui.go("activity", {"activityId": activity_id})
        self.facade.showWindowRequested.emit()

    def _activated(self, reason: Any) -> None:
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.desktop is not None and self._cap("runningId", ""):
                self.desktop.togglePanel()
            else:
                self.facade.showWindowRequested.emit()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.facade.showWindowRequested.emit()

    def _toast(self, title: str, body: str, level: str) -> None:
        if self.icon is None:
            return
        win = self.main_window
        if win is not None and win.isVisible() and not win.windowState() & Qt.WindowState.WindowMinimized:
            return   # the shell shows its own toast
        from PySide6.QtWidgets import QSystemTrayIcon
        kind = {"error": QSystemTrayIcon.MessageIcon.Critical, "warning": QSystemTrayIcon.MessageIcon.Warning}.get(
            level, QSystemTrayIcon.MessageIcon.Information)
        self.icon.showMessage(title, body, kind, 5000)
