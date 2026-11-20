"""Weekly Wrapped, the office board with its opt-out, the Office pulse and Handover (po4-team).

The counting is driven with fixed dates; the board and the handover run on two fake PCs (real ``AppContext``,
synchronous ``run_async``) sharing one temp hub folder, as in ``test_v4_hub_apis``.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from project_opener.core import models as M  # noqa: E402
from project_opener.core import wrapped as W  # noqa: E402
from project_opener.core.jsonio import append_jsonl  # noqa: E402
from project_opener.core.tasks import TaskStore  # noqa: E402
from project_opener.lan import teamboard as TB  # noqa: E402
from project_opener.lan.hub import TeamHub  # noqa: E402
from project_opener.quick.hub_api import HubApi  # noqa: E402
from project_opener.quick.tasks_api import TasksApi  # noqa: E402
from project_opener.quick.team_api import TeamApi  # noqa: E402
from project_opener.quick.watchers_api import WatchersApi  # noqa: E402
from project_opener.ui.context import AppContext  # noqa: E402

THU = date(2026, 11, 19)                 # a Thursday; its week runs Mon 16 .. Sun 22 Nov


def at(day: date, hh: int = 10) -> str:
    return datetime(day.year, day.month, day.day, hh, 0).astimezone().isoformat(timespec="seconds")


def launch(day: date, activity: bool = True) -> dict:
    row = {"ts": at(day), "project_id": "p1", "project": "", "count": 3, "ok": 3, "missing": 0}
    if activity:
        row.update(activity_id="a1", activity="Lot 7 check")
    return row


def closed(title: str, by: str, on: date, due: str = "") -> M.Task:
    t = M.Task(title, owner=by, due=due)
    t.done_at, t.done_by = at(on, 16), by
    return t


# ----------------------------------------------------------------- counting
def test_week_counts_from_history_and_tasks():
    mon = W.week_start(THU)
    assert mon == date(2026, 11, 16) and W.week_id(THU) == "2026-W47"
    history = [launch(date(2026, 11, 13)),                      # Fri before: streak only
               launch(mon), launch(mon), launch(mon + timedelta(days=1), activity=False),
               launch(mon + timedelta(days=2)), launch(THU)]
    tasks = [closed("A", "vikram", mon, due="2026-11-17"),      # on time
             closed("B", "vikram", THU, due="2026-11-18"),      # late
             closed("C", "vikram", THU),                        # no due date: not in the rate
             closed("D", "priya", THU, due="2026-11-30"),       # someone else's
             closed("E", "vikram", date(2026, 11, 12))]         # last week
    st = W.week_stats(history, tasks, "vikram", THU)
    assert st["activities_run"] == 4                            # the project launch is not an activity
    assert (st["tasks_closed"], st["tasks_with_due"], st["tasks_on_time"]) == (3, 2, 1)
    assert st["on_time_rate"] == 50
    assert st["day_streak"] == 5                                # Fri, (weekend), Mon..Thu
    assert st["squares"] == [True, True, True, True, False, False, False]
    assert st["windows_reopened"] is None                       # the restore-log hook is empty
    # no hours and no window titles anywhere in what is published
    assert not {k for k in st if "hour" in k or "title" in k}


def test_streak_rules():
    assert W.day_streak({THU}, THU) == 1
    assert W.day_streak({THU - timedelta(days=1)}, THU) == 1     # today not over yet: yesterday counts
    assert W.day_streak({THU - timedelta(days=2)}, THU) == 0     # a working day missed
    sat, sun, mon = date(2026, 11, 21), date(2026, 11, 22), date(2026, 11, 23)
    assert W.day_streak({THU, date(2026, 11, 20), mon}, mon) == 3     # a quiet weekend does not break it
    assert W.day_streak({date(2026, 11, 20), sat, sun, mon}, mon) == 4  # a worked weekend counts


def test_on_time_rate_is_none_without_due_dates():
    st = W.week_stats([], [closed("C", "vikram", THU)], "vikram", THU)
    assert st["tasks_closed"] == 1 and st["on_time_rate"] is None


def test_merge_two_pcs_of_one_person_and_rank():
    a = W.week_stats([launch(THU), launch(THU)], [closed("A", "v", THU, "2026-11-20")], "v", THU)
    b = W.week_stats([launch(THU - timedelta(days=1))], [closed("A", "v", THU, "2026-11-20")], "v", THU)
    m = W.merge_person([a, b], THU)
    assert m["activities_run"] == 3                             # launches add up across PCs
    assert m["tasks_closed"] == 1                               # hub tasks are counted once
    assert m["day_streak"] == 2                                 # Wed (PC b) + Thu (PC a)
    rows = W.rank([{"name": "B", "tasks_closed": 2, "activities_run": 1, "day_streak": 1},
                   {"name": "A", "tasks_closed": 2, "activities_run": 1, "day_streak": 1},
                   {"name": "C", "tasks_closed": 5, "activities_run": 0, "day_streak": 0}])
    assert [(r["name"], r["place"]) for r in rows] == [("C", 1), ("A", 2), ("B", 2)]
    assert [r["name"] for r in W.rank(rows, "activities")][0] in ("A", "B")


def test_the_space_post_says_only_the_counts():
    st = W.week_stats([launch(THU)], [], "vikram", THU)
    title, lines = W.post_lines("Vikram", st, place=2, of=5)
    assert title.startswith("Vikram's week (")
    assert "Activities run: 1" in lines and "On time: no due dates" in lines and "Office board: 2 of 5" in lines
    assert not any("Windows reopened" in x for x in lines)                       # not counted yet: not claimed


# -------------------------------------------------------------- two PCs
@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeApp(QObject):
    toast = Signal(str, str, str)

    def __init__(self, data_dir, hub_root, user, name):
        super().__init__()
        self.ctx = AppContext(data_dir)
        self.ctx.user = user
        self.ctx.settings.display_name = name
        self.ctx.settings.hub_path = str(hub_root)
        self.ctx.hub = TeamHub(hub_root, user, name)
        self.ctx.hub.host = f"PC-{user.upper()}"
        self.toasts: list[tuple[str, str, str]] = []
        self.toast.connect(lambda t, b, lv: self.toasts.append((t, b, lv)))
        self.hub = HubApi(self)
        self.tasks = TasksApi(self)
        self.watchers = WatchersApi(self)
        self.team = TeamApi(self)
        self.team.today_fn = lambda: THU
        self.capture = None
        self.ctx.hub.heartbeat()

    def run_async(self, fn, done=None, fail=None):
        try:
            r = fn()
        except Exception as exc:  # noqa: BLE001
            if fail:
                fail(exc)
                return
            raise
        if done:
            done(r)

    def run_on_gui(self, fn):
        fn()

    def open_link(self, kind, key):
        pass

    def sync(self):
        self.ctx.hub.heartbeat()
        self.ctx.peers = self.ctx.hub.peers()
        self.hub._force_refresh()
        self.tasks.refresh()
        self.team.refresh()

    def history(self, *rows):
        for r in rows:
            append_jsonl(self.ctx.store.history_path, r)


@pytest.fixture
def office(qapp, tmp_path, hub_root):
    vikram = FakeApp(tmp_path / "v", hub_root, "vikram", "Vikram")
    yokesh = FakeApp(tmp_path / "y", hub_root, "yokesh", "Yokesh")
    return vikram, yokesh, hub_root


def board(app):
    return {r["login"]: r for r in app.team.board.rows}


def test_board_is_shared_through_the_hub(office):
    vikram, yokesh, hub_root = office
    vikram.history(launch(THU), launch(THU), launch(THU - timedelta(days=1)))
    yokesh.history(launch(THU))
    TaskStore(hub_root / "tasks").save(closed("Back-check lot 7", "yokesh", THU, "2026-11-20"))
    vikram.sync()
    yokesh.sync()
    vikram.sync()
    rows = board(vikram)
    assert rows["vikram"]["activitiesRun"] == 3 and rows["vikram"]["isMe"]
    assert rows["yokesh"]["tasksClosed"] == 1 and rows["yokesh"]["onTimeText"] == "100 %"
    assert rows["yokesh"]["place"] == 1                          # sorted by tasks closed
    assert vikram.team.wrapped["place"] == 2 and vikram.team.wrapped["of"] == 2
    vikram.team.setBoardSort("activities")
    assert vikram.team.board.rows[0]["login"] == "vikram"
    # each PC writes only its own file
    files = sorted(p.relative_to(hub_root).as_posix() for p in (hub_root / "board").rglob("*.json"))
    assert files == ["board/vikram/PC-VIKRAM.json", "board/yokesh/PC-YOKESH.json"]


def test_opt_out_hides_me_from_the_board_but_not_from_my_wrapped(office):
    vikram, yokesh, hub_root = office
    vikram.history(launch(THU))
    yokesh.history(launch(THU), launch(THU))
    assert yokesh.ctx.settings.board_show_me is True              # on by default
    yokesh.ctx.settings.board_show_me = False
    yokesh.sync()
    vikram.sync()
    assert "yokesh" not in board(vikram) and "yokesh" not in board(yokesh)
    assert yokesh.team.wrapped["activitiesRun"] == 2              # still sees their own week
    assert yokesh.team.wrapped["place"] == 0
    data = json.loads((hub_root / "board" / "yokesh" / "PC-YOKESH.json").read_text(encoding="utf-8"))
    assert data["hidden"] is True and data["weeks"] == {}         # no numbers leave the PC
    # a second PC of the same person that has not opted out does not bring them back
    other = TB.TeamBoard(TeamHub(hub_root, "yokesh", "Yokesh"))
    other.hub.host = "PC-YOKESH-2"
    other.write_week(W.week_stats([launch(THU)], [], "yokesh", THU), hidden=False)
    vikram.sync()
    assert "yokesh" not in board(vikram)
    yokesh.ctx.settings.board_show_me = True
    yokesh.sync()
    vikram.sync()
    assert board(vikram)["yokesh"]["activitiesRun"] == 3          # both PCs' launches


def test_handover_round_trip(office):
    vikram, yokesh, hub_root = office
    store = vikram.ctx.store
    proj = store.add(M.Project("As-built isometrics", job_number="P12513"))
    act = store.add_activity(M.Activity("Lot 7 check", project_ids=[proj.id],
                                        items=[M.ActivityItem(path=r"D:\Projects\P12513\Line list.xlsx")]))
    ts = TaskStore(hub_root / "tasks")
    open_task = M.Task("Send rev C sheets to FST", owner="vikram", due="2026-11-24")
    other = M.Task("Priya's task", owner="priya")
    ts.save(open_task)
    ts.save(other)
    vikram.sync()
    yokesh.sync()
    assert [t["id"] for t in vikram.team.choices["tasks"]] == [open_task.id]

    why = vikram.team.startHandover("yokesh", "2026-11-19", "2026-11-27", [act.id], [open_task.id])
    assert why == ""
    vikram.sync()
    mine = vikram.team.handover
    assert mine["toName"] == "Yokesh" and mine["on"] and not mine["accepted"] and mine["taskCount"] == 1
    assert ts.get(open_task.id).owner == "vikram"                # nothing moves before it is accepted
    assert vikram.team.startHandover("yokesh", "2026-11-19", "2026-11-27", [act.id], []) .startswith("You already")

    # the colleague sees an inbox item and the office shows the leave
    yokesh.sync()
    entry = next(r for r in yokesh.hub.inbox.rows if r["kind"] == "handover")
    assert yokesh.team.incoming.rows[0]["stateText"] == "waiting for you"
    office_row = next(r for r in yokesh.team.office.rows if r["login"] == "vikram")
    assert office_row["presence"] == "leave" and office_row["leaveText"] == "on leave · handed to Yokesh"

    yokesh.hub.acceptInbox(entry["messageId"])
    copies = [a for a in yokesh.ctx.store.activities if a.origin.source == "handover"]
    assert [a.name for a in copies] == ["Lot 7 check"] and copies[0].origin.author == "vikram"
    assert ts.get(open_task.id).owner == "yokesh" and ts.get(other.id).owner == "priya"
    assert not any(r["kind"] == "handover" for r in yokesh.hub.inbox.rows)
    vikram.sync()
    assert vikram.team.handover["accepted"] and vikram.team.handover["movedCount"] == 1

    # back early: the task returns; the colleague's untouched copy goes
    vikram.team.endHandover("")
    assert ts.get(open_task.id).owner == "vikram"
    assert vikram.team.handover == {}
    yokesh.sync()
    assert not [a for a in yokesh.ctx.store.activities if a.origin.source == "handover"]
    assert yokesh.team.incoming.count() == 0
    office_row = next(r for r in yokesh.team.office.rows if r["login"] == "vikram")
    assert office_row["presence"] != "leave"


def test_handover_reverses_itself_after_the_end_date(office):
    vikram, yokesh, hub_root = office
    ts = TaskStore(hub_root / "tasks")
    task = M.Task("GAD comments to Cairn", owner="vikram")
    ts.save(task)
    vikram.sync()
    yokesh.sync()
    assert vikram.team.startHandover("yokesh", "2026-11-19", "2026-11-20", [], [task.id]) == ""
    yokesh.sync()
    hid = yokesh.team.incoming.rows[0]["handoverId"]
    yokesh.team.acceptHandover(hid)
    assert ts.get(task.id).owner == "yokesh"
    vikram.team.today_fn = lambda: date(2026, 11, 23)            # Monday: back from leave
    vikram.sync()
    assert ts.get(task.id).owner == "vikram"
    assert TB.TeamBoard(vikram.ctx.hub).get(hid)["state"] == "returned"


def test_handover_validation(office):
    vikram, _yokesh, _hub = office
    vikram.sync()
    t = vikram.team
    assert t.startHandover("", "2026-11-19", "2026-11-20", ["x"], []).startswith("Pick the colleague")
    assert t.startHandover("vikram", "2026-11-19", "2026-11-20", ["x"], []).startswith("Pick a colleague")
    assert t.startHandover("yokesh", "19/11", "2026-11-20", ["x"], []).startswith("Dates are")
    assert t.startHandover("yokesh", "2026-11-20", "2026-11-19", ["x"], []).startswith("The last day is before")
    assert t.startHandover("yokesh", "2026-11-01", "2026-11-02", ["x"], []).startswith("The last day has passed")
    assert t.startHandover("yokesh", "2026-11-19", "2026-11-20", [], []).startswith("Tick at least one")


def test_office_states(office):
    vikram, yokesh, hub_root = office
    yokesh.ctx.hub.current_activity = "Lot 7 check"
    yokesh.ctx.hub.heartbeat()
    priya = TeamHub(hub_root, "priya", "Priya")
    priya.heartbeat()
    priya.sign_off()
    ravi = TeamHub(hub_root, "ravi", "Ravi")
    ravi.heartbeat(current_activity="")
    vikram.ctx.peers = vikram.ctx.hub.peers()
    vikram.hub._force_refresh()
    vikram.team.refresh()
    states = {r["login"]: (r["presence"], r["doing"]) for r in vikram.team.office.rows}
    assert states == {"yokesh": ("active", "Lot 7 check"), "ravi": ("idle", ""), "priya": ("away", "")}
    assert [r["login"] for r in vikram.team.office.rows] == ["yokesh", "ravi", "priya"]
    assert vikram.team.officeCounts == {"active": 1, "idle": 1, "away": 1, "leave": 0}
