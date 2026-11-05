"""Global hotkeys: RegisterHotKey on a hidden message-only window, read through a native event filter.
Owner: builder 3 (DESKTOP).

Ids are ``constants.HOTKEY_IDS``; key strings ("Ctrl+Alt+S") come from
``Settings.hotkeys``.  A failed registration (another app owns the combo) is
reported per key with Windows' error text, never retried silently.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000


def parse_keys(text: str) -> tuple[int, int]:
    """"Ctrl+Alt+S" -> (modifiers | MOD_NOREPEAT, virtual key).  ValueError when it cannot be a hotkey."""
    raise NotImplementedError("parse_keys")


class HotkeyFilter(QAbstractNativeEventFilter):
    """Installed on the QCoreApplication; turns WM_HOTKEY into ``HotkeyManager.triggered``."""

    def __init__(self, manager: HotkeyManager):
        super().__init__()
        self.manager = manager

    def nativeEventFilter(self, event_type: Any, message: Any) -> tuple[bool, int]:  # noqa: N802
        return False, 0


class HotkeyManager(QObject):
    triggered = Signal(str)                    # "snapshot" | "add_window" | "panel" | "palette"
    statusChanged = Signal("QVariantMap")      # key -> {keys, ok, error}

    def register_all(self, hotkeys: dict[str, str]) -> dict[str, Any]:
        raise NotImplementedError("HotkeyManager.register_all")

    def unregister_all(self) -> None:
        raise NotImplementedError("HotkeyManager.unregister_all")
