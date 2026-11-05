"""Hotkey parsing and conflict reporting (builder 3), against a fake RegisterHotKey backend."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from project_opener import constants as C
from project_opener.desktop import hotkeys as H


@pytest.mark.parametrize(("text", "mods", "vk"), [
    ("Ctrl+Alt+S", H.MOD_CONTROL | H.MOD_ALT, ord("S")),
    ("ctrl + alt + a", H.MOD_CONTROL | H.MOD_ALT, ord("A")),
    ("Control+Shift+F5", H.MOD_CONTROL | H.MOD_SHIFT, 0x74),
    ("Win+Alt+1", H.MOD_WIN | H.MOD_ALT, ord("1")),
    ("Alt+Space", H.MOD_ALT, 0x20),
    ("Ctrl+Alt+PageDown", H.MOD_CONTROL | H.MOD_ALT, 0x22),
    ("Ctrl+Alt+/", H.MOD_CONTROL | H.MOD_ALT, 0xBF),
    ("F13", 0, 0x7C),
])
def test_parse_keys(text, mods, vk):
    assert H.parse_keys(text) == (mods | H.MOD_NOREPEAT, vk)


@pytest.mark.parametrize("text", ["", "Ctrl+Alt", "Ctrl+Alt+S+D", "S", "Shift+S", "Ctrl+Ctrl+S",
                                  "Ctrl+Alt+Banana", "Ctrl+F25"])
def test_parse_keys_refuses(text):
    with pytest.raises(ValueError):
        H.parse_keys(text)


def test_format_round_trip():
    for text in ("Ctrl+Alt+S", "Ctrl+Shift+F5", "Alt+Win+Space", "Ctrl+Alt+PageDown"):
        mods, vk = H.parse_keys(text)
        again = H.format_keys(mods, vk)
        assert H.parse_keys(again) == (mods, vk)
    assert H.format_keys(*H.parse_keys("alt+ctrl+s")) == "Ctrl+Alt+S"


class FakeBackend:
    """RegisterHotKey as Windows behaves: a combination owned elsewhere fails with error 1409."""

    def __init__(self, owned_elsewhere=()):
        parsed = [H.parse_keys(k) for k in owned_elsewhere]
        self.owned = {(mods & ~H.MOD_NOREPEAT, vk) for mods, vk in parsed}
        self.live: dict[int, tuple[int, int]] = {}
        self.hwnd = 0x1234
        self.closed = False

    def register(self, hotkey_id, mods, vk):
        assert mods & H.MOD_NOREPEAT
        if (mods & ~H.MOD_NOREPEAT, vk) in self.owned:
            return False, "Hot key is already registered."
        assert hotkey_id not in self.live
        self.live[hotkey_id] = (mods, vk)
        return True, ""

    def unregister(self, hotkey_id):
        self.live.pop(hotkey_id, None)

    def close(self):
        self.closed = True


def test_register_all_defaults_and_conflict():
    backend = FakeBackend(owned_elsewhere=["Ctrl+Alt+K"])
    mgr = H.HotkeyManager(backend, install_filter=False)
    seen = []
    mgr.statusChanged.connect(seen.append)
    status = mgr.register_all(dict(C.HOTKEY_DEFAULTS))
    assert status["snapshot"] == {"keys": "Ctrl+Alt+S", "ok": True, "error": ""}
    assert status["palette"]["ok"] is False
    assert status["palette"]["error"] == "Hot key is already registered."
    assert set(backend.live) == {C.HOTKEY_SNAPSHOT, C.HOTKEY_ADD_WINDOW, C.HOTKEY_PANEL}
    assert seen and seen[-1] == status


def test_register_all_reports_bad_and_duplicate_keys():
    backend = FakeBackend()
    mgr = H.HotkeyManager(backend, install_filter=False)
    status = mgr.register_all({"snapshot": "Ctrl+Alt+S", "add_window": "ctrl+alt+s", "panel": "P",
                               "palette": ""})
    assert status["snapshot"]["ok"] is True
    assert status["add_window"] == {"keys": "Ctrl+Alt+S", "ok": False, "error": "Already used here for snapshot"}
    assert status["panel"]["ok"] is False and "Ctrl, Alt or Win" in status["panel"]["error"]
    # a missing entry falls back to the default; an empty one is "No shortcut set"
    assert status["palette"] == {"keys": "", "ok": False, "error": "No shortcut set"}
    assert list(backend.live) == [C.HOTKEY_SNAPSHOT]


def test_reregister_and_unregister_leave_nothing_behind():
    backend = FakeBackend()
    mgr = H.HotkeyManager(backend, install_filter=False)
    mgr.register_all(dict(C.HOTKEY_DEFAULTS))
    mgr.register_all({**C.HOTKEY_DEFAULTS, "snapshot": "Ctrl+Shift+F9"})
    assert backend.live[C.HOTKEY_SNAPSHOT][1] == 0x78
    assert len(backend.live) == 4
    status = mgr.register_all(dict(C.HOTKEY_DEFAULTS), enabled=False)
    assert backend.live == {} and all(not s["ok"] for s in status.values())
    mgr.register_all(dict(C.HOTKEY_DEFAULTS))
    mgr.close()
    assert backend.live == {} and backend.closed


def test_triggered_by_id():
    backend = FakeBackend()
    mgr = H.HotkeyManager(backend, install_filter=False)
    mgr.register_all(dict(C.HOTKEY_DEFAULTS))
    got = []
    mgr.triggered.connect(got.append)
    assert mgr.handle_hotkey(C.HOTKEY_PANEL) is True
    assert mgr.handle_hotkey(0x9999) is False
    assert got == ["panel"]
    assert mgr.window_handle() == 0x1234


def test_windows_error_text():
    assert "already registered" in H.windows_error_text(H.ERROR_HOTKEY_ALREADY_REGISTERED).lower()
