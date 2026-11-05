"""Offscreen renders of the pill in every state, the panel and the picker overlay (builder 3).

Each state loads the real ``qml/desktop`` files through ``PillController`` with fake capture data,
must produce no QML warnings, and is saved as a PNG on the board's backdrop colour.  Set
``PO_B3_SHOTS`` to a folder to keep the images (they go to pytest's temp folder otherwise).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from PySide6.QtWidgets import QApplication
from test_v4_desktop_fakes import FakeFacade

from project_opener.desktop import pill as P
from project_opener.desktop.integration import DesktopApi

QML_DIR = Path(__file__).resolve().parents[1] / "project_opener" / "qml"
BACKDROP = "#1C2B33"          # the board's desktop colour

LIVE = [
    {"entryKey": "win:acad|Drawing1", "status": "unidentified", "name": "Drawing1", "appName": "AutoCAD"},
    {"entryKey": "path:z:\\p12513\\ise\\rev c", "status": "offline", "name": "Revision C", "appName": "Explorer"},
    {"entryKey": "path:z:\\p12513_model.nwd", "status": "identified", "name": "P12513_Model.nwd",
     "appName": "Navisworks"},
    {"entryKey": "path:z:\\line list.xlsx", "status": "identified", "name": "Line list.xlsx", "appName": "Excel"},
] + [{"entryKey": f"path:z:\\iso-{i}.pdf", "status": "identified", "name": f"P12513-ISO-10{i}.pdf",
      "appName": "PDF-XChange"} for i in range(8)]


@pytest.fixture(scope="module")
def qapp():
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
    app = QApplication.instance() or QApplication([])
    from project_opener.ui import theme
    theme.load_fonts()
    return app


@pytest.fixture
def warnings():
    seen: list[str] = []

    def handler(mode, _ctx, msg):
        # the offscreen platform has no font directory; that is the test platform, not our QML
        if mode != QtMsgType.QtDebugMsg and "propagateSizeHints" not in msg and "QFontDatabase" not in msg:
            seen.append(msg)
    previous = qInstallMessageHandler(handler)
    yield seen
    qInstallMessageHandler(previous)


def _shots_dir(tmp_path: Path) -> Path:
    d = Path(os.environ.get("PO_B3_SHOTS") or tmp_path / "shots")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _settle(app, rounds=8):
    for _ in range(rounds):
        app.processEvents()


def _save(win, path: Path, pad: int = 24) -> QImage:
    img = win.grabWindow()
    assert not img.isNull() and img.width() > 0
    out = QImage(img.width() + 2 * pad, img.height() + 2 * pad, QImage.Format.Format_ARGB32)
    out.setDevicePixelRatio(img.devicePixelRatio())
    out.fill(QColor(BACKDROP))
    p = QPainter(out)
    p.drawImage(pad / img.devicePixelRatio(), pad / img.devicePixelRatio(), img)
    p.end()
    out.save(str(path))
    return img


@pytest.fixture
def rig(qapp, isolated_data_dir):
    from PySide6.QtQml import QQmlEngine
    facade = FakeFacade(isolated_data_dir)
    api = DesktopApi(facade)
    api._set_hotkeys({"snapshot": {"keys": "Ctrl+Alt+S", "ok": True, "error": ""}})
    facade.set_desktop(api)
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("app", facade)
    ctl = P.PillController(facade, engine, QML_DIR)
    yield facade, ctl, qapp
    ctl.destroy()
    _settle(qapp)


RUNNING = dict(running_id="a1", running_name="P12513 · Lot 7 check", running_label="Lot 7 check",
               running_color="#4F7DFF", state="running", open=12, identified=9, needs_path=0,
               last_checkpoint_text="10:52", since_checkpoint=2)

STATES = {
    "1-running": dict(RUNNING),
    "2-needs-amber": {**RUNNING, "state": "needs", "needs_path": 3},
    "3-needs-red": {**RUNNING, "state": "needs", "needs_path": 0, "drive_down": True},
    "4-paused": {**RUNNING, "state": "paused"},
    "6-start-pinned": dict(running_id="", state="idle"),
}


@pytest.mark.parametrize("name", list(STATES))
def test_pill_state_renders(rig, warnings, tmp_path, name):
    facade, ctl, app = rig
    if name == "6-start-pinned":
        facade.ctx.settings.pill_pinned = True
    facade.capture.set(**STATES[name])
    ctl.create()
    _settle(app)
    assert ctl.window is not None and ctl.window.isVisible()
    img = _save(ctl.window, _shots_dir(tmp_path) / f"pill-{name}.png")
    assert img.height() / img.devicePixelRatio() == pytest.approx(P.CAPSULE_H, abs=1)
    assert warnings == []


def test_pill_saved_flash_then_back(rig, warnings, tmp_path):
    facade, ctl, app = rig
    facade.capture.set(**RUNNING)
    ctl.create()
    facade.capture.checkpointSaved.emit("cp1", 12, "14:32")
    _settle(app)
    assert ctl.view["kind"] == "saved" and ctl.view["detail"] == "12 things · 14:32"
    _save(ctl.window, _shots_dir(tmp_path) / "pill-5-saved.png")
    ctl._saved_over()
    assert ctl.view["kind"] == "running"
    assert warnings == []


def test_pill_hidden_when_idle_or_quiet(rig):
    facade, ctl, app = rig
    facade.capture.set(state="idle", running_id="")
    ctl.create()
    _settle(app)
    assert not ctl.window.isVisible()
    facade.capture.set(**RUNNING)
    _settle(app)
    assert ctl.window.isVisible()
    ctl.set_quiet(True)
    assert not ctl.window.isVisible()
    ctl.set_quiet(False)
    assert ctl.window.isVisible()


def test_edge_tab_renders(rig, warnings, tmp_path):
    facade, ctl, app = rig
    facade.ctx.settings.pill_rest_style = "edge"
    facade.capture.set(**RUNNING)
    ctl.create()
    ctl._edge, ctl._offset = "right", 400
    ctl._apply_geometry()
    _settle(app)
    g = ctl.window.geometry()
    assert (g.width(), g.height()) == P.EDGE_TAB
    work = ctl.window.screen().availableGeometry()
    assert g.x() + g.width() == work.x() + work.width()        # flush with the right edge
    _save(ctl.window, _shots_dir(tmp_path) / "pill-7-edge-tab.png", pad=40)
    assert warnings == []


def test_panel_renders_and_opens_upward(rig, warnings, tmp_path):
    facade, ctl, app = rig
    facade.capture.set(**{**RUNNING, "new": 2})
    facade.capture.live.reset(LIVE)
    ctl.create()
    _settle(app)
    rest = ctl.window.geometry()
    ctl.openPanel()
    _settle(app, 20)
    g = ctl.window.geometry()
    assert ctl.property("panelOpen") is True
    assert g.width() >= 400 and g.height() > 200
    assert g.bottom() == rest.bottom() and g.right() == rest.right()     # grew up and left from the pill
    _save(ctl.window, _shots_dir(tmp_path) / "panel-1-open.png")
    facade.capture.set(state="paused")
    _settle(app, 10)
    _save(ctl.window, _shots_dir(tmp_path) / "panel-2-paused.png")
    ctl.closePanel()
    _settle(app, 10)
    back = ctl.window.geometry()                       # "paused" is wider than "12": same right end
    assert (back.right(), back.bottom()) == (rest.right(), rest.bottom())
    assert warnings == []


def test_panel_light_theme(rig, warnings, tmp_path):
    facade, ctl, app = rig
    from project_opener.quick.ui_state import tokens_for
    s = facade.ctx.settings
    facade.ui._tokens = tokens_for(False, s.accent, s.density)
    facade.capture.set(**RUNNING)
    facade.capture.live.reset(LIVE[:3])
    ctl.create()
    ctl.openPanel()
    _settle(app, 20)
    _save(ctl.window, _shots_dir(tmp_path) / "panel-3-light.png")
    assert warnings == []


def test_panel_actions(rig):
    facade, ctl, _app = rig
    facade.capture.set(**RUNNING)
    for a in ("snapshot", "save_new", "pause", "resume"):
        ctl.act(a)
    ctl.act("review")
    assert [c[0] for c in facade.capture.calls] == ["snapshotNow", "saveNewAsItems", "pause", "resume"]
    assert facade.ui.routes == [("activity", {"activityId": "a1", "focus": "unidentified"})]
    ctl.act("start_from_open")
    assert facade.commands == [{"cmd": "start-from-open"}]


def test_picker_overlay_renders(qapp, isolated_data_dir, warnings, tmp_path):
    from PySide6.QtQml import QQmlEngine

    from project_opener.desktop.picker import WindowPicker
    facade = FakeFacade(isolated_data_dir)
    facade.capture.set(**RUNNING)
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("app", facade)
    picker = WindowPicker(facade, engine, QML_DIR)
    picker._create_overlays()
    assert picker._overlays
    ov = picker._overlays[0]
    for name, ok, label in (("amber", False, "AutoCAD · Drawing1\nNo file path. You will be asked for it once."),
                            ("green", True, "Excel · Line list.xlsx\nZ:\\P12513\\Line list.xlsx")):
        picker._hwnd, picker._rect = 99, (120, 140, 560, 420)
        picker._labels[99] = (ok, label)
        picker.frameChanged.emit()
        _settle(qapp)
        img = ov.grabWindow()
        assert not img.isNull()
        img.save(str(_shots_dir(tmp_path) / f"picker-{name}.png"))
    ov.hide()
    picker.close()
    assert warnings == []
