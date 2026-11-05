"""Wires the pill, hotkeys, picker, tray, quiet-time detection and Explorer entries to the facade.
Owner: builder 3 (DESKTOP).

``app_v4`` calls, once the main QML window exists::

    desktop = DesktopIntegration(facade, engine, main_window)
    facade.set_desktop(desktop.api)
    desktop.start()
    ...
    desktop.shutdown()

Hotkey actions (constants.HOTKEY_IDS): snapshot -> ``app.capture.snapshotNow``;
add_window -> the window in front is added (``app.capture.addWindow``) unless the key is pressed
again within ``ADD_WINDOW_DOUBLE_PRESS_MS``, which opens the picker instead; panel -> toggle the
pill's panel; palette -> ``facade.paletteRequested``.

``PO_DESKTOP=off`` in the environment skips every native piece (tray, pill, hotkeys); the
smoke tests and offscreen renders use it.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from project_opener import constants as C
from project_opener.quick.base import ApiBase, ro

log = logging.getLogger(__name__)


class DoublePress:
    """Ctrl+Alt+A: the first press waits ``window_ms`` for a second one.

    ``press(now_ms)`` returns "picker" on the second press inside the window (the pending single
    action is dropped), else "wait"; ``due(now_ms)`` returns True once when the pending single press
    has outlived the window and should run.
    """

    def __init__(self, window_ms: int = C.ADD_WINDOW_DOUBLE_PRESS_MS):
        self.window_ms = window_ms
        self._pending_at: float | None = None

    @property
    def pending(self) -> bool:
        return self._pending_at is not None

    def press(self, now_ms: float) -> str:
        if self._pending_at is not None and now_ms - self._pending_at <= self.window_ms:
            self._pending_at = None
            return "picker"
        self._pending_at = now_ms
        return "wait"

    def due(self, now_ms: float) -> bool:
        if self._pending_at is not None and now_ms - self._pending_at >= self.window_ms:
            self._pending_at = None
            return True
        return False

    def reset(self) -> None:
        self._pending_at = None


def foreground_window() -> int:
    if sys.platform != "win32":
        return 0
    import ctypes
    from ctypes import wintypes
    ctypes.windll.user32.GetForegroundWindow.restype = wintypes.HWND
    return int(ctypes.windll.user32.GetForegroundWindow() or 0)


class DesktopApi(ApiBase):
    """``app.desktop``: what the shell's Settings > Snapshot page and the pill read."""

    pillChanged = Signal()
    quietChanged = Signal()
    hotkeysChanged = Signal()
    shellEntriesChanged = Signal()
    pickerFinished = Signal(int)              # hwnd chosen, 0 when cancelled

    def __init__(self, app: Any, integration: DesktopIntegration | None = None):
        super().__init__(app)
        self._integration = integration
        self._pill_visible = False
        self._panel_open = False
        self._quiet = False
        self._hotkey_status: dict[str, Any] = {}   # key -> {keys, ok, error}
        self._explorer_verb = False
        self._sendto = False

    pillVisible = ro(bool, "_pill_visible", pillChanged)
    panelOpen = ro(bool, "_panel_open", pillChanged)
    quiet = ro(bool, "_quiet", quietChanged)                     # full screen / presentation / RDP / DND
    hotkeyStatus = ro("QVariantMap", "_hotkey_status", hotkeysChanged)
    explorerVerbInstalled = ro(bool, "_explorer_verb", shellEntriesChanged)
    sendToInstalled = ro(bool, "_sendto", shellEntriesChanged)

    def _pill(self) -> Any:
        return self._integration.pill if self._integration else None

    @Slot()
    def togglePanel(self) -> None:
        pill = self._pill()
        if pill is not None:
            pill.togglePanel()

    @Slot()
    def showPanel(self) -> None:
        pill = self._pill()
        if pill is not None:
            pill.openPanel()

    @Slot()
    def hidePanel(self) -> None:
        pill = self._pill()
        if pill is not None:
            pill.closePanel()

    @Slot()
    def startPicker(self) -> None:
        """Dim the screens, frame the window under the pointer (green/amber), click adds, Esc cancels."""
        if self._integration and self._integration.picker is not None:
            self.hidePanel()
            self._integration.picker.start()

    @Slot()
    def cancelPicker(self) -> None:
        if self._integration and self._integration.picker is not None:
            self._integration.picker.cancel()

    @Slot(bool)
    def setPillPinned(self, on: bool) -> None:
        s = self.app.ctx.settings
        s.pill_pinned = bool(on)
        s.save()
        self.applyPill()

    @Slot()
    def applyPill(self) -> None:  # noqa: N802
        """Settings > Snapshot changed pill_enabled / pill_rest_style / pill_pinned / position."""
        if self._integration:
            self._integration.pill_settings_changed()

    @Slot()
    def applyHotkeys(self) -> None:
        """Re-register from Settings.hotkeys; conflicts land in ``hotkeyStatus`` as Windows reports them."""
        if self._integration:
            self._integration.apply_hotkeys()

    @Slot(bool)
    def setShellEntries(self, on: bool) -> None:
        """Install/remove the Explorer verb and the Send to shortcut (HKCU, no admin)."""
        if self._integration:
            self._integration.set_shell_entries(on, on)

    # ------------------------------------------------- integration setters
    def _set_pill(self, visible: bool, panel_open: bool) -> None:
        if (visible, panel_open) != (self._pill_visible, self._panel_open):
            self._pill_visible, self._panel_open = visible, panel_open
            self.pillChanged.emit()

    def _set_quiet(self, quiet: bool) -> None:
        self.set_("_quiet", bool(quiet), self.quietChanged)

    def _set_hotkeys(self, status: dict[str, Any]) -> None:
        self._hotkey_status = dict(status)
        self.hotkeysChanged.emit()

    def _set_shell(self, verb: bool, sendto: bool) -> None:
        if (verb, sendto) != (self._explorer_verb, self._sendto):
            self._explorer_verb, self._sendto = verb, sendto
            self.shellEntriesChanged.emit()


class DesktopIntegration(QObject):
    def __init__(self, facade: Any, engine: Any, main_window: Any = None, qml_dir: Path | None = None,
                 clock: Callable[[], float] | None = None):
        super().__init__(facade)
        self.facade = facade
        self.engine = engine
        self.main_window = main_window
        self.qml_dir = qml_dir or Path(__file__).resolve().parents[1] / "qml"
        if C.is_frozen():
            self.qml_dir = C.bundle_dir() / "qml"
        self.api = DesktopApi(facade, self)
        self.tray = None        # desktop.tray.TrayController
        self.pill = None        # desktop.pill.PillController
        self.hotkeys = None     # desktop.hotkeys.HotkeyManager
        self.picker = None      # desktop.picker.WindowPicker
        self.quiet = None       # desktop.quiet.QuietWatcher
        self._clock = clock or (lambda: time.monotonic() * 1000)
        self._double = DoublePress()
        self._pending_hwnd = 0
        self._double_timer = QTimer(self, singleShot=True, interval=C.ADD_WINDOW_DOUBLE_PRESS_MS)
        self._double_timer.timeout.connect(self._add_window_due)
        self._started = False

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        """Create the tray, the pill window, register hotkeys, start the quiet-time watcher."""
        if self._started:
            return
        self._started = True
        self.refresh_shell_state()
        if os.environ.get("PO_DESKTOP", "").lower() == "off" or sys.platform != "win32":
            log.info("desktop integration: native pieces off (PO_DESKTOP=off or not Windows)")
            return
        from project_opener.desktop.hotkeys import HotkeyManager
        from project_opener.desktop.picker import WindowPicker
        from project_opener.desktop.pill import PillController
        from project_opener.desktop.quiet import QuietWatcher
        from project_opener.desktop.tray import TrayController

        self.tray = TrayController(self.facade, self.api)
        self.tray.main_window = self.main_window
        try:
            self.tray.create()
        except Exception:  # noqa: BLE001
            log.exception("tray failed")

        self.picker = WindowPicker(self.facade, self.engine, self.qml_dir)
        self.picker.finished.connect(self.api.pickerFinished.emit)

        self.pill = PillController(self.facade, self.engine, self.qml_dir)
        self.pill.panelChanged.connect(self._sync_pill)
        self.pill.visibilityChanged.connect(lambda _v: self._sync_pill())
        self.pill.viewChanged.connect(self._update_quiet_watch)
        try:
            self.pill.create()
        except Exception:  # noqa: BLE001
            log.exception("pill failed")

        self.quiet = QuietWatcher(parent=self, background=True)
        self.quiet.changed.connect(self._on_quiet)
        self._update_quiet_watch()

        self.hotkeys = HotkeyManager(parent=self)
        self.hotkeys.triggered.connect(self.on_hotkey)
        self.hotkeys.statusChanged.connect(self.api._set_hotkeys)
        self.apply_hotkeys()

        from PySide6.QtGui import QGuiApplication
        app = QGuiApplication.instance()
        if app is not None:
            for sig in (app.screenAdded, app.screenRemoved):
                sig.connect(lambda *_: QTimer.singleShot(500, self._screens_changed))
            app.aboutToQuit.connect(self.shutdown)
        self._sync_pill()

    def shutdown(self) -> None:
        """Unregister hotkeys, hide the tray icon, save the pill position."""
        if not self._started:
            return
        self._started = False
        self._double_timer.stop()
        for name, fn in (("hotkeys", lambda: self.hotkeys and self.hotkeys.close()),
                         ("picker", lambda: self.picker and self.picker.close()),
                         ("quiet", lambda: self.quiet and self.quiet.stop()),
                         ("pill", lambda: self.pill and self.pill.destroy()),
                         ("tray", lambda: self.tray and self.tray.close())):
            try:
                fn()
            except Exception:  # noqa: BLE001
                log.exception("desktop shutdown: %s", name)

    # -------------------------------------------------------------- hotkeys
    def apply_hotkeys(self) -> None:
        if self.hotkeys is None:
            return
        s = self.facade.ctx.settings
        self.hotkeys.register_all(dict(getattr(s, "hotkeys", {}) or {}), bool(getattr(s, "hotkeys_enabled", True)))
        if self.tray is not None:
            self.tray.rebuild_menu()

    @Slot(str)
    def on_hotkey(self, name: str) -> None:
        f = self.facade
        try:
            if name == "snapshot":
                f.capture.snapshotNow()
            elif name == "add_window":
                self.add_window_pressed()
            elif name == "panel":
                self.api.togglePanel()
            elif name == "palette":
                f.paletteRequested.emit()
        except Exception:  # noqa: BLE001 - a hotkey must never take the event filter down
            log.exception("hotkey %s failed", name)

    def add_window_pressed(self) -> None:
        verdict = self._double.press(self._clock())
        if verdict == "picker":
            self._double_timer.stop()
            self._pending_hwnd = 0
            self.api.startPicker()
            return
        self._pending_hwnd = foreground_window()   # the window in front now, before anything moves
        self._double_timer.start()

    def _add_window_due(self) -> None:
        if not self._double.pending:        # a second press already turned it into the picker
            return
        self._double.reset()                # the timer is the clock here (coarse timers may fire early)
        hwnd, self._pending_hwnd = self._pending_hwnd, 0
        try:
            if hwnd:
                self.facade.capture.addWindow(hwnd)
            else:
                self.facade.capture.addForegroundWindow()
        except Exception:  # noqa: BLE001
            log.exception("add window failed")

    # ----------------------------------------------------------- pill/quiet
    def pill_settings_changed(self) -> None:
        if self.pill is not None:
            self.pill.screens_changed()
            self.pill.refresh()

    def _screens_changed(self) -> None:
        if self.pill is not None:
            self.pill.screens_changed()

    def _sync_pill(self) -> None:
        if self.pill is None:
            return
        self.api._set_pill(self.pill.visible, bool(self.pill.property("panelOpen")))

    def _update_quiet_watch(self) -> None:
        """Poll quiet time only while the pill would be on screen."""
        if self.quiet is None or self.pill is None:
            return
        if self.pill.would_show():
            self.quiet.start()
        elif self.quiet.running:
            self.quiet.stop()

    def _on_quiet(self, quiet: bool) -> None:
        self.api._set_quiet(quiet)
        if self.pill is not None:
            self.pill.set_quiet(quiet)

    # -------------------------------------------------------- shell entries
    def refresh_shell_state(self) -> None:
        if sys.platform != "win32":
            return
        from project_opener.desktop import shellext
        try:
            self.api._set_shell(shellext.explorer_verb_installed(), shellext.sendto_installed())
        except Exception:  # noqa: BLE001
            log.exception("cannot read the Explorer entries")

    def set_shell_entries(self, verb: bool, sendto: bool, **kw: Any) -> tuple[bool, bool]:
        """Settings > Snapshot: write or remove both entries for this user; remembered in Settings."""
        from project_opener.desktop import shellext
        s = self.facade.ctx.settings
        s.explorer_verb, s.sendto_entry = bool(verb), bool(sendto)
        try:
            s.save()
        except Exception:  # noqa: BLE001
            log.exception("could not save the Explorer settings")
        state = shellext.set_entries(verb, sendto, **kw)
        self.api._set_shell(*state)
        return state
