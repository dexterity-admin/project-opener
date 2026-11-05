"""The polish round's owner decisions and fixes (5 November 2026).

* "Everything open, I untick": Save N new as items is a tick list; Ignore per row persists for the
  activity; "Always ignore this app" writes Settings.capture_ignore; ignored windows never count as new.
* "A tick list, items pre-ticked": the Resume sheet groups and restores only what stays ticked.
* The snapshot store serves reads from memory and writes in the background (dock frame times).
* The engine stamps Snapshot.session_start; the pill stays away while the dock is on screen; the
  quiet-time probe can run off the GUI thread.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_v4_capture_api import FakeApp, FakeEngine, ent, qapp  # noqa: E402,F401

from project_opener.capture import windows as W  # noqa: E402
from project_opener.capture.engine import CaptureEngine, EngineCallbacks, EngineConfig  # noqa: E402
from project_opener.core import models as M  # noqa: E402
from project_opener.core.snapshots import SnapshotStore  # noqa: E402
from project_opener.desktop import pill as P  # noqa: E402
from project_opener.desktop import quiet as Q  # noqa: E402
from project_opener.quick.capture_api import CaptureApi  # noqa: E402

START = "2026-11-05T10:00:00+00:00"
LATER = "2026-11-05T10:05:00+00:00"


def stamped(e: M.SnapshotEntry, when: str) -> M.SnapshotEntry:
    e.first_seen = when
    return e


def rig_for(store, data):
    act = M.Activity(name="Lot 7 check", items=[M.ActivityItem(path=r"U:\Lot 7\list.xlsx", id="i1")])
    store.add_activity(act)
    app = FakeApp(store, data)
    api = CaptureApi(app)
    api._engine = FakeEngine()
    return act, app, api


def live_snapshot(aid: str) -> M.Snapshot:
    item = stamped(ent(r"U:\Lot 7\list.xlsx"), START)
    item.item_id = "i1"
    return M.Snapshot(aid, session_start=START, entries=[
        item,
        stamped(ent(r"U:\Lot 7\new.pdf", process="pdfx.exe"), LATER),                 # opened since: ticked
        stamped(ent(r"U:\Old\before.xlsx", process="excel.exe"), START),              # already open: unticked
        stamped(ent(status="unidentified", title="Inbox - Outlook", process="outlook.exe",
                    exe=r"C:\Office\OUTLOOK.EXE"), LATER),                            # mail: unticked
        stamped(ent(status="unidentified", title="Calculator", process="calc.exe"), LATER),  # no exe: untickable
    ])


# ------------------------------------------------------------ pure helpers
def test_new_rows_groups_and_ticks():
    snap = live_snapshot("a")
    rows = W.new_rows(snap, [e for e in snap.entries if not e.item_id])
    got = [(W.entry_name(e), g, t) for e, g, t in rows]
    assert got == [("new.pdf", "since", True), ("before.xlsx", "before", False),
                   ("Inbox - Outlook", "other", False), ("Calculator", "other", False)]
    assert W.new_action(rows[2][0]) == "Adds Outlook itself as an application"
    assert W.new_action(rows[3][0]) == ""


def test_new_rows_without_a_recorded_start_tick_nothing():
    snap = live_snapshot("a")
    snap.session_start = ""                                   # an old snapshot: cannot tell, so no tick
    assert all(not t for _e, _g, t in W.new_rows(snap, snap.entries[1:]))


def test_resume_rows_groups_and_ticks():
    snap = live_snapshot("a")
    items = [M.ActivityItem(path=r"U:\Lot 7\list.xlsx", id="i1")]
    got = [(W.entry_name(e), g, t) for e, g, t in W.resume_rows(snap, items)]
    assert got == [("list.xlsx", "items", True), ("new.pdf", "during", True), ("before.xlsx", "other", False),
                   ("Inbox - Outlook", "other", False), ("Calculator", "other", False)]


# ------------------------------------------------------------ CaptureApi
def test_save_new_sheet_ticks_left_out_and_counts(store, isolated_data_dir, qapp):  # noqa: F811
    act, app, api = rig_for(store, isolated_data_dir)
    api.startActivity(act.id)
    api._on_snapshot(live_snapshot(act.id))
    assert api.newCount == 4                                  # every window that is not an item
    api.prepareSaveNew()
    rows = api.newCandidates.rows
    assert [(r["name"], r["ticked"], r["tickable"], r["group"]) for r in rows] == [
        ("new.pdf", True, True, "since"), ("before.xlsx", False, True, "before"),
        ("Inbox - Outlook", False, True, "other"), ("Calculator", False, False, "other")]
    api.setNewTicked(rows[3]["entryKey"], True)              # cannot be added: stays unticked
    assert not api.newCandidates.rows[3]["ticked"]
    assert api.saveTicked() == 1
    assert [i.path for i in store.activity(act.id).items] == [r"U:\Lot 7\list.xlsx", r"U:\Lot 7\new.pdf"]
    assert api.newCount == 0                                  # the unticked ones are left out ...
    assert api.openCount == 5                                 # ... but still listed as open
    assert len(app.snapshots.review(act.id)[1]) == 3          # and kept for the next run


def test_ignore_for_activity_persists_and_always_ignore_writes_the_setting(store, isolated_data_dir, qapp):  # noqa: F811
    act, app, api = rig_for(store, isolated_data_dir)
    api.startActivity(act.id)
    api._on_snapshot(live_snapshot(act.id))
    outlook = next(r for r in api.live.rows if r["name"] == "Inbox - Outlook")["entryKey"]
    api.ignoreForActivity(outlook)
    assert api.openCount == 4 and api.newCount == 3
    assert outlook not in [r["entryKey"] for r in api.live.rows]
    api.endActivity()
    api.startActivity(act.id)                                 # the next run of the activity
    api._on_snapshot(live_snapshot(act.id))
    assert api.openCount == 4
    api.unignoreForActivity(outlook)
    assert api.openCount == 5
    assert api.ignoreApp(outlook) == "Outlook"
    assert {"process": "outlook.exe"} in app.ctx.settings.capture_ignore
    assert api.openCount == 4
    api.unignoreApp(outlook)
    assert {"process": "outlook.exe"} not in app.ctx.settings.capture_ignore


def test_resume_tick_list_restores_only_the_ticked(store, isolated_data_dir, qapp):  # noqa: F811
    act, app, api = rig_for(store, isolated_data_dir)
    snap = live_snapshot(act.id)
    app.snapshots.save_live(snap)
    api.prepareResume(act.id)
    rows = api.resumeCandidates.rows
    assert [(r["name"], r["ticked"], r["tickable"]) for r in rows] == [
        ("list.xlsx", True, True), ("new.pdf", True, True), ("before.xlsx", False, True),
        ("Inbox - Outlook", False, False), ("Calculator", False, False)]
    assert rows[3]["note"] == "No file path: cannot be reopened"
    api.setResumeTicked(rows[1]["entryKey"], False)           # leave new.pdf closed
    api.setResumeTicked(rows[2]["entryKey"], True)            # reopen before.xlsx
    assert api.resume_prepared(act.id)
    api.startActivity(act.id)
    api.restoreTicked(act.id)
    restore = [c for c in api._engine.calls if c[0] == "request_restore"]
    assert [e.path for e in restore[0][1].entries] == [r"U:\Lot 7\list.xlsx", r"U:\Old\before.xlsx"]
    assert not api.resume_prepared(act.id)


def test_resume_with_nothing_captured_lists_the_items(store, isolated_data_dir, qapp):  # noqa: F811
    act, _app, api = rig_for(store, isolated_data_dir)
    api.prepareResume(act.id)
    assert [(r["entryKey"], r["ticked"], r["group"]) for r in api.resumeCandidates.rows] == [("item:i1", True, "items")]


# ------------------------------------------------------------ SnapshotStore
def test_store_reads_from_memory_and_writes_in_the_background(tmp_path):
    st = SnapshotStore(tmp_path, background=True)
    snap = live_snapshot("a1")
    gate = threading.Event()
    real = st._run_op

    def slow(key, op):                                        # a share that takes its time
        gate.wait(5)
        real(key, op)
    st._run_op = slow
    t = time.perf_counter()
    st.save_live(snap)
    st.add_checkpoint(M.Checkpoint("a1", snap, kind="manual"))
    st.mark_running(M.RunningMarker(activity_id="a1", pid=1))
    st.set_review("a1", ignored={"win:x|y"})
    assert len(st.checkpoints("a1")) == 1 and st.latest("a1").session_start == START
    assert st.review("a1")[0] == {"win:x|y"} and st.markers()[0].activity_id == "a1"
    assert time.perf_counter() - t < 1.0                      # nobody waited for the disk
    assert not (tmp_path / "running.json").exists()
    gate.set()
    assert st.flush(10)
    on_disk = json.loads((tmp_path / "snapshots" / "a1.json").read_text(encoding="utf-8"))
    assert on_disk["ignored"] == ["win:x|y"] and len(on_disk["checkpoints"]) == 1
    fresh = SnapshotStore(tmp_path)
    assert fresh.latest("a1").entries[1].path == r"U:\Lot 7\new.pdf" and fresh.markers()[0].pid == 1
    st.close()


def test_store_keeps_newest_content_under_concurrent_writes(tmp_path):
    st = SnapshotStore(tmp_path, background=True)

    def writer(n):
        for i in range(20):
            st.save_live(M.Snapshot("a1", taken_at=f"2026-11-05T10:{n:02d}:{i:02d}+00:00"))
    threads = [threading.Thread(target=writer, args=(n,)) for n in range(3)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert st.flush(10)
    last = st.live("a1").taken_at
    assert SnapshotStore(tmp_path).live("a1").taken_at == last
    st.close()


# ------------------------------------------------------------ engine, pill, quiet
def test_engine_stamps_the_session_start(tmp_path):
    windows = [[]]
    first = ent(r"U:\a.pdf")
    later = ent(r"U:\b.pdf")

    class Ident:
        ignore_rules: list = []

        def identify(self, wins, paths, full=False, apply_ignore=True):
            return [M.SnapshotEntry.from_dict(e.to_dict()) for e in wins]

        def items_changed(self):
            pass

    eng = CaptureEngine(SnapshotStore(tmp_path), EngineCallbacks(), EngineConfig(),
                        enumerate_fn=lambda _x: windows[0], monitors_fn=lambda: [],
                        identifier_factory=lambda _c: Ident(), com=False)
    eng.identifier = Ident()
    eng._handle(("run", "a1", []))
    windows[0] = [first]
    s1, _ms = eng._build()
    assert s1.session_start and s1.entries[0].first_seen == s1.session_start
    assert not s1.opened_since_start(s1.entries[0])
    time.sleep(1.1)                                           # stamps are whole seconds
    windows[0] = [first, later]
    s2, _ms = eng._build()
    assert s2.session_start == s1.session_start
    assert [s2.opened_since_start(e) for e in s2.entries] == [False, True]
    assert M.Snapshot.from_dict(s2.to_dict()).session_start == s1.session_start


def test_pill_stays_away_while_the_dock_is_on_screen():
    base = P.PillFacts(state="running", label="Lot 7", open_count=3)
    assert P.pill_view(base)["visible"]
    v = P.pill_view(P.PillFacts(state="running", label="Lot 7", open_count=3, docking=True))
    assert not v["visible"] and v["reason"] == "the dock is on screen"


def test_quiet_watcher_probes_off_the_gui_thread(qapp):  # noqa: F811
    seen_threads = []

    def probe():
        seen_threads.append(threading.current_thread() is threading.main_thread())
        return Q.QuietFacts(remote_session=True)
    w = Q.QuietWatcher(probe=probe, background=True)
    changes = []
    w.changed.connect(changes.append)
    w.start()
    deadline = time.monotonic() + 5
    while not changes and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    w.stop()
    assert seen_threads and seen_threads[0] is False
    assert changes[:1] == [True]


def test_pill_panel_text_pairs_pass_contrast():
    """Every text the panel draws, on the tokens it draws them on (both themes, the Stage's accent)."""
    from project_opener.quick.ui_state import tokens_for
    from project_opener.ui import theme
    for dark in (False, True):
        t = tokens_for(dark, theme.DEFAULT_ACCENT, "comfortable")
        pairs = [("text", "surface"), ("text_muted", "surface"), ("text", "surface_2"), ("text_muted", "surface_2"),
                 ("accent_fg", "accent"), ("pill_ok_ink", "pill_ok_bg"), ("pill_warn_ink", "pill_warn_bg"),
                 ("pill_bad_ink", "pill_bad_bg"), ("pill_neutral_ink", "pill_neutral_bg")]
        for fg, bg in pairs:
            assert theme.contrast(t[fg], t[bg]) >= 4.5, (dark, fg, bg, theme.contrast(t[fg], t[bg]))
        assert len(t["surface"]) == 7                                  # opaque #RRGGBB, no alpha
    qml = (Path(__file__).resolve().parents[1] / "project_opener" / "qml" / "desktop" / "PillPanel.qml").read_text(
        encoding="utf-8")
    assert "Qt.rgba" not in qml and "text_faint" not in qml
