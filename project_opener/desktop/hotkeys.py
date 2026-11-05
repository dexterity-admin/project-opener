"""Global hotkeys: RegisterHotKey on a hidden message-only window, read through a native event filter.
Owner: builder 3 (DESKTOP).

Ids are ``constants.HOTKEY_IDS``; key strings ("Ctrl+Alt+S") come from
``Settings.hotkeys``.  A failed registration (another app owns the combo) is
reported per key with Windows' error text, never retried silently.

The Win32 calls sit behind a small backend (``Win32HotkeyBackend``) so the
parsing, the conflict reporting and the bookkeeping are tested with a fake.
"""
from __future__ import annotations

import ctypes
import logging
import sys
from typing import Any, Protocol

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

from project_opener import constants as C

log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
ERROR_HOTKEY_ALREADY_REGISTERED = 1409
HWND_MESSAGE = -3

_MODIFIERS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL, "ctl": MOD_CONTROL,
    "alt": MOD_ALT, "menu": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN, "windows": MOD_WIN, "meta": MOD_WIN, "super": MOD_WIN,
}
_MOD_ORDER = ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift"), (MOD_WIN, "Win"))

# Named keys -> virtual-key codes (winuser.h).  Letters, digits and F1-F24 are computed.
_NAMED_KEYS: dict[str, int] = {
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "return": 0x0D, "backspace": 0x08,
    "esc": 0x1B, "escape": 0x1B, "pause": 0x13, "insert": 0x2D, "ins": 0x2D, "delete": 0x2E, "del": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pgup": 0x21, "pagedown": 0x22, "pgdn": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "printscreen": 0x2C, "prtsc": 0x2C,
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF, "`": 0xC0,
    "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
    "num0": 0x60, "num1": 0x61, "num2": 0x62, "num3": 0x63, "num4": 0x64,
    "num5": 0x65, "num6": 0x66, "num7": 0x67, "num8": 0x68, "num9": 0x69,
}
_KEY_NAMES = {0x20: "Space", 0x09: "Tab", 0x0D: "Enter", 0x08: "Backspace", 0x1B: "Esc", 0x13: "Pause",
              0x2D: "Insert", 0x2E: "Delete", 0x24: "Home", 0x23: "End", 0x21: "PageUp", 0x22: "PageDown",
              0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down", 0x2C: "PrintScreen",
              0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`",
              0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'"}


def _vk_for(name: str) -> int:
    low = name.lower()
    if len(name) == 1 and name.isalnum() and name.isascii():
        return ord(name.upper())
    if low.startswith("f") and low[1:].isdigit() and 1 <= int(low[1:]) <= 24:
        return 0x70 + int(low[1:]) - 1
    if low in _NAMED_KEYS:
        return _NAMED_KEYS[low]
    raise ValueError(f'"{name}" is not a key Windows can use for a shortcut')


def parse_keys(text: str) -> tuple[int, int]:
    """"Ctrl+Alt+S" -> (modifiers | MOD_NOREPEAT, virtual key).  ValueError when it cannot be a hotkey.

    Rules: exactly one non-modifier key; at least one of Ctrl, Alt or Win (Shift alone would take a
    typed character away from every program), except F13-F24, which nobody types.
    """
    raw = (text or "").strip()
    if not raw:
        raise ValueError("No keys given")
    # "Ctrl++" means Ctrl and the plus key; split on "+" but keep a trailing "+" as a key.
    parts = [p.strip() for p in raw.split("+")]
    if raw.endswith("++"):
        parts = parts[:-2] + ["="]  # the "+" key is VK_OEM_PLUS, labelled "="
    parts = [p for p in parts if p]
    mods = 0
    keys: list[str] = []
    for p in parts:
        m = _MODIFIERS.get(p.lower())
        if m is not None:
            if mods & m:
                raise ValueError(f'"{p}" is given twice')
            mods |= m
        else:
            keys.append(p)
    if not keys:
        raise ValueError("A shortcut needs a key besides Ctrl, Alt, Shift or Win")
    if len(keys) > 1:
        raise ValueError(f"A shortcut takes one key, not {len(keys)} ({' and '.join(keys)})")
    vk = _vk_for(keys[0])
    if not mods & (MOD_CONTROL | MOD_ALT | MOD_WIN) and not 0x7C <= vk <= 0x87:
        raise ValueError("A shortcut needs Ctrl, Alt or Win (Shift alone would take a key from every program)")
    return mods | MOD_NOREPEAT, vk


def format_keys(mods: int, vk: int) -> str:
    """The canonical spelling of a parsed shortcut ("Ctrl+Alt+S")."""
    names = [n for m, n in _MOD_ORDER if mods & m]
    if 0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39:
        key = chr(vk)
    elif 0x70 <= vk <= 0x87:
        key = f"F{vk - 0x70 + 1}"
    elif 0x60 <= vk <= 0x69:
        key = f"Num{vk - 0x60}"
    else:
        key = _KEY_NAMES.get(vk, f"0x{vk:02X}")
    return "+".join([*names, key])


# ----------------------------------------------------------------- backend
class HotkeyBackend(Protocol):
    def register(self, hotkey_id: int, mods: int, vk: int) -> tuple[bool, str]: ...
    def unregister(self, hotkey_id: int) -> None: ...
    def close(self) -> None: ...


def windows_error_text(code: int) -> str:
    """Windows' own wording for an error code ("Hot key is already registered.")."""
    try:
        text = ctypes.FormatError(code).strip()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        text = ""
    return text or f"Windows error {code}"


class Win32HotkeyBackend:
    """RegisterHotKey against a hidden message-only window ("STATIC" class, parent HWND_MESSAGE).

    WM_HOTKEY is posted to that window's queue; Qt's event dispatcher hands every queued message to
    the native event filters before dispatching it, which is where ``HotkeyFilter`` reads it.
    """

    def __init__(self) -> None:
        from ctypes import wintypes
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        u = self._user32
        u.CreateWindowExW.restype = wintypes.HWND
        u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                      wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        u.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        u.RegisterHotKey.restype = wintypes.BOOL
        u.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        u.UnregisterHotKey.restype = wintypes.BOOL
        u.DestroyWindow.argtypes = [wintypes.HWND]
        self.hwnd = u.CreateWindowExW(0, "STATIC", "ProjectOpener.Hotkeys", 0, 0, 0, 0, 0,
                                      wintypes.HWND(HWND_MESSAGE), None, None, None) or 0
        if not self.hwnd:
            log.warning("hotkeys: cannot create the message window (%s)",
                        windows_error_text(ctypes.get_last_error()))

    def register(self, hotkey_id: int, mods: int, vk: int) -> tuple[bool, str]:
        if not self.hwnd:
            return False, "The hotkey window could not be created"
        if self._user32.RegisterHotKey(self.hwnd, hotkey_id, mods, vk):
            return True, ""
        code = ctypes.get_last_error()
        return False, windows_error_text(code)

    def unregister(self, hotkey_id: int) -> None:
        if self.hwnd:
            self._user32.UnregisterHotKey(self.hwnd, hotkey_id)

    def close(self) -> None:
        if self.hwnd:
            self._user32.DestroyWindow(self.hwnd)
            self.hwnd = 0


class HotkeyFilter(QAbstractNativeEventFilter):
    """Installed on the QCoreApplication; turns WM_HOTKEY into ``HotkeyManager.triggered``."""

    def __init__(self, manager: HotkeyManager):
        super().__init__()
        self.manager = manager

    def nativeEventFilter(self, event_type: Any, message: Any) -> tuple[bool, int]:  # noqa: N802
        if bytes(event_type) != b"windows_generic_MSG":
            return False, 0
        try:
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
        except Exception:  # noqa: BLE001
            return False, 0
        if msg.message != WM_HOTKEY:
            return False, 0
        hwnd = int(msg.hWnd or 0)
        if hwnd != self.manager.window_handle():
            return False, 0
        return (True, 0) if self.manager.handle_hotkey(int(msg.wParam)) else (False, 0)


class HotkeyManager(QObject):
    triggered = Signal(str)                    # "snapshot" | "add_window" | "panel" | "palette"
    statusChanged = Signal("QVariantMap")      # key -> {keys, ok, error}

    def __init__(self, backend: HotkeyBackend | None = None, parent: QObject | None = None,
                 install_filter: bool = True):
        super().__init__(parent)
        self._backend = backend
        self._registered: dict[int, str] = {}   # id -> name
        self._status: dict[str, Any] = {}
        self._filter: HotkeyFilter | None = None
        self._install_filter = install_filter

    # -------------------------------------------------------------- plumbing
    def _ensure_backend(self) -> HotkeyBackend:
        if self._backend is None:
            if sys.platform != "win32":
                raise RuntimeError("global hotkeys need Windows")
            self._backend = Win32HotkeyBackend()
        if self._install_filter and self._filter is None and QCoreApplication.instance() is not None:
            self._filter = HotkeyFilter(self)
            QCoreApplication.instance().installNativeEventFilter(self._filter)
        return self._backend

    def window_handle(self) -> int:
        return int(getattr(self._backend, "hwnd", 0) or 0)

    @property
    def status(self) -> dict[str, Any]:
        return dict(self._status)

    @property
    def registered(self) -> dict[int, str]:
        return dict(self._registered)

    def handle_hotkey(self, hotkey_id: int) -> bool:
        name = self._registered.get(hotkey_id)
        if not name:
            return False
        self.triggered.emit(name)
        return True

    # ------------------------------------------------------------------ API
    def register_all(self, hotkeys: dict[str, str], enabled: bool = True) -> dict[str, Any]:
        """Unregister everything, then register each known key.  Returns (and emits) the status map.

        Status per name: ``{"keys": canonical or as typed, "ok": bool, "error": text}``; "" error when
        ok.  Two names on the same combination: the second is refused without asking Windows.
        """
        self.unregister_all()
        status: dict[str, Any] = {}
        if not enabled:
            for name in C.HOTKEY_IDS:
                status[name] = {"keys": str(hotkeys.get(name, "")), "ok": False, "error": "Turned off"}
            self._status = status
            self.statusChanged.emit(dict(status))
            return dict(status)
        backend = self._ensure_backend()
        taken: dict[tuple[int, int], str] = {}
        for name, hotkey_id in C.HOTKEY_IDS.items():
            text = str(hotkeys.get(name, C.HOTKEY_DEFAULTS.get(name, "")) or "").strip()
            if not text:
                status[name] = {"keys": "", "ok": False, "error": "No shortcut set"}
                continue
            try:
                mods, vk = parse_keys(text)
            except ValueError as exc:
                status[name] = {"keys": text, "ok": False, "error": str(exc)}
                continue
            keys = format_keys(mods, vk)
            combo = (mods & ~MOD_NOREPEAT, vk)
            if combo in taken:
                status[name] = {"keys": keys, "ok": False, "error": f"Already used here for {taken[combo]}"}
                continue
            ok, error = backend.register(hotkey_id, mods, vk)
            if ok:
                self._registered[hotkey_id] = name
                taken[combo] = name.replace("_", " ")
            else:
                log.info("hotkey %s (%s) refused: %s", name, keys, error)
            status[name] = {"keys": keys, "ok": ok, "error": error}
        self._status = status
        self.statusChanged.emit(dict(status))
        return dict(status)

    def unregister_all(self) -> None:
        if self._backend is not None:
            for hotkey_id in list(self._registered):
                self._backend.unregister(hotkey_id)
        self._registered.clear()

    def close(self) -> None:
        """Unregister every key, destroy the message window, remove the filter (on exit)."""
        self.unregister_all()
        if self._filter is not None and QCoreApplication.instance() is not None:
            QCoreApplication.instance().removeNativeEventFilter(self._filter)
            self._filter = None
        if self._backend is not None:
            self._backend.close()
