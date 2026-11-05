"""Wires the pill, hotkeys, picker, tray, quiet-time detection and Explorer entries to the facade.
Owner: builder 3 (DESKTOP).

``app_v4`` calls, once the main QML window exists::

    desktop = DesktopIntegration(facade, engine, main_window)
    facade.set_desktop(desktop.api)
    desktop.start()
    ...
    desktop.shutdown()

Hotkey actions (constants.HOTKEY_IDS): snapshot -> ``app.capture.snapshotNow``;
add_window -> ``app.capture.addForegroundWindow`` (twice within
``ADD_WINDOW_DOUBLE_PRESS_MS`` -> the picker); panel -> toggle the pill's
panel; palette -> ``facade.paletteRequested``.
"""
from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from project_opener.quick.base import ApiBase, ro

log = logging.getLogger(__name__)


class DesktopApi(ApiBase):
    """``app.desktop``: what the shell's Settings > Snapshot page and the pill read."""

    pillChanged = Signal()
    quietChanged = Signal()
    hotkeysChanged = Signal()
    shellEntriesChanged = Signal()
    pickerFinished = Signal(int)              # hwnd chosen, 0 when cancelled

    def __init__(self, app: Any):
        super().__init__(app)
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

    @Slot()
    def togglePanel(self) -> None:
        self.todo("DesktopApi.togglePanel")

    @Slot()
    def showPanel(self) -> None:
        self.todo("DesktopApi.showPanel")

    @Slot()
    def hidePanel(self) -> None:
        self.todo("DesktopApi.hidePanel")

    @Slot()
    def startPicker(self) -> None:
        """Dim the screens, frame the window under the pointer (green/amber), click adds, Esc cancels."""
        self.todo("DesktopApi.startPicker")

    @Slot()
    def cancelPicker(self) -> None:
        self.todo("DesktopApi.cancelPicker")

    @Slot(bool)
    def setPillPinned(self, on: bool) -> None:
        self.todo("DesktopApi.setPillPinned")

    @Slot()
    def applyHotkeys(self) -> None:
        """Re-register from Settings.hotkeys; conflicts land in ``hotkeyStatus`` as Windows reports them."""
        self.todo("DesktopApi.applyHotkeys")

    @Slot(bool)
    def setShellEntries(self, on: bool) -> None:
        """Install/remove the Explorer verb and the Send to shortcut (HKCU, no admin)."""
        self.todo("DesktopApi.setShellEntries")


class DesktopIntegration(QObject):
    def __init__(self, facade: Any, engine: Any, main_window: Any = None):
        super().__init__(facade)
        self.facade = facade
        self.engine = engine
        self.main_window = main_window
        self.api = DesktopApi(facade)
        self.tray = None        # desktop.tray.TrayController
        self.pill = None        # desktop.pill.PillController
        self.hotkeys = None     # desktop.hotkeys.HotkeyManager
        self.picker = None      # desktop.picker.WindowPicker
        self.quiet = None       # desktop.quiet.QuietWatcher

    def start(self) -> None:
        """Create the tray, the pill window, register hotkeys, start the quiet-time watcher.

        Stub: does nothing until builder 3 fills it, so ``--v4`` runs without native side effects.
        """
        log.info("desktop integration: not built yet (stub)")

    def shutdown(self) -> None:
        """Unregister hotkeys, hide the tray icon, save the pill position."""
