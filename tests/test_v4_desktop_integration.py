"""Desktop wiring (builder 3): hotkey routing, the Ctrl+Alt+A double press, the tray menu, app.desktop.

No native pieces: ``DesktopIntegration.start`` is not called; hotkeys use a fake backend and the
Explorer entries a fake registry.
"""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from test_v4_desktop_fakes import FakeFacade

from project_opener import constants as C
from project_opener.desktop import shellext
from project_opener.desktop.integration import DesktopIntegration, DoublePress
from project_opener.desktop.tray import menu_spec, title_line


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def facade(qapp, isolated_data_dir):
    return FakeFacade(isolated_data_dir)


def test_double_press_rule():
    d = DoublePress(1000)
    assert d.press(0) == "wait" and d.pending
    assert d.press(600) == "picker" and not d.pending
    assert d.press(5000) == "wait"
    assert d.due(5500) is False and d.due(6000) is True and d.due(6001) is False
    assert d.press(8000) == "wait" and d.press(9200) == "wait"   # too slow: two single presses


def _pump(ms):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def test_hotkeys_route_to_the_facade(facade):
    integ = DesktopIntegration(facade, None)
    facade.set_desktop(integ.api)
    palette = []
    facade.paletteRequested.connect(lambda: palette.append(1))
    integ.on_hotkey("snapshot")
    integ.on_hotkey("palette")
    assert facade.capture.calls == [("snapshotNow", ())] and palette == [1]


def test_add_window_single_press_adds_after_the_window(facade, monkeypatch):
    integ = DesktopIntegration(facade, None)
    integ._double_timer.setInterval(60)
    monkeypatch.setattr("project_opener.desktop.integration.foreground_window", lambda: 4242)
    integ.on_hotkey("add_window")
    assert facade.capture.calls == []
    _pump(200)
    assert facade.capture.calls == [("addWindow", (4242,))]


def test_add_window_double_press_opens_the_picker_instead(facade, monkeypatch):
    integ = DesktopIntegration(facade, None)
    integ._double_timer.setInterval(60)
    started = []

    class FakePicker:
        def start(self):
            started.append(1)
    integ.picker = FakePicker()
    integ.on_hotkey("add_window")
    integ.on_hotkey("add_window")
    _pump(200)
    assert started == [1] and facade.capture.calls == []


def test_not_built_capture_slots_do_not_raise(facade):
    integ = DesktopIntegration(facade, None)

    def todo():
        raise NotImplementedError("CaptureApi.snapshotNow")
    facade.capture.snapshotNow = todo
    integ.on_hotkey("snapshot")      # logged, not raised


def test_shell_entries_through_app_desktop(facade, tmp_path):
    integ = DesktopIntegration(facade, None)
    reg = shellext.FakeRegistry()
    seen = []
    integ.api.shellEntriesChanged.connect(lambda: seen.append(1))

    def writer(lnk, *_a):
        lnk.write_bytes(b"lnk")
    state = integ.set_shell_entries(True, True, reg=reg, folder=tmp_path, writer=writer, frozen=True,
                                    executable=r"C:\x\ProjectOpener.exe")
    assert state == (True, True) and integ.api.property("explorerVerbInstalled") and seen
    assert facade.ctx.settings.explorer_verb is True
    state = integ.set_shell_entries(False, False, reg=reg, folder=tmp_path, writer=writer)
    assert state == (False, False) and not integ.api.property("sendToInstalled")
    assert facade.ctx.settings.sendto_entry is False


def test_hotkey_status_reaches_app_desktop(facade):
    from test_v4_desktop_hotkeys import FakeBackend

    from project_opener.desktop.hotkeys import HotkeyManager
    integ = DesktopIntegration(facade, None)
    integ.hotkeys = HotkeyManager(FakeBackend(owned_elsewhere=["Ctrl+Alt+P"]), install_filter=False)
    integ.hotkeys.statusChanged.connect(integ.api._set_hotkeys)
    integ.apply_hotkeys()
    status = integ.api.property("hotkeyStatus")
    assert status["snapshot"]["ok"] is True and status["panel"]["ok"] is False
    assert status["panel"]["error"] == "Hot key is already registered."
    integ.hotkeys.close()


def test_tray_menu_order_and_state():
    keys = {"snapshot": "Ctrl+Alt+S", "add_window": "Ctrl+Alt+A", "panel": "Ctrl+Alt+P", "palette": "Ctrl+Alt+K"}
    rows = menu_spec(True, title_line("Lot 7 check", 12, "running"), False, keys)
    texts = [r[1] for r in rows if r[0] != "-"]
    assert texts == ["Lot 7 check · 12 open · capture on", "Snapshot now", "Add a window…", "Pause capture",
                     "End activity…", "Start an activity from what's open…", "Open an activity", "Show the pill",
                     "Search…", "Show Project Opener", "Quit"]
    assert rows[0][2] is False                                   # the title line is not clickable
    assert dict((r[0], r[3]) for r in rows)["snapshot"] == "Ctrl+Alt+S"
    idle = {r[0]: r[2] for r in menu_spec(False, "", False, {})}
    assert not idle["snapshot"] and not idle["pause"] and not idle["end"] and idle["start_from_open"]
    paused = {r[0]: r[1] for r in menu_spec(True, "x", True, {})}
    assert paused["pause"] == "Resume capture"
    assert title_line("L", 3, "paused") == "L · 3 open · capture paused"


def test_tray_actions_call_the_facade(facade):
    from project_opener.desktop.tray import TrayController
    t = TrayController(facade, None)
    t.trigger("snapshot")
    t.trigger("end")
    t.trigger("start_from_open")
    assert [c[0] for c in facade.capture.calls] == ["snapshotNow", "endActivity"]
    assert facade.commands == [{"cmd": "start-from-open"}]


def test_hotkey_ids_are_the_contracts():
    assert C.HOTKEY_IDS == {"snapshot": 0xB001, "add_window": 0xB002, "panel": 0xB003, "palette": 0xB004}
