"""``app.capture`` (CaptureApi) over a fake facade: real store and snapshot store, fake engine."""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from project_opener.capture.identify import entry_key  # noqa: E402
from project_opener.core import models as M  # noqa: E402
from project_opener.core.pathvars import PathResolver  # noqa: E402
from project_opener.core.settings import Settings  # noqa: E402
from project_opener.core.snapshots import SnapshotStore  # noqa: E402
from project_opener.quick.capture_api import CaptureApi, time_text  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeEngine:
    def __init__(self):
        self.calls: list[tuple] = []
        self.alive = True

    def __getattr__(self, name):
        def rec(*a, **k):
            self.calls.append((name, *a))
        return rec

    def start(self):
        pass

    def stop(self):
        self.alive = False


class FakeApp(QObject):
    toast = Signal(str, str, str)
    chooserRequested = Signal("QStringList")

    def __init__(self, store, data):
        super().__init__()
        settings = Settings.load(data)
        self.ctx = SimpleNamespace(settings=settings, store=store, resolver=PathResolver({}, drive_map={}),
                                   launcher=SimpleNamespace(openers={}, open_item=lambda item: None))
        self.snapshots = SnapshotStore(data)
        self.toasts: list[tuple] = []
        self.toast.connect(lambda t, b, lvl: self.toasts.append((t, b, lvl)))

    def run_on_gui(self, fn):
        fn()


def ent(path="", status="identified", kind="file", title="t", process="app.exe", doc="", exe="", pid=4242):
    return M.SnapshotEntry(key=entry_key(status, path if status == "identified" else "", process, title),
                           status=status, kind=kind if status == "identified" else "",
                           path=path if status == "identified" else "", title=title, process=process, doc_name=doc,
                           exe=exe, pid=pid, identified_by="shell", app=process.split(".")[0].title(),
                           placement=M.WindowPlacement(1, [0, 0, 10, 10], [0, 0, 10, 10], "\\\\.\\DISPLAY2",
                                                       [0, 0, 1920, 1080]))


@pytest.fixture
def rig(qapp, store, isolated_data_dir):
    act = M.Activity(name="Lot 7 check", items=[M.ActivityItem(path=r"U:\Lot 7\list.xlsx", id="i1")])
    store.add_activity(act)
    app = FakeApp(store, isolated_data_dir)
    api = CaptureApi(app)
    api._engine = FakeEngine()
    return SimpleNamespace(app=app, api=api, act=act, store=store, engine=api._engine)


def test_start_activity_marks_running_and_starts_passes(rig):
    rig.api.startActivity(rig.act.id)
    assert rig.api.runningId == rig.act.id and rig.api.runningLabel == "Lot 7 check"
    assert rig.api.state == "running"
    m = rig.app.snapshots.markers()
    assert m and m[0].activity_id == rig.act.id and m[0].pid == os.getpid()
    names = [c[0] for c in rig.engine.calls]
    assert names[:2] == ["run_activity", "set_paused"] and rig.engine.calls[1][1] is False


def test_live_list_worst_first_counts_and_needs_state(rig):
    rig.api.startActivity(rig.act.id)
    s = M.Snapshot(rig.act.id, entries=[
        ent(r"U:\Lot 7\list.xlsx"), ent(r"U:\Lot 7\new.pdf"), ent(status="unidentified", title="Calculator"),
        ent(status="unidentified", title="GA.dwg - AutoCAD", doc="GA.dwg"), ent(status="unsaved", title="Book1")])
    s.entries[0].item_id = "i1"
    rig.api._on_snapshot(s)
    rows = rig.api.live.rows
    assert [r["status"] for r in rows] == ["unidentified", "unsaved", "window", "identified", "identified"]
    assert rig.api.openCount == 5 and rig.api.identifiedCount == 2
    assert rig.api.needsPathCount == 1 and rig.api.newCount == 1
    assert rig.api.state == "needs"
    assert next(r for r in rows if r["path"].endswith("list.xlsx"))["isItem"]
    assert rows[0]["monitor"] == "DISPLAY2"        # offscreen test screens: the device's short name
    assert rows[0]["placeW"] == round(10 / 1920, 4) and rows[0]["placeX"] == 0.0


def test_snapshot_for_another_activity_is_ignored(rig):
    rig.api.startActivity(rig.act.id)
    rig.api._on_snapshot(M.Snapshot("other", entries=[ent(r"U:\x.pdf")]))
    assert rig.api.openCount == 0


def test_save_new_as_items(rig):
    rig.api.startActivity(rig.act.id)
    rig.api._on_snapshot(M.Snapshot(rig.act.id, entries=[ent(r"U:\Lot 7\new.pdf"), ent(r"U:\Lot 7\list.xlsx")]))
    rig.api.saveNewAsItems()
    act = rig.store.activity(rig.act.id)
    assert [i.path for i in act.items] == [r"U:\Lot 7\list.xlsx", r"U:\Lot 7\new.pdf"]
    assert rig.api.newCount == 0
    assert any(c[0] == "update_items" for c in rig.engine.calls)


def test_checkpoint_saved_state_and_models(rig):
    rig.api.startActivity(rig.act.id)
    saved = []
    rig.api.checkpointSaved.connect(lambda i, n, t: saved.append((i, n, t)))
    cp = M.Checkpoint(rig.act.id, M.Snapshot(rig.act.id, entries=[ent(r"U:\a.pdf")]))
    rig.app.snapshots.add_checkpoint(cp)
    rig.api._on_checkpoint(cp)
    assert saved and saved[0][0] == cp.id and saved[0][1] == 1
    assert rig.api.state == "saved"
    assert rig.api.checkpoints.rows[0]["checkpointId"] == cp.id and rig.api.checkpoints.rows[0]["isLatest"]
    assert rig.api.lastCheckpointText == time_text(cp.taken_at)
    rig.api._end_saved()
    assert rig.api.state == "running"


def test_add_window_flows(rig):
    results = []
    rig.api.addResult.connect(lambda ok, msg, needs, key: results.append((ok, msg, needs)))
    chooser = []
    rig.app.chooserRequested.connect(lambda paths: chooser.append(list(paths)))
    # nothing running: identified -> the chooser
    rig.api._on_identified(1, ent(r"U:\x.pdf"), "add")
    assert chooser == [[r"U:\x.pdf"]] and results[-1][0] is False
    rig.api.startActivity(rig.act.id)
    rig.api._on_identified(1, ent(r"U:\x.pdf", process="PDFXEdit.exe"), "add")
    assert results[-1][0] is True and "x.pdf" in results[-1][1]
    rig.api._on_identified(1, ent(r"U:\x.pdf"), "add")
    assert results[-1][1].startswith("Already in")
    rig.api._on_identified(2, ent(status="unsaved", title="Drawing1.dwg - AutoCAD"), "add")
    assert results[-1][0] is False and results[-1][2] is True and "Unsaved: no file yet" in results[-1][1]
    rig.api._on_identified(3, ent(r"U:\me.pdf", pid=os.getpid()), "add")
    assert results[-1][1] == "That is Project Opener's own window"
    assert [i.path for i in rig.store.activity(rig.act.id).items][-1] == r"U:\x.pdf"


def test_hover_labels(rig):
    got = []
    rig.api.hoverIdentified.connect(lambda h, ok, label: got.append((h, ok, label)))
    rig.api._on_identified(5, ent(r"U:\Lot 7\Line list.xlsx", process="EXCEL.EXE"), "hover")
    rig.api._on_identified(6, ent(status="unidentified", title="Calculator"), "hover")
    assert got[0] == (5, True, "Line list.xlsx · Excel\n" + r"U:\Lot 7\Line list.xlsx")
    assert got[1][:2] == (6, False) and got[1][2].startswith("App · Calculator\nNot a file")


def test_attach_path_add_as_application_and_ignore(rig):
    rig.api.startActivity(rig.act.id)
    amb = ent(status="unidentified", title="GA.dwg - AutoCAD", doc="GA.dwg", process="acad.exe",
              exe=r"C:\AutoCAD\acad.exe")
    rig.api._on_snapshot(M.Snapshot(rig.act.id, entries=[amb]))
    rig.api.attachPath(amb.key, r'"U:\Lot 7\GA.dwg"')
    rig.api.addAsApplication(amb.key)
    paths = [i.path for i in rig.store.activity(rig.act.id).items]
    assert r"U:\Lot 7\GA.dwg" in paths and r"C:\AutoCAD\acad.exe" in paths
    rig.api.ignoreEntry(amb.key)
    assert {"process": "acad.exe", "title": "GA.dwg - AutoCAD"} in rig.app.ctx.settings.capture_ignore
    assert rig.api.live.rows == []
    assert any(c[0] == "set_ignore_rules" for c in rig.engine.calls)


def test_pause_resume_global_switch(rig):
    rig.api.startActivity(rig.act.id)
    rig.api.pause()
    assert rig.api.state == "paused" and rig.engine.calls[-1] == ("set_paused", True)
    rig.api.resume()
    assert rig.api.state == "running"
    rig.api.setGlobal(False)
    assert rig.api.state == "paused" and not rig.api.globalEnabled
    assert Settings.load(rig.app.ctx.settings._root).capture_enabled is False


def test_end_activity_requests_close_checkpoint_and_clears_marker(rig):
    rig.api.startActivity(rig.act.id)
    rig.api.endActivity()
    assert ("request_snapshot", "close", "") in rig.engine.calls
    assert rig.engine.calls[-1] == ("stop_activity",)
    assert rig.app.snapshots.markers() == [] and rig.api.state == "idle" and rig.api.runningId == ""


def test_start_from_open(rig):
    ready = []
    rig.api.startCandidatesReady.connect(lambda: ready.append(1))
    rig.api._on_candidates([ent(r"U:\a.pdf"), ent(status="unidentified", title="Inbox", process="OUTLOOK.EXE",
                                                  exe=r"C:\Office\OUTLOOK.EXE"),
                            ent("https://x.com", kind="url"), ent(status="ambiguous", title="iso", doc="iso.pdf")])
    rows = {r["name"]: r for r in rig.api.startCandidates.rows}
    assert ready and rows["a.pdf"]["ticked"] and not rows["Inbox"]["ticked"] and not rows["iso.pdf"]["ticked"]
    rig.api.setCandidateTicked(rows["Inbox"]["entryKey"], True)
    rig.api.setCandidateTicked(rows["iso.pdf"]["entryKey"], True)
    new_id = rig.api.startFromOpen("Morning", "")
    act = rig.store.activity(new_id)
    assert [(i.path, i.kind) for i in act.items] == [(r"U:\a.pdf", "file"), ("https://x.com", "url"),
                                                     (r"C:\Office\OUTLOOK.EXE", "app")]
    assert rig.api.runningId == new_id
    assert any("need a path" in t[1] for t in rig.app.toasts)


def test_restore_latest_with_nothing_saved_and_with_a_snapshot(rig):
    done = []
    rig.api.restoreFinished.connect(lambda r: done.append(r))
    rig.api.restoreLatest(rig.act.id)
    assert done and done[0]["opened"] == 0
    rig.app.snapshots.save_live(M.Snapshot(rig.act.id, entries=[ent(r"U:\a.pdf")]))
    rig.api.restoreLatest(rig.act.id)
    assert rig.engine.calls[-1][0] == "request_restore"
    rig.api._on_restore_done({"opened": 1, "placed": 1, "failed": [], "unrestorable": []})
    assert rig.app.toasts[-1][0] == "Restore finished"


def test_office_opener_registered_when_launcher_offers_openers(rig):
    rig.api._register_openers()
    assert ".xlsx" in rig.app.ctx.launcher.openers and ".csv" not in rig.app.ctx.launcher.openers
    rig.app.ctx.settings.open_office_via_com = False
    rig.api._register_openers()
    assert rig.app.ctx.launcher.openers == {}


def test_drive_down_from_watchers_roots(rig):
    roots = SimpleNamespace(rows=[{"rootName": "U:", "status": "offline"}])
    rig.app.watchers = SimpleNamespace(roots=roots)
    rig.api.startActivity(rig.act.id)
    rig.api._on_snapshot(M.Snapshot(rig.act.id, entries=[ent(r"U:\Lot 7\list.xlsx")]))
    assert rig.api.driveDown and rig.api.state == "needs"
    assert rig.api.live.rows[0]["status"] == "offline"


def test_resume_restores_what_was_saved_before_the_start(rig):
    rig.app.snapshots.save_live(M.Snapshot(rig.act.id, entries=[ent(r"U:\yesterday.pdf")]))
    rig.api.startActivity(rig.act.id)
    rig.app.snapshots.save_live(M.Snapshot(rig.act.id, entries=[ent(r"U:\today.pdf")]))   # the first pass
    rig.api.restoreLatest(rig.act.id)
    name, snap, _items = rig.engine.calls[-1]
    assert name == "request_restore" and [e.path for e in snap.entries] == [r"U:\yesterday.pdf"]
    rig.api.restoreLatest(rig.act.id)                    # once only; later calls use the live snapshot
    assert [e.path for e in rig.engine.calls[-1][1].entries] == [r"U:\today.pdf"]


def test_monitor_and_place_maths():
    from project_opener.quick.capture_api import monitor_and_place
    pl = M.WindowPlacement(1, [2400, 266, 3360, 806], [2400, 266, 3360, 806], r"\\.\DISPLAY1", [1920, -4, 3840, 1076])
    mon, place = monitor_and_place(pl, [r"\\.\DISPLAY2", r"\\.\DISPLAY1"])
    assert mon == "monitor 2"
    assert place == {"placeX": 0.25, "placeY": 0.25, "placeW": 0.5, "placeH": 0.5}
    maxed = M.WindowPlacement(3, [0, 0, 10, 10], [1912, -12, 3848, 1044], r"\\.\DISPLAY1", [1920, -4, 3840, 1076])
    assert monitor_and_place(maxed, [])[1] == {"placeX": 0.0, "placeY": 0.0, "placeW": 1.0, "placeH": 0.9778}
    assert monitor_and_place(None, []) == ("", {})
