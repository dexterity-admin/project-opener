"""Juror round 1 fixes owned by the lead (6 November 2026).

* 3.8: Project Opener's own windows are never captured: by pid, by this build's executable, and by a
  Qt-registered window class of ProjectOpener.exe (another copy or version of the app).
* T1: the Resume band hides once its activity runs again; its count is the snapshot's open count.
* U4: one capture-state word set.
* C4: a folder watcher's new files as one fact.
* U1: the workspace store's background writer (saves coalesce, history keeps order, quit is bounded).
"""
from __future__ import annotations

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_v4_quick_facade import facade, qapp, seeded  # noqa: E402,F401

from project_opener.capture import win32  # noqa: E402
from project_opener.core import models as M  # noqa: E402
from project_opener.core.store import WorkspaceStore  # noqa: E402
from project_opener.quick.watchers_api import new_files_fact  # noqa: E402
from project_opener.ui import text as T  # noqa: E402

OWN = os.path.normcase(r"C:\Users\x\AppData\Local\Programs\Project Opener\ProjectOpener.exe")


# ------------------------------------------------------------ 3.8 self-exclusion
def test_own_window_by_pid_exe_and_qt_class():
    me = {4242}
    assert win32.is_own_window(4242, r"C:\Python314\python.exe", "Qt673QWindowIcon", me, OWN)        # this process
    assert win32.is_own_window(17, OWN, "Chrome_WidgetWin_1", me, OWN)                                # this build
    # another copy or version of the app (an installed 3.2, a second instance): its Qt window is ours too
    assert win32.is_own_window(18, r"D:\Old\ProjectOpener.exe", "Qt673QWindowIcon", me, "")
    assert win32.is_own_window(18, r"D:\Old\PROJECTOPENER.EXE", "Qt6.8.1QWindowToolSaveBits", me, "")
    # not ours: another Qt application, or a non-Qt window of a process merely named like us
    assert not win32.is_own_window(19, r"C:\Tools\qtcreator.exe", "Qt673QWindowIcon", me, OWN)
    assert not win32.is_own_window(20, r"C:\x\ProjectOpener.exe", "#32770", me, "")
    assert not win32.is_own_window(21, r"C:\Office\EXCEL.EXE", "XLMAIN", me, OWN)
    assert win32.own_exe() == ""                              # from source: python.exe is not "ours"


def test_enumeration_drops_own_windows(monkeypatch):
    infos = {101: win32.WindowInfo(101, "Report.xlsx - Excel", "XLMAIN", 7, "EXCEL.EXE", r"C:\Office\EXCEL.EXE"),
             102: win32.WindowInfo(102, "Project Opener", "Qt673QWindowIcon", 8, "ProjectOpener.exe",
                                   r"C:\Programs\Project Opener\ProjectOpener.exe")}
    monkeypatch.setattr(win32, "capturable", lambda h: True)
    monkeypatch.setattr(win32, "window_pid", lambda h: infos[h].pid if h in infos else 0)
    monkeypatch.setattr(win32, "_info", lambda h, with_placement=True: infos[h])
    monkeypatch.setattr(win32, "_prune_proc_cache", lambda pids: None)

    class U:
        def EnumWindows(self, cb, _lp):  # noqa: N802
            for h in infos:
                cb(h, 0)
    monkeypatch.setattr(win32, "_user32", U())
    monkeypatch.setattr(win32, "_WNDENUMPROC", lambda f: f)
    got = win32.enumerate_windows(set())
    assert [w.title for w in got] == ["Report.xlsx - Excel"]


# ------------------------------------------------------------ U4 words
def test_capture_line_word_set():
    assert T.capture_line("watching", "", 12, 9) == "Capture on · watching · 12 things open · 9 identified"
    assert T.capture_line("watching") == "Capture on · watching"
    assert T.capture_line("off", "").endswith("nothing recorded yet")
    when = "2026-11-05T09:32:00+00:00"
    assert T.capture_line("off", when) == f"Capture off · last snapshot {T.clock(when)}"
    assert T.capture_line("paused", when).startswith("Capture paused · last snapshot")
    assert T.capture_line("idle", when).startswith("Capture on · last snapshot")


# ------------------------------------------------------------ T1 Resume band
def test_resume_band_counts_the_snapshot_and_hides_while_it_runs(facade, seeded, monkeypatch):  # noqa: F811
    aid = seeded["act"]
    entries = [M.SnapshotEntry(key=f"path:x{i}", status="identified" if i < 4 else "unidentified",
                               path=f"X:\\{i}.pdf" if i < 4 else "") for i in range(6)]
    facade.snapshots.add_checkpoint(M.Checkpoint(activity_id=aid, kind="manual",
                                                 snapshot=M.Snapshot(activity_id=aid, entries=entries)))
    facade.snapshots.mark_running(M.RunningMarker(activity_id=aid, pid=999_999))
    facade.activities._compute_resume()
    band = facade.activities.resume
    assert band["count"] == 6 and band["text"].startswith("6 things open at ")
    assert band["title"] == "Resume " + facade.ctx.store.activity(aid).name          # the name keeps its case
    monkeypatch.setattr(facade.activities, "_cap", lambda name, default=None: aid if name == "runningId" else default)
    facade.activities._compute_resume()
    assert facade.activities.resume == {}                    # it runs again: band and activity are one object


# ------------------------------------------------------------ C4 the watcher's figure
def test_new_files_fact_from_alerts():
    w = M.Watcher(name="Revision C", kind="folder", target=r"\\nas01\P\Rev C", activity_id="a1")
    other = M.Watcher(name="nas01", kind="health", target=r"\\nas01", activity_id="a1")
    rows = [
        {"watcher_id": w.id, "event": "new", "title": "2 new sheets in Revision C", "path": r"\\nas01\P\Rev C",
         "detail": "ISO-1043.pdf, ISO-1044.pdf", "ts": "2026-11-05T10:41:00+00:00", "key": "k1"},
        {"watcher_id": w.id, "event": "new", "title": "New in Revision C: ISO-1045.pdf",
         "path": r"\\nas01\P\Rev C\ISO-1045.pdf", "detail": "ISO-1045.pdf", "ts": "2026-11-05T10:50:00+00:00",
         "key": "k2", "read": True},
        {"watcher_id": other.id, "event": "down", "title": "nas01 is down", "path": r"\\nas01", "key": "k3"},
    ]
    fact = new_files_fact(rows, [w, other], "a1")
    assert fact["count"] == 2 and fact["text"] == "2 new sheets in Revision C" and fact["keys"] == ["k1"]
    assert fact["paths"] == [os.path.join(r"\\nas01\P\Rev C", "ISO-1043.pdf"), os.path.join(r"\\nas01\P\Rev C", "ISO-1044.pdf")]
    assert new_files_fact(rows, [w], "a1", is_item=lambda p: True) == {}           # already items
    assert new_files_fact(rows, [w], "other") == {}


# ------------------------------------------------------------ U1 background writes
def test_store_background_writer_coalesces_and_keeps_history_order(isolated_data_dir):
    st = WorkspaceStore(isolated_data_dir)
    st.write_in_background()
    gate = threading.Event()
    real = st._write_workspace
    calls = []

    def slow(data, backup):
        gate.wait(5)
        calls.append(len(data.get("projects", [])))
        real(data, backup)
    st._write_workspace = slow
    t = time.perf_counter()
    for i in range(5):
        st.add(M.Project(name=f"p{i}"))
    act = M.Activity(name="Lot 7")
    st.add_activity(act)
    st.record_activity_launch(act, [], ok=0)
    assert time.perf_counter() - t < 1.0                     # nobody waited for the disk
    gate.set()
    assert st.flush(10)
    assert len(calls) <= 3 and calls[-1] == 5                 # consecutive saves coalesced; the newest is on disk
    fresh = WorkspaceStore(isolated_data_dir)
    assert len(fresh.projects) == 5 and fresh.activity(act.id) is not None
    assert [h.get("activity") for h in fresh.history(10) if h.get("activity")] == ["Lot 7"]
    assert st.close_writer(2.0)
    st.add(M.Project(name="after"))                          # synchronous again
    assert len(WorkspaceStore(isolated_data_dir).projects) == 6


def test_store_close_is_bounded(isolated_data_dir):
    st = WorkspaceStore(isolated_data_dir)
    st.write_in_background()
    st._write_workspace = lambda data, backup: time.sleep(5)
    st.add(M.Project(name="slow"))
    t = time.perf_counter()
    assert st.close_writer(0.5) is False
    assert time.perf_counter() - t < 1.5
