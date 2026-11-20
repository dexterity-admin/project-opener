"""Workspace memory: the restore log, Park, checkpoint retention and the Time travel lanes.

Core (``SnapshotStore``), engine (automatic checkpoints), restorer (what was actually reopened) and the
``app.capture`` facade properties Today reads (weekReopened, weekRestores, latestPark, timeline)."""
from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from test_v4_capture_api import FakeApp, FakeEngine, ent, qapp  # noqa: E402,F401
from test_v4_capture_engine import Rig  # noqa: E402
from test_v4_quick_facade import facade, pump, seeded  # noqa: E402,F401

from project_opener import constants as C  # noqa: E402
from project_opener.capture.restore import RestoreReport, RestoreResult  # noqa: E402
from project_opener.core import models as M  # noqa: E402
from project_opener.core.settings import Settings  # noqa: E402
from project_opener.core.snapshots import SnapshotStore, thin_checkpoints  # noqa: E402
from project_opener.quick import capture_api as CA  # noqa: E402
from project_opener.quick.capture_api import CaptureApi  # noqa: E402


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def snap(aid: str = "act1", n: int = 2) -> M.Snapshot:
    return M.Snapshot(activity_id=aid, entries=[
        M.SnapshotEntry(key=f"k{i}", status="identified", kind="file", path=rf"U:\job\{i}.pdf") for i in range(n)]
        + [M.SnapshotEntry(key="u", status="unsaved", title="Drawing1")])


def cp(aid: str, when: datetime, kind: str = "manual", label: str = "") -> M.Checkpoint:
    return M.Checkpoint(activity_id=aid, snapshot=snap(aid), taken_at=iso(when), kind=kind, label=label)


# ------------------------------------------------------------------ retention
def test_thin_keeps_14_days_then_one_per_day_to_60():
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    rows = [{"id": "recent1", "taken_at": iso(now - timedelta(days=1))},
            {"id": "recent2", "taken_at": iso(now - timedelta(days=1, minutes=15))},
            {"id": "d20-late", "taken_at": iso(now - timedelta(days=20))},
            {"id": "d20-early", "taken_at": iso(now - timedelta(days=20, minutes=30))},
            {"id": "d30", "taken_at": iso(now - timedelta(days=30))},
            {"id": "old", "taken_at": iso(now - timedelta(days=61))},
            {"id": "unreadable", "taken_at": "not a time"}]
    kept = [r["id"] for r in thin_checkpoints(rows, now)]
    assert "recent1" in kept and "recent2" in kept               # everything within 14 days
    assert "d20-late" in kept and "d20-early" not in kept        # one per day after that: the newest
    assert "d30" in kept and "old" not in kept                   # nothing past 60 days
    assert "unreadable" in kept                                  # never judged, never dropped


def test_store_keeps_more_than_ten_recent_checkpoints(isolated_data_dir):
    ss = SnapshotStore(isolated_data_dir)
    now = datetime.now(UTC)
    for i in range(C.CHECKPOINTS_KEPT + 3):
        ss.add_checkpoint(cp("act1", now - timedelta(minutes=15 * i), label=str(i)))
    cps = ss.checkpoints("act1")
    assert len(cps) == C.CHECKPOINTS_KEPT + 3 and cps[0].label == "0"
    ss.add_checkpoint(cp("act1", now - timedelta(days=70), label="ancient"))
    assert all(c.label != "ancient" for c in ss.checkpoints("act1"))


def test_checkpoints_since_and_latest_park_across_activities(isolated_data_dir):
    ss = SnapshotStore(isolated_data_dir)
    now = datetime.now(UTC)
    ss.add_checkpoint(cp("a", now - timedelta(days=9)))
    ss.add_checkpoint(cp("a", now - timedelta(hours=3), "park", "Lot 7: 12 to 18 done"))
    ss.add_checkpoint(cp("b", now - timedelta(hours=1), "park", "GAD rev C next"))
    ss.add_checkpoint(cp("b", now - timedelta(minutes=5), "auto"))
    week = ss.checkpoints_since(["a", "b"], now - timedelta(days=7))
    assert [c.kind for c in week] == ["auto", "park", "park"]
    park = ss.latest_of_kind(["a", "b"], "park")
    assert park.activity_id == "b" and park.label == "GAD rev C next"
    assert ss.latest_of_kind(["a"], "park").label == "Lot 7: 12 to 18 done"
    assert ss.latest_of_kind(["a", "b"], "start") is None


def test_park_is_a_checkpoint_kind():
    c = M.Checkpoint.from_dict(cp("a", datetime.now(UTC), "park", "note").to_dict())
    assert c.kind == "park" and c.label == "note"
    assert M.Checkpoint.from_dict({**c.to_dict(), "kind": "bogus"}).kind == "manual"


# ------------------------------------------------------------------ restore log
def test_restore_log_counts_and_persists(isolated_data_dir):
    ss = SnapshotStore(isolated_data_dir)
    now = datetime.now(UTC)
    ss.log_reopened("a", "restore", 6, at=iso(now - timedelta(hours=2)))
    ss.log_reopened("a", "launch", 4, at=iso(now - timedelta(hours=1)))
    ss.log_reopened("b", "restore", -3)                          # never negative
    ss.log_reopened("b", "restore", 2, at=iso(now - timedelta(days=9)))
    assert ss.reopened_since(now - timedelta(days=1)) == (10, 2)
    again = SnapshotStore(isolated_data_dir)                     # on disk, read back
    assert again.reopened_since(now - timedelta(days=30)) == (12, 3)
    assert [e["source"] for e in again.restore_events(now - timedelta(days=1))] == ["restore", "launch", "restore"]
    assert C.RESTORE_LOG_FILE in os.listdir(isolated_data_dir)


def test_restore_log_drops_events_past_60_days(isolated_data_dir):
    ss = SnapshotStore(isolated_data_dir)
    now = datetime.now(UTC)
    ss.log_reopened("a", "restore", 5, at=iso(now - timedelta(days=C.RESTORE_LOG_DAYS + 1)))
    ss.log_reopened("a", "restore", 1)
    assert [e["reopened"] for e in ss.restore_events()] == [1]


def test_restore_report_counts_only_what_it_reopened():
    report = RestoreReport(results=[RestoreResult("a", "a.pdf", opened=True),
                                    RestoreResult("b", "b.xlsx", opened=True, already_open=True),
                                    RestoreResult("c", "c.dwg", opened=False)])
    d = report.to_dict()
    assert d["opened"] == 2 and d["reopened"] == 1 and d["failed"] == ["c.dwg"]


# ------------------------------------------------------------------ engine: automatic checkpoints
def test_start_checkpoint_then_auto_only_when_windows_changed(tmp_path):
    r = Rig(tmp_path)
    e = r.engine
    e._handle(("run", "act1", []))
    r.pass_()
    assert r.got["cp"] == []                                     # not in the first minute
    r.t = C.CHECKPOINT_START_AFTER_S
    r.pass_()
    assert [c.kind for c in r.got["cp"]] == ["start"]
    r.t += C.CHECKPOINT_AUTO_MIN_S + 1
    r.pass_()
    assert len(r.got["cp"]) == 1                                 # idle: nothing changed, nothing kept
    r.desk.append(r.desk[0].__class__(3, r"U:\b.pdf", "C", 7, "y.exe"))
    r.t += 3
    r.pass_()
    assert [c.kind for c in r.got["cp"]] == ["start", "auto"]   # changed, and 15 min since the last
    r.desk.pop()
    r.t += 60
    r.pass_()
    assert len(r.got["cp"]) == 2                                 # changed again, but within 15 min
    assert [c.kind for c in r.store.checkpoints("act1")] == ["auto", "start"]


def test_manual_and_park_reset_the_automatic_clock(tmp_path):
    r = Rig(tmp_path)
    r.engine._handle(("run", "act1", []))
    r.engine._handle(("snapshot", "park", "where I left off"))
    assert r.got["cp"][0].kind == "park" and r.got["cp"][0].label == "where I left off"
    r.t = C.CHECKPOINT_START_AFTER_S + 1
    r.pass_()
    assert len(r.got["cp"]) == 1                                 # the park stood in for the start one


def test_restore_done_names_the_activity(tmp_path):
    from test_v4_capture_restore import FakeDesktop  # the restorer's fake desktop
    r = Rig(tmp_path)
    r.engine._platform_factory = lambda ident, cfg: FakeDesktop([], {})
    r.engine._handle(("restore", M.Snapshot(activity_id="act9"), []))
    assert r.got["done"][0]["activityId"] == "act9" and r.got["done"][0]["reopened"] == 0


# ------------------------------------------------------------------ facade
@pytest.fixture
def rig(qapp, store, isolated_data_dir):  # noqa: F811
    act = M.Activity(name="Lot 7 check", items=[M.ActivityItem(path=r"U:\Lot 7\list.xlsx", id="i1")])
    other = M.Activity(name="Mangala GAD review")
    store.add_activity(act)
    store.add_activity(other)
    app = FakeApp(store, isolated_data_dir)
    api = CaptureApi(app)
    api._engine = FakeEngine()
    from types import SimpleNamespace
    return SimpleNamespace(app=app, api=api, act=act, other=other, engine=api._engine)


def test_week_start_is_monday_midnight_and_lane_hours():
    thu = datetime(2026, 11, 19, 15, 30).astimezone()
    ws = CA.week_start(thu)
    assert ws.weekday() == 0 and (ws.hour, ws.minute) == (0, 0) and ws.date().isoformat() == "2026-11-16"
    assert CA.lane_hours([]) == (8, 18)
    assert CA.lane_hours([7.5, 21.6]) == (7, 22)
    assert CA.day_label(thu, 0) == "Today" and CA.day_label(thu, 1) == "Yesterday"
    assert CA.day_label(datetime(2026, 11, 16), 3) == "Mon 16 Nov"


def test_restore_and_launch_fill_the_week_counts(rig):
    seen: list = []
    rig.api.memoryChanged.connect(lambda: seen.append(1))
    rig.api._on_restore_done({"opened": 5, "reopened": 3, "placed": 3, "failed": [], "unrestorable": [],
                              "activityId": rig.act.id})
    rig.api.note_reopened(rig.other.id, "launch", 4)
    rig.api._on_restore_done({"opened": 0, "placed": 0, "failed": [], "unrestorable": [], "seconds": 0})
    assert rig.api.weekReopened == 7 and rig.api.weekRestores == 1 and seen
    events = rig.app.snapshots.restore_events()
    assert [(e["activity_id"], e["source"], e["reopened"]) for e in events] == [
        (rig.act.id, "restore", 3), (rig.other.id, "launch", 4)]


def test_last_weeks_restores_are_not_this_weeks(rig):
    last_week = CA.week_start() - timedelta(hours=1)
    rig.app.snapshots.log_reopened(rig.act.id, "restore", 9, at=iso(last_week))
    rig.api.refreshMemory()
    assert (rig.api.weekReopened, rig.api.weekRestores) == (0, 0)


def test_park_asks_for_a_note_then_captures_it(rig):
    asked: list = []
    rig.api.parkRequested.connect(lambda: asked.append(1))
    rig.api.requestPark()
    assert not asked and rig.app.toasts[-1][1].startswith("No activity is running")
    assert rig.api.park("x") is False
    rig.api.startActivity(rig.act.id)
    rig.api.requestPark()
    assert asked == [1]
    assert rig.api.park("  Lot 7:\n sheets 12 to 18 done  ") is True
    assert ("request_snapshot", "park", "Lot 7: sheets 12 to 18 done") in rig.engine.calls


def test_latest_park_reaches_the_facade(rig):
    rig.api.startActivity(rig.act.id)
    assert rig.api.latestPark == {}
    park = cp(rig.act.id, datetime.now(UTC) - timedelta(minutes=2), "park", "19 next")
    rig.app.snapshots.add_checkpoint(park)
    rig.api._on_checkpoint(park)
    lp = rig.api.latestPark
    assert lp["activityId"] == rig.act.id and lp["activityName"] == "Lot 7 check" and lp["note"] == "19 next"
    assert lp["checkpointId"] == park.id and lp["windows"] == 3 and lp["restorable"] == 2 and lp["takenText"]
    assert rig.app.toasts[-1][0] == "Parked"


def test_automatic_checkpoints_do_not_say_saved(rig):
    saved: list = []
    rig.api.checkpointSaved.connect(lambda *a: saved.append(a))
    rig.api.startActivity(rig.act.id)
    auto = cp(rig.act.id, datetime.now(UTC), "auto")
    rig.app.snapshots.add_checkpoint(auto)
    rig.api._on_checkpoint(auto)
    assert saved == [] and rig.api.state != "saved"
    manual = cp(rig.act.id, datetime.now(UTC), "manual")
    rig.api._on_checkpoint(manual)
    assert len(saved) == 1


def test_timeline_has_a_lane_per_day_and_a_tick_per_checkpoint(rig):
    now = datetime.now().astimezone()
    today_10 = now.replace(hour=10, minute=0, second=0, microsecond=0)
    if today_10 > now:                                           # before 10:00 today: use earlier slots
        today_10 = now - timedelta(minutes=1)
    two_days = today_10 - timedelta(days=2)
    snaps = rig.app.snapshots
    snaps.add_checkpoint(cp(rig.act.id, today_10, "start"))
    snaps.add_checkpoint(cp(rig.other.id, two_days, "park", "rev C next"))
    snaps.add_checkpoint(cp(rig.other.id, now - timedelta(days=8)))           # outside the week
    rig.api.refreshMemory()
    info = rig.api.timelineInfo
    assert info["total"] == 2 and len(info["days"]) == CA.TIMELINE_DAYS
    assert [d["count"] for d in info["days"]][:3] == [1, 0, 1] and info["days"][0]["label"] == "Today"
    rows = rig.api.timeline.rows
    assert [r["day"] for r in rows] == [0, 2]
    assert rows[0]["activityName"] == "Lot 7 check" and rows[0]["kindWord"] == "When it started"
    assert rows[1]["note"] == "rev C next" and rows[1]["count"] == 3 and rows[1]["restorable"] == 2
    lo, hi = info["startHour"], info["endHour"]
    h = today_10.hour + today_10.minute / 60 + today_10.second / 3600    # before 10:00 the slot keeps its seconds
    assert rows[0]["pos"] == pytest.approx((h - lo) / (hi - lo), abs=1e-3)
    assert all(0.0 <= r["pos"] <= 1.0 for r in rows)


def test_activity_page_lists_the_newest_ten(rig):
    now = datetime.now(UTC)
    for i in range(C.CHECKPOINTS_KEPT + 4):
        rig.app.snapshots.add_checkpoint(cp(rig.act.id, now - timedelta(minutes=20 * i)))
    rig.api.selectActivity(rig.act.id)
    assert rig.api.checkpoints.rowCount() == C.CHECKPOINTS_KEPT


# ------------------------------------------------------------------ launch -> restore log (real facade)
def test_a_dry_run_launch_logs_nothing(facade, seeded):  # noqa: F811
    """The smoke and --bench launch in dry run: nothing is opened, so nothing may be counted."""
    api = facade.activities
    done: list = []
    api.launchFinished.connect(lambda aid, s: done.append(aid))
    api.open(seeded["act"])
    deadline = time.monotonic() + 10
    while not done and time.monotonic() < deadline:
        pump(30)
    assert done == [seeded["act"]]
    assert facade.snapshots.restore_events() == [] and facade.capture.weekReopened == 0


def test_a_finished_launch_logs_what_it_opened(facade, seeded):  # noqa: F811
    from PySide6.QtCore import QObject, Signal

    class Run(QObject):                       # what ctx.launch_activity returns, driven by hand
        item_started = Signal(int)
        item_finished = Signal(int, object)
        finished = Signal(object)

        def __init__(self, n):
            super().__init__()
            self.items, self.elapsed, self.sheet_shown = [None] * n, 0.4, False

    from types import SimpleNamespace
    facade.ctx.launcher.dry_run = False
    api = facade.activities
    act = facade.ctx.store.activity(seeded["act"])
    api._begin_dock(act.id, act.name, "", "", "", act.enabled_items)
    run = Run(3)
    api._attach_run(run, act.id)
    for i, code in enumerate(("opened", "missing", "opened")):
        run.item_finished.emit(i, SimpleNamespace(code=code, status=code, message="", resolved=""))
    run.finished.emit(None)
    events = facade.snapshots.restore_events()
    assert [(e["source"], e["activity_id"], e["reopened"]) for e in events] == [("launch", act.id, 2)]
    assert facade.capture.weekReopened == 2 and facade.capture.weekRestores == 0


# ------------------------------------------------------------------ hotkeys
def test_park_hotkey_and_the_panel_key_moves_off_ctrl_alt_p(isolated_data_dir):
    assert C.HOTKEY_DEFAULTS["park"] == "Ctrl+Alt+P" and "park" in C.HOTKEY_IDS
    assert len(set(C.HOTKEY_DEFAULTS.values())) == len(C.HOTKEY_DEFAULTS)       # no two actions share a key
    s = Settings.load(isolated_data_dir)
    s.hotkeys = {"snapshot": "Ctrl+Alt+S", "panel": "Ctrl+Alt+P"}                # saved by 4.0 before Park
    s.save()
    again = Settings.load(isolated_data_dir)
    assert again.hotkeys["park"] == "Ctrl+Alt+P" and again.hotkeys["panel"] == C.HOTKEY_DEFAULTS["panel"]
    again.hotkeys = {"panel": "Ctrl+Shift+F9"}                                    # a key the person chose stays
    again.save()
    assert Settings.load(isolated_data_dir).hotkeys["panel"] == "Ctrl+Shift+F9"
