"""Round 2 juror fixes on Home's footlights (app-v4-juror-1: D1, C1, C2, brief items 4 and 5).

- C1: the Office is the board's desks, each colleague a tile in a stable pale tint of their hue; the text on
  every tint passes 4.5:1 in both themes (the tint constants are read from the QML, the one source).
- D1: each panel is as tall as its content, the three share one height and top edge (bottoms level), and
  each panel's action is in its heading; rows cap at 4.
- C2 / brief 4: a down drive's second line reads "down since 09:40 · seen by 3 PCs · 14 jobs" whole.
- Brief 5: the newest current announcement shows as one line above the panels and hides when there is none.

The QML half runs in a child process (offscreen), so the engine never shares this process's QApplication.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtGui import QColor

from project_opener.ui import theme

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "project_opener" / "qml" / "components"


def _tint_constants(qml: Path) -> dict[bool, tuple[float, float]]:
    s = qml.read_text(encoding="utf-8")
    ms = re.search(r"tintS:\s*tk\.dark\s*\?\s*([\d.]+)\s*:\s*([\d.]+)", s)
    ml = re.search(r"tintL:\s*tk\.dark\s*\?\s*([\d.]+)\s*:\s*([\d.]+)", s)
    assert ms and ml, f"tintS / tintL not found in {qml.name}"
    return {True: (float(ms.group(1)), float(ml.group(1))), False: (float(ms.group(2)), float(ml.group(2)))}


@pytest.mark.parametrize("qml", ["DeskTile.qml", "Avatar.qml"])
@pytest.mark.parametrize("dark", [True, False], ids=["dark", "light"])
def test_desk_tint_text_passes_4_5_for_every_hue(qml, dark):
    """Qt.hsla in QML and QColor.fromHslF are one algorithm, so this is the colour the tile draws."""
    s, lum = _tint_constants(COMP / qml)[dark]
    t = theme.build_tokens(dark)
    worst = []
    for hue in range(360):
        bg = QColor.fromHslF(hue / 360, s, lum).name()
        for name, fg in (("text", t.text), ("text_muted", t.text_muted)):
            c = theme.contrast(fg, bg)
            if c < 4.5:
                worst.append(f"{name} on hue {hue} ({bg}): {c:.2f}")
    assert not worst, worst[:8]


def test_desk_tile_and_avatar_share_the_tint():
    assert _tint_constants(COMP / "DeskTile.qml") == _tint_constants(COMP / "Avatar.qml")


@pytest.mark.parametrize("dark", [True, False], ids=["dark", "light"])
def test_offline_desk_and_initials_disc_pass(dark):
    t = theme.build_tokens(dark)
    assert theme.contrast(t.text_muted, t.surface_2) >= 4.5      # an offline desk: muted on surface_2
    assert theme.contrast(t.text, t.surface) >= 4.5              # the initials disc


def test_panel_actions_sit_in_the_heading_not_the_foot():
    """No panel carries a foot action: the "N more" link left TasksPanel for its heading's facts."""
    tasks = (COMP / "TasksPanel.qml").read_text(encoding="utf-8")
    assert '" more"' in tasks and 'kind: "link"' not in tasks
    for name in ("DrivesPanel.qml", "TasksPanel.qml", "OfficePanel.qml"):
        s = (COMP / name).read_text(encoding="utf-8")
        assert "implicitHeight: list.y + list.implicitHeight + pad" in s, name
        assert "* 48 + 40" not in s, name                       # the old fixed-height formula (panel-void)


CHILD = r'''
import json, os, sys
from pathlib import Path
ROOT = Path(sys.argv[1]); work = Path(sys.argv[2])
sys.path.insert(0, str(ROOT))
os.environ["PO_DATA_DIR"] = str(work / "data")
from PySide6.QtCore import QUrl, QTimer, QEventLoop
from PySide6.QtQml import QQmlComponent, QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
msgs = []
from PySide6.QtCore import qInstallMessageHandler
qInstallMessageHandler(lambda mode, ctx, m: msgs.append(m))
app = QApplication(sys.argv)
QQuickStyle.setStyle("Basic")
from project_opener.quick.facade import AppFacade
from project_opener.ui import theme
theme.load_fonts()
f = AppFacade(work / "data")

def find_all(item, name):
    hits, stack = [], [item]
    while stack:
        it = stack.pop()
        if it.objectName() == name:
            hits.append(it)
        stack.extend(it.childItems())
    return hits

def find(item, name):
    hits = find_all(item, name)
    return hits[0] if hits else None

def pump(ms):
    loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

peers = [
    {"login": "ravi", "displayName": "Ravi", "role": "Designer", "host": "PC2", "online": False, "doing": "",
     "initials": "RA", "hue": 140, "cliqLinked": False},
    {"login": "priya", "displayName": "Priya", "role": "Checker", "host": "PC1", "online": True,
     "doing": "DM-GAD · Mangala GAD review", "initials": "PR", "hue": 40, "cliqLinked": False},
]
for i in range(4):
    peers.append({"login": f"u{i}", "displayName": f"User {i}", "role": "", "host": "", "online": i < 2,
                  "doing": "", "initials": f"U{i}", "hue": 60 * i, "cliqLinked": False})
f.hub._peers.reset(peers)
f.hub.peersChanged.emit()
f.watchers._roots.reset([
    {"rootName": "\\\\nas01", "status": "offline", "statusLabel": "Server offline", "mapping": "Z: → \\\\nas01\\Project",
     "uses": "3 items · P12513", "seenBy": 3, "since": "2026-11-05T09:40:00",
     "sinceText": "down since 09:40 · seen by 3 PCs", "jobsAffected": 14},
    {"rootName": "W:", "status": "ok", "statusLabel": "Reachable", "mapping": "W: → \\\\nas01\\Submissions",
     "uses": "1 item", "seenBy": 0, "since": "", "sinceText": "", "jobsAffected": 0},
])
f.watchers.rootsChanged.emit()
NEWS = [
    {"announcementId": "a1", "title": "Old notice", "body": "x", "level": "info", "author": "y", "authorName": "Y",
     "ts": "2026-11-01T09:00:00", "tsText": "4 d ago", "mine": False},
    {"announcementId": "a2", "title": "Z: drive moves on Friday", "body": "The share moves.", "level": "warning",
     "author": "yokesh", "authorName": "Yokesh", "ts": "2026-11-05T10:00:00", "tsText": "just now", "mine": False},
]
f.hub._announcements.reset(NEWS)
f.ui.setMotion(sys.argv[3])

engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("app", f)
comp_dir = (ROOT / "project_opener" / "qml" / "components").as_uri()
src = ('import QtQuick\nimport QtQuick.Window\nimport "' + comp_dir + '"\n'
       'Window { width: %d; height: 900; visible: true\n'
       '  Footlights { objectName: "strip"; width: %d } }\n')
out = {}
for label, w, sw in (("wide", 1400, 1252), ("stack", 1040, 916)):
    c = QQmlComponent(engine)
    c.setData((src % (w, sw)).encode("utf-8"), QUrl.fromLocalFile(str(work / f"t_{label}.qml")))
    win = c.create()
    if win is None:
        print(json.dumps({"error": [e.toString() for e in c.errors()], "msgs": msgs})); sys.exit(2)
    win.requestActivate()
    pump(500)
    top = win.contentItem()
    strip = find(top, "strip")
    panels = {n: find(top, n) for n in ("footNews", "footDrives", "footTasks", "footOffice")}
    geo = {n: [p.x(), p.y(), p.width(), p.height(), p.property("implicitHeight"), p.isVisible()] for n, p in panels.items()}
    desks = [d for d in find_all(top, "deskTile") if d.isVisible()]
    desks.sort(key=lambda d: d.mapToScene(d.position()).y())
    facts = [x for x in find_all(top, "driveFacts") if x.isVisible()][0]
    title = find(top, "newsTitle")
    out[label] = {"geo": geo, "strip_h": strip.height(),
                  "desks": [[d.property("displayName"), d.property("online"), d.height()] for d in desks],
                  "facts": facts.property("text"), "facts_truncated": facts.property("truncated"),
                  "facts_lines": facts.property("lineCount"),
                  "title": title.property("text"), "title_truncated": title.property("truncated"),
                  "active": win.isActive()}
    if label == "wide":
        # an arrival: ravi comes online; the ring plays once at k-scaled length (none in off)
        peers[0]["online"] = True
        f.hub._peers.reset(peers)
        f.hub.peersChanged.emit()
        pump(100)
        ravi = [d for d in find_all(top, "deskTile") if d.property("login") == "ravi"]
        out["ring"] = [ravi[0].property("ringing"), ravi[0].property("ringMs")] if ravi else None
        # no announcement: the line hides and the panels move up
        f.hub._announcements.reset([])
        pump(200)
        out["no_news"] = {"visible": panels["footNews"].isVisible(), "drives_y": panels["footDrives"].y()}
        f.hub._announcements.reset(NEWS)
        peers[0]["online"] = False
        f.hub._peers.reset(peers)
        f.hub.peersChanged.emit()
    win.close()
    win.deleteLater()
    pump(100)
msgs = [m for m in msgs if not m.startswith("QFontDatabase")]     # this venv's Qt has no font folder
print("JSON" + json.dumps({"out": out, "msgs": msgs}))
f.shutdown()
'''


def _run_child(tmp_path: Path, motion: str) -> dict:
    script = tmp_path / "child.py"
    script.write_text(CHILD, encoding="utf-8")
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QML_DISK_CACHE_PATH"] = str(ROOT / "build" / "qmlcache")
    env.pop("PO_DATA_DIR", None)
    res = subprocess.run([sys.executable, str(script), str(ROOT), str(tmp_path), motion], cwd=ROOT, env=env,
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=150)
    line = next((ln for ln in res.stdout.splitlines() if ln.startswith("JSON")), None)
    assert line, (res.stdout + res.stderr)[-4000:]
    return json.loads(line[4:])


@pytest.fixture(scope="module")
def purposeful(tmp_path_factory) -> dict:
    return _run_child(tmp_path_factory.mktemp("foot-p"), "purposeful")


def test_no_qml_warnings(purposeful):
    assert purposeful["msgs"] == [], purposeful["msgs"][:10]


@pytest.mark.parametrize("label", ["wide", "stack"])
def test_panels_are_content_sized_and_end_level(purposeful, label):
    o = purposeful["out"][label]
    g = o["geo"]
    news, drives, tasks, office = g["footNews"], g["footDrives"], g["footTasks"], g["footOffice"]
    assert news[5] and news[3] == 40
    if label == "wide":
        assert drives[1] == tasks[1] == office[1] == 56                      # one top edge under the line
        h = max(drives[4], tasks[4], office[4])
        assert drives[3] == tasks[3] == office[3] == h                       # one height: bottoms level
        assert o["strip_h"] == 56 + h
    else:
        assert drives[2] > tasks[2] and drives[3] == drives[4]               # drive map full width
        assert tasks[1] == office[1] and tasks[3] == office[3] == max(tasks[4], office[4])
    # no panel is taller than its tallest neighbour's content: implicitHeight follows the rows, not a formula
    assert tasks[4] < 200                                                    # empty tasks: heading + empty state


@pytest.mark.parametrize("label", ["wide", "stack"])
def test_office_desks_online_first_capped_at_four(purposeful, label):
    desks = purposeful["out"][label]["desks"]
    assert len(desks) == 4
    assert [d[1] for d in desks] == [True, True, True, False]
    assert desks[0][0] == "Priya" and all(d[2] == 44 for d in desks)


@pytest.mark.parametrize("label", ["wide", "stack"])
def test_down_drive_reads_whole(purposeful, label):
    o = purposeful["out"][label]
    assert o["facts"].replace(" ", " ") == "down since 09:40 · seen by 3 PCs · 14 jobs"
    assert o["facts_truncated"] is False


def test_newest_announcement_shows_and_hides(purposeful):
    o = purposeful["out"]["wide"]
    assert o["title"] == "Z: drive moves on Friday" and o["title_truncated"] is False
    assert purposeful["out"]["no_news"] == {"visible": False, "drives_y": 0}


def test_arrival_ring_purposeful(purposeful):
    ring = purposeful["out"]["ring"]
    assert ring is not None and ring[1] == 1440                              # 2400 ms x 0.6
    if purposeful["out"]["wide"]["active"]:
        assert ring[0] is True


def test_arrival_ring_none_in_off(tmp_path):
    res = _run_child(tmp_path, "off")
    assert res["msgs"] == [], res["msgs"][:10]
    assert res["out"]["ring"] == [False, 0]
