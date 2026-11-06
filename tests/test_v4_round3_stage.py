"""Juror round 2 fixes on the stage, the Monitors panel, the empty states and the copy (app-v4-juror-2).

- D2-1 / C2-1: Monitors frames are drawn in border_strong; only a window that needs a path (warning) or whose
  server is offline (danger) is coloured; each screen's label sits in a strip under it; an activity that is
  not running shows its last snapshot's frames at 50 % (``CaptureApi.lastWindows``).
- D2-3: a wing carries no task line; the centre's task rows put the due date in its own right-aligned
  column, so the title elides and the date never does.
- D2-4: no title-row action repeats the empty block's; Projects' empty state is framed; the empty block is
  sized to its content; the icon picker is a fixed-column grid (16 icons: one row of 16 or two of 8).
- T2-4: empty states are one trade-word line plus the action; Settings has no subtitle; the Snapshot tab
  states a fact; the Save-new rule is the button's tooltip.

The QML half runs in a child process (offscreen), so the engine never shares this process's QApplication.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_v4_quick_facade import facade, qapp, seeded  # noqa: E402,F401

from project_opener.core import models as M  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
QML = ROOT / "project_opener" / "qml"


def _placement(x: int, y: int, w: int, h: int) -> M.WindowPlacement:
    return M.WindowPlacement(show_cmd=1, normal_rect=[x, y, x + w, y + h], window_rect=[x, y, x + w, y + h],
                             monitor=r"\\.\DISPLAY1", monitor_rect=[0, 0, 1920, 1080])


def _entries() -> list[M.SnapshotEntry]:
    return [M.SnapshotEntry(key="path:a", status="identified", path=r"D:\Jobs\a.pdf", kind="file",
                            placement=_placement(0, 0, 960, 1080)),
            M.SnapshotEntry(key="win:b", status="unidentified", doc_name="GAD-0121-B.pdf", app="PDF-XChange",
                            placement=_placement(960, 0, 960, 540))]


# ------------------------------------------------------------ D2-1 / C2-1: the API
def test_last_windows_of_an_activity_that_is_not_running(facade, seeded):  # noqa: F811
    aid = seeded["act"]
    assert facade.capture.lastWindows(aid) == {"takenText": "", "rows": []}
    facade.snapshots.add_checkpoint(M.Checkpoint(activity_id=aid, kind="manual",
                                                 snapshot=M.Snapshot(activity_id=aid, entries=_entries())))
    got = facade.capture.lastWindows(aid)
    assert got["takenText"] != ""
    rows = {r["status"]: r for r in got["rows"]}
    assert set(rows) == {"identified", "unidentified"}
    assert rows["identified"]["monitor"] == "monitor 1"
    assert rows["identified"]["placeW"] == pytest.approx(0.5)
    assert rows["unidentified"]["placeX"] == pytest.approx(0.5) and rows["unidentified"]["placeH"] == pytest.approx(0.5)
    assert facade.capture.lastWindows("") == {"takenText": "", "rows": []}


# ------------------------------------------------------------ D2-1, D2-3: rendered
CHILD = r'''
import json, os, sys
from pathlib import Path
ROOT = Path(sys.argv[1]); work = Path(sys.argv[2])
sys.path.insert(0, str(ROOT))
os.environ["PO_DATA_DIR"] = str(work / "data")
from PySide6.QtCore import QPointF, QUrl, QTimer, QEventLoop, qInstallMessageHandler
from PySide6.QtQml import QQmlComponent, QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
msgs = []
qInstallMessageHandler(lambda mode, ctx, m: msgs.append(m))
app = QApplication(sys.argv)
QQuickStyle.setStyle("Basic")
from project_opener.core import models as M
from project_opener.quick.facade import AppFacade
from project_opener.ui import theme
theme.load_fonts()
f = AppFacade(work / "data")
f.ui.setMotion("purposeful")

def pl(x, y, w, h):
    return M.WindowPlacement(show_cmd=1, normal_rect=[x, y, x + w, y + h], window_rect=[x, y, x + w, y + h],
                             monitor=r"\\.\DISPLAY1", monitor_rect=[0, 0, 1920, 1080])
entries = [M.SnapshotEntry(key="path:a", status="identified", path=r"D:\Jobs\a.pdf", kind="file", placement=pl(0, 0, 960, 1080)),
           M.SnapshotEntry(key="win:b", status="unidentified", doc_name="GAD-0121-B.pdf", app="PDF-XChange",
                           placement=pl(960, 0, 960, 540))]
f.snapshots.add_checkpoint(M.Checkpoint(activity_id="act1", kind="manual",
                                        snapshot=M.Snapshot(activity_id="act1", entries=entries)))

def find_all(item, name):
    hits, stack = [], [item]
    while stack:
        it = stack.pop()
        if it.objectName() == name:
            hits.append(it)
        stack.extend(it.childItems())
    return hits

def pump(ms):
    loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("app", f)
comp_dir = (ROOT / "project_opener" / "qml" / "components").as_uri()
TASK = "Send rev C sheets to FST and copy the transmittal to the client's document controller"
src = ('import QtQuick\nimport QtQuick.Window\nimport "' + comp_dir + '"\n'
       'Window { width: 1400; height: 900; visible: true\n'
       '  Column { spacing: 10\n'
       '  MonitorsPanel { objectName: "mon"; width: 440; height: implicitHeight; running: false; activityId: "act1" }\n'
       '  Scene { objectName: "centre"; width: 750; height: 330; mode: "centre"; m: ({ activityId: "act1", title: "P12513 · Lot 7 check",\n'
       '      subtitle: "FST · 8 items", icon: "checks", dotColor: "#2F5BFF", running: false, pausedAt: "", pinned: false,\n'
       '      itemCount: 0, previewNames: [], previewGlyphs: [], problems: [], okCount: 0, healthWorst: "", driveDown: false,\n'
       '      driveText: "", newFiles: ({}), captureText: "", taskLine: "Task: GAD comments", lastOpenedText: "never opened",\n'
       '      openTasks: [{ title: "%s", dueText: "due today", overdue: false }] }) }\n'
       '  Scene { objectName: "wing"; width: 230; height: 200; mode: "wing"; m: ({ activityId: "act2", title: "DM-GAD · Mangala GAD review",\n'
       '      subtitle: "2 items · never opened", icon: "stack", dotColor: "#F97316", running: false, pausedAt: "", pinned: false,\n'
       '      itemCount: 2, previewNames: ["GAD", "GAD-0120-B.pdf"], previewGlyphs: ["folder", "file"], problems: [], okCount: 0,\n'
       '      healthWorst: "", driveDown: false, driveText: "", newFiles: ({}), captureText: "", taskLine: "Task: GAD comments to Cairn",\n'
       '      lastOpenedText: "never opened", openTasks: [] }) }\n'
       '  } }\n') % TASK
c = QQmlComponent(engine)
c.setData(src.encode("utf-8"), QUrl.fromLocalFile(str(work / "t.qml")))
win = c.create()
if win is None:
    print(json.dumps({"error": [e.toString() for e in c.errors()], "msgs": msgs})); sys.exit(2)
pump(600)
top = win.contentItem()
tk = f.ui.tokens
frames = [fr for fr in find_all(top, "monitorFrame") if fr.isVisible()]
layer = find_all(top, "monitorWindows")
faces = find_all(top, "monitorFace")
labels = find_all(top, "monitorLabel")
due = [d for d in find_all(top, "taskDue") if d.isVisible()]
title = [t for t in find_all(top, "taskTitle") if t.isVisible()]
wing = find_all(top, "wing")[0]

def sx(it):
    return it.mapToScene(QPointF(0, 0)).x()

def sy(it):
    return it.mapToScene(QPointF(0, 0)).y()

def texts(item):
    out, stack = [], [item]
    while stack:
        it = stack.pop()
        t = it.property("text")
        if isinstance(t, str) and t and it.isVisible():
            out.append(t)
        stack.extend(it.childItems())
    return out

out = {
    "frames": sorted([fr.property("edge").name() for fr in frames]),
    "layer_opacity": [l.property("opacity") for l in layer],
    "face_bottom": [sy(fa) + fa.height() for fa in faces],
    "label_top": [sy(lb) for lb in labels],
    "labels": [lb.property("text") for lb in labels],
    "tokens": {"border_strong": tk["border_strong"].lower(), "warning": tk["warning"].lower()},
    "due": [[d.property("text"), d.property("truncated")] for d in due],
    "title": [[t.property("text"), t.property("truncated")] for t in title],
    "due_right": [sx(d) + d.width() for d in due],
    "col_right": [sx(d.parentItem()) + d.parentItem().width() for d in due],
    "wing_texts": texts(wing),
}
msgs = [m for m in msgs if not m.startswith("QFontDatabase")]
print("JSON" + json.dumps({"out": out, "msgs": msgs}))
win.close()
f.shutdown()
'''


@pytest.fixture(scope="module")
def rendered(tmp_path_factory) -> dict:
    work = tmp_path_factory.mktemp("r3stage")
    script = work / "child.py"
    script.write_text(CHILD, encoding="utf-8")
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QML_DISK_CACHE_PATH"] = str(ROOT / "build" / "qmlcache")
    env.pop("PO_DATA_DIR", None)
    res = subprocess.run([sys.executable, str(script), str(ROOT), str(work)], cwd=ROOT, env=env,
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=150)
    line = next((ln for ln in res.stdout.splitlines() if ln.startswith("JSON")), None)
    assert line, (res.stdout + res.stderr)[-4000:]
    return json.loads(line[4:])


def test_render_has_no_qml_warnings(rendered):
    assert rendered["msgs"] == [], rendered["msgs"][:10]


def test_monitor_frames_neutral_unless_flagged_and_last_snapshot_at_half(rendered):
    o = rendered["out"]
    tk = o["tokens"]
    # one identified window in border_strong, one that needs a path in the warning colour; none in amber chrome
    assert sorted(o["frames"]) == sorted([tk["border_strong"], tk["warning"]])
    assert o["layer_opacity"] and all(abs(v - 0.5) < 1e-6 for v in o["layer_opacity"])     # not running: 50 %


def test_monitor_label_sits_under_the_screen(rendered):
    o = rendered["out"]
    assert o["labels"] and all(" · " in t and "×" in t for t in o["labels"])
    for bottom, top in zip(o["face_bottom"], o["label_top"], strict=True):
        assert top >= bottom, (top, bottom)                       # in its strip, never on the frame lines
    assert any("2 windows" in t for t in o["labels"])


def test_centre_task_due_date_never_elides(rendered):
    o = rendered["out"]
    assert o["due"] == [["due today", False]]
    assert o["title"] and o["title"][0][1] is True                # the long title elides instead
    assert abs(o["due_right"][0] - o["col_right"][0]) < 1.0       # right-aligned in its own column


def test_wing_has_no_task_line(rendered):
    texts = rendered["out"]["wing_texts"]
    assert not any(t.startswith("Task:") for t in texts), texts
    assert "2 items · never opened" in texts


# ------------------------------------------------------------ D2-4, T2-4: the pages' source
def _read(rel: str) -> str:
    return (QML / rel).read_text(encoding="utf-8")


def test_no_title_row_action_repeats_the_empty_block():
    home = _read("pages/HomePage.qml")
    assert 'visible: home.n > 0              // with no activities the empty block offers it' in home
    acts = _read("pages/ActivitiesPage.qml")
    assert 'visible: app.capture.runningId === "" && rep.count > 0' in acts
    projects = _read("pages/ProjectsPage.qml")
    assert projects.count("visible: app.activities.projectCount > 0") >= 2      # New project and the search row


def test_empty_states_are_one_line_and_framed():
    home = _read("pages/HomePage.qml")
    assert 'Txt { text: "No activities yet."; role: "heading" }' in home
    assert "height: emptyCol.implicitHeight + 2 * pad" in home                   # sized to its content
    assert "Open what a task needs" not in home
    assert 'line: "No activities yet."' in _read("pages/ActivitiesPage.qml")
    projects = _read("pages/ProjectsPage.qml")
    assert '"No projects yet."' in projects and "A project holds" not in projects
    assert "height: projectsEmpty.implicitHeight + 2 * pad" in projects         # framed in a Card
    assert "implicitHeight: col.implicitHeight " in _read("components/EmptyBlock.qml")


def test_icon_picker_is_a_fixed_column_grid():
    ed = _read("sheets/ActivityEditor.qml")
    assert "Grid {\n                id: iconPick" in ed
    assert "columns: width >= 16 * 40 - 6 ? 16 : 8" in ed
    icons = ed.split('model: ["stack"', 1)[1].split("]", 1)[0]
    assert icons.count('"') // 2 + 1 == 16                                      # two full rows of 8


def test_interface_sentences_are_gone():
    settings = _read("pages/SettingsPage.qml")
    assert "Saved as you change them" not in settings
    assert "the watcher keeps a snapshot" not in settings
    assert "10 checkpoints kept per activity" in settings
    save = _read("sheets/SaveNewSheet.qml")
    assert 'confirmTooltip: total > 0 ? "Unticked things stay open' in save
    assert 'text: "Unticked things' not in save
    assert "tooltip: sheet.confirmTooltip" in _read("components/Sheet.qml")
