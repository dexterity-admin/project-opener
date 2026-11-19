"""Today v1 (docs/V4-PLUS-BRIEF.md section 5): ``app.today`` reads stored data only.  The pure rules (tasks due,
changed overnight, the day streak, the week's checkpoints, the hero) and the facade over a seeded store."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from project_opener.core import models as M  # noqa: E402
from project_opener.quick import today_api as TA  # noqa: E402

# Thursday 19 November 2026, 09:30 local
NOW = datetime(2026, 11, 19, 9, 30).astimezone()
TODAY = NOW.date()


def iso(d: datetime) -> str:
    return d.astimezone().isoformat(timespec="seconds")


def at(days_ago: int, hh: int, mm: int = 0) -> datetime:
    return (NOW - timedelta(days=days_ago)).replace(hour=hh, minute=mm, second=0, microsecond=0)


# ------------------------------------------------------------------ tasks
def task(owner: str, due: str = "", done: bool = False, by: str = "") -> M.Task:
    t = M.Task("t", owner, due, created_by=by or owner)
    if done:
        t.done_at = iso(NOW)
        t.done_by = owner
    return t


def test_task_stats_count_only_my_open_tasks():
    tasks = [task("me", "2026-11-19", by="ravi"), task("me", "2026-11-19", by="ravi"), task("me", "2026-11-19"),
             task("me", "2026-11-18"),                   # overdue
             task("me", "2026-11-22"),                   # Sunday: this week
             task("me", "2026-11-23"),                   # next week
             task("me"),                                 # no date
             task("me", "2026-11-19", done=True),        # done: not counted anywhere
             task("ravi", "2026-11-19")]                 # not mine
    s = TA.task_stats(tasks, "ME", TODAY, lambda u: {"ravi": "Ravi"}.get(u, u))
    assert (s["dueToday"], s["open"], s["overdue"], s["dueWeek"], s["noDate"]) == (3, 7, 1, 4, 1)
    assert s["fromNames"] == ["Ravi"] and s["weekEnd"] == "Sun 22 Nov"
    assert TA.tasks_line(s) == "from Ravi · 1 overdue"
    assert TA.tasks_line(TA.task_stats([], "me", TODAY)) == ""


# ------------------------------------------------------------ overnight
def alert(ts: datetime, event: str = "new", title: str = "New in Rev C: a.pdf", key: str = "w:new:a") -> dict:
    return {"watcher_id": "w", "event": event, "title": title, "ts": iso(ts), "key": key}


def test_changed_overnight_counts_files_since_six_yesterday():
    rows = [alert(at(1, 17, 59)),                                         # before 18:00 yesterday
            alert(at(1, 18, 5)), alert(at(1, 22, 0), "changed"), alert(at(0, 7, 10), "gone"),
            alert(at(0, 8, 0), title="12 new files in Revision C", key="w:new:*:abc123"),   # collapsed: 12
            alert(at(0, 8, 1), "down", title="nas01 down"),                # a health event: not a file
            alert(at(0, 8, 2), "task_assigned", title="3 tasks")]
    r = TA.changed_overnight(rows, NOW)
    assert r["count"] == 15
    assert len(r["spark"]) == 16 and sum(r["spark"]) == 15                # 18:00 .. 09:30, hourly
    assert r["spark"][0] == 1 and r["spark"][14] == 12
    assert TA.files_in({"key": "w:new:*:x", "title": "no count here"}) == 1


# --------------------------------------------------------------- streak
def test_day_streak_skips_quiet_weekends_only():
    thu = TODAY
    days = {thu - timedelta(days=n) for n in (0, 1, 2, 3, 6, 7)}          # Thu Wed Tue Mon, Fri Thu
    n, squares = TA.day_streak(days, thu)
    assert n == 6                                                          # Sat and Sun had no launch: no break
    assert len(squares) == TA.STREAK_SQUARES and squares[-1] is True and squares[-4] is True
    assert squares[-5] is False                                            # Sunday
    assert TA.day_streak(days - {thu}, thu)[0] == 5                        # not yet today: counts from yesterday
    assert TA.day_streak(days - {thu - timedelta(days=1)}, thu)[0] == 1    # a quiet Wednesday breaks it
    assert TA.day_streak(set(), thu) == (0, [False] * TA.STREAK_SQUARES)


# ---------------------------------------------------------- time travel
def cp(taken: datetime, n: int = 3) -> M.Checkpoint:
    snap = M.Snapshot("a", taken_at=iso(taken),
                      entries=[M.SnapshotEntry(f"path:{i}", status="identified", path=f"D:\\j\\{i}.pdf") for i in range(n)])
    return M.Checkpoint("a", snap, taken_at=iso(taken), kind="auto")


def test_week_ticks_keep_this_week_only_oldest_first():
    cps = [("a", "Lot 7 check", cp(at(0, 9, 5))), ("a", "Lot 7 check", cp(at(2, 16, 5), 7)),   # Thu, Tue
           ("b", "GAD review", cp(at(4, 17, 0)))]                                               # last Sunday
    ticks = TA.week_ticks(cps, NOW)
    assert [t["day"] for t in ticks] == [1, 3]
    assert ticks[0]["whenText"] == "Tue 16:05" and ticks[0]["windows"] == 7 and ticks[0]["minute"] == 16 * 60 + 5
    assert TA.week_days(NOW) == ["MON", "TUE", "WED", "THU"]


# ------------------------------------------------------------------ hero
def test_hero_shows_the_restorable_windows_else_the_items():
    act = M.Activity("Lot 7 check", items=[M.ActivityItem(path="D:\\j\\a.pdf"), M.ActivityItem(path="D:\\j\\b.xlsx")])
    act.last_opened = iso(at(1, 18, 42))
    snap = M.Snapshot(act.id, taken_at=iso(at(1, 18, 42)), entries=[
        M.SnapshotEntry("path:1", status="identified", path="D:\\j\\Register.xlsx", kind="file", app="Excel"),
        M.SnapshotEntry("path:2", status="identified", path="D:\\j\\IN", kind="folder", app="Explorer"),
        M.SnapshotEntry("win:x", status="unidentified", title="Untitled", app="Notepad")])
    h = TA.hero_fact(act, "last", snap, "P12513", now=NOW)
    assert h["label"] == "Opened yesterday 18:42 · Lot 7 check" and h["planText"] == "2 windows · 2 apps"
    assert [c["text"] for c in h["chips"]] == ["Register.xlsx", "IN"] and h["chips"][1]["glyph"] == "folder"
    assert h["fromText"] == "Opened 18:42" and h["line"] == "2 items · P12513"
    plan = TA.hero_fact(act, "resume", None, "", {"text": "the PC shut down", "takenIso": iso(at(0, 8, 1))}, NOW)
    assert plan["planKind"] == "items" and plan["planText"] == "2 items in launch order"
    assert plan["label"] == "Stopped today 08:01 · Lot 7 check" and plan["line"] == "the PC shut down"
    assert TA.hero_fact(None, "", None, "") == {}
    other = M.Activity("Other")
    assert TA.pick_last([other, act]) == (act, "last") and TA.pick_last([other]) == (other, "new")
    assert TA.pick_last([]) == (None, "")


def test_hero_park_says_when_where_and_the_note():
    act = M.Activity("Lot 7 check", items=[M.ActivityItem(path=r"D:\j\a.pdf")])
    snap = M.Snapshot(act.id, entries=[
        M.SnapshotEntry("path:1", status="identified", path=r"D:\j\Register.xlsx", kind="file", app="Excel"),
        M.SnapshotEntry("path:2", status="identified", path=r"D:\j\IN", kind="folder", app="Explorer")])
    park = {"activityId": act.id, "checkpointId": "cp1", "takenAt": iso(at(0, 8, 5)), "note": "halfway, sheet 4"}
    h = TA.hero_fact(act, "park", snap, "P12513", park, NOW)
    assert h["kind"] == "park" and h["label"] == "Parked today 08:05 · Lot 7 check"
    assert h["heading"] == "Pick up where you parked" and h["note"] == "halfway, sheet 4"
    assert h["line"] == "2 windows to reopen · P12513" and h["checkpointId"] == "cp1"
    assert h["planKind"] == "windows" and h["planCount"] == 2 and h["fromText"] == "Parked 08:05"
    assert TA.hero_fact(act, "last", snap, "", now=NOW)["note"] == ""


def test_the_latest_park_wins_unless_something_newer_happened():
    park = {"checkpointId": "cp1", "takenAt": iso(at(0, 8, 5))}
    assert TA.park_wins(park, iso(at(1, 18, 0)))                # opened yesterday, parked today: the park
    assert not TA.park_wins(park, iso(at(0, 9, 0)))             # opened again after parking: the last run
    assert TA.park_wins(park, None) and TA.park_wins(park, "")  # nothing else to compare: the park
    assert not TA.park_wins({}, None)                           # no park at all


# ---------------------------------------------------------------- facade
@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def pump_until(cond, seconds: float = 5.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def facade(qapp, isolated_data_dir):
    from project_opener.core.store import WorkspaceStore
    store = WorkspaceStore(isolated_data_dir)
    store.activities.clear()
    act = M.Activity("Lot 7 check", items=[M.ActivityItem(path=str(isolated_data_dir / "a.pdf"))])
    store.add_activity(act)
    store.save()
    from project_opener.quick.facade import AppFacade
    app = AppFacade(isolated_data_dir)
    app.ctx.launcher.dry_run = True
    app.activities.refresh()
    yield app, act.id
    app.deleteLater()
    pump_until(lambda: False, 0.02)


def test_facade_hero_week_and_streak_from_the_store(facade):
    app, aid = facade
    t = app.today
    t.refresh_hero()
    assert t.hero["activityId"] == aid and t.hero["kind"] == "new" and t.hero["planText"] == "1 item"
    now = datetime.now().astimezone()
    app.snapshots.add_checkpoint(M.Checkpoint(aid, M.Snapshot(aid, taken_at=iso(now)), taken_at=iso(now)))
    act = app.ctx.store.activity(aid)
    app.ctx.store.record_activity_launch(act, list(act.items), ok=1)
    t.refresh_week()
    t.refresh_days()
    assert pump_until(lambda: len(t.week) == 1 and t.stats.get("streak") == 1)
    assert t.week[0]["activityId"] == aid and t.weekDays[-1] == TA.DAY_WORDS[now.weekday()]
    assert t.stats["changed"] == -1                         # no folder watcher: the card says so, no zero
    assert t.stats["dueToday"] == 0 and t.stats["ready"]
    t.refresh_hero()
    assert t.hero["kind"] == "last" and t.hero["label"].startswith("Opened today ")


def test_facade_hero_parks_and_the_week_counts_reopened_windows(facade):
    app, aid = facade
    t = app.today
    now = datetime.now().astimezone()
    act = app.ctx.store.activity(aid)
    act.last_opened = iso(now - timedelta(minutes=10))
    entries = [M.SnapshotEntry(f"k{i}", status="identified", kind="file", path=rf"U:\job\{i}.pdf") for i in range(3)]
    app.snapshots.add_checkpoint(M.Checkpoint(aid, M.Snapshot(aid, entries=entries), taken_at=iso(now),
                                              kind="park", label="back after lunch"))
    app.snapshots.log_reopened(aid, "restore", 4)
    app.snapshots.log_reopened(aid, "launch", 2)
    t.start()                                               # wires memoryChanged to the hero and the stats
    app.capture.refreshMemory()
    h = t.hero
    assert h["kind"] == "park" and h["note"] == "back after lunch" and h["planCount"] == 3
    assert h["label"].startswith("Parked today ") and h["checkpointId"] == app.capture.latestPark["checkpointId"]
    assert (t.stats["reopened"], t.stats["restores"]) == (6, 1)
    act.last_opened = iso(now + timedelta(minutes=1))       # opened again after the park: the last run leads
    t.refresh_hero()
    assert t.hero["kind"] == "last"
    t.shutdown()


# ------------------------------------------------------------- the page
def test_today_keeps_the_dock_rules_and_finishes_its_arrival():
    """The hero grows into the dock: the guard's window, the settle into the activity page and Esc stay; the
    dock opening completes the arrival (never restarts a count-up)."""
    from pathlib import Path
    qml = Path(__file__).resolve().parents[1] / "project_opener" / "qml"
    home = (qml / "pages" / "HomePage.qml").read_text(encoding="utf-8")
    for s in ("app.ui.beginDockMeasure(); measure.restart()", "interval: Math.max(1, app.ui.dockMeasureMs)",
              "onTriggered: app.ui.endDockMeasure()", "interval: 1200", 'sequence: "Esc"',
              "cards[j].finishCount()", "docked: home.docked"):
        assert s in home, s
    assert "countUp(0)" not in home
    hero = (qml / "components" / "TodayHero.qml").read_text(encoding="utf-8")
    assert 'kind: "primary"' in hero and hero.count('kind: "primary"') == 1        # the one amber control
    assert "Behavior on height { NumberAnimation { duration: Math.round(420 * app.ui.k)" in hero
