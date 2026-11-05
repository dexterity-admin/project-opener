"""Tasks: store, lifecycle across two users on one hub folder, due text."""
from __future__ import annotations

from datetime import date

from project_opener.core import models as M
from project_opener.core.tasks import TaskStore, due_text, is_overdue, sort_by_due, when_text
from project_opener.lan.hub import TeamHub


def test_due_text_wording():
    today = date(2026, 11, 5)          # a Thursday
    assert due_text("", today) == ""
    assert due_text("garbage", today) == ""
    assert due_text("2026-11-05", today) == "due today"
    assert due_text("2026-11-06", today) == "due tomorrow"
    assert due_text("2026-11-07", today) == "due Sat"
    assert due_text("2026-11-14", today) == "due 14 Nov"
    assert due_text("2027-01-02", today) == "due 2 Jan 2027"
    assert due_text("2026-11-04", today) == "1 day overdue"
    assert due_text("2026-11-03", today) == "2 days overdue"


def test_overdue_ignores_done_tasks():
    t = M.Task("x", due="2026-11-01")
    assert is_overdue(t, date(2026, 11, 5))
    t.mark_done("a")
    assert not is_overdue(t, date(2026, 11, 5))


def test_sort_due_soonest_first_no_due_last():
    a = M.Task("a", due="2026-11-10", created_at="2026-01-01T00:00:00+00:00")
    b = M.Task("b", due="", created_at="2026-01-01T00:00:00+00:00")
    c = M.Task("c", due="2026-11-06", created_at="2026-01-02T00:00:00+00:00")
    assert [t.title for t in sort_by_due([a, b, c])] == ["c", "a", "b"]


def test_store_roundtrip_corrupt_and_unsafe_ids(tmp_path):
    st = TaskStore(tmp_path / "tasks")
    t = M.Task("Back-check lot 7", owner="yokesh", due="2026-11-07")
    st.save(t)
    (tmp_path / "tasks" / "broken.json").write_text("{not json", encoding="utf-8")
    assert [x.title for x in st.all()] == ["Back-check lot 7"]
    assert st.get(t.id).owner == "yokesh"
    assert st.get("../../etc") is None
    assert st.remove("../x") is False
    bad = M.Task("bad", id="..\\evil")
    try:
        st.save(bad)
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("unsafe id accepted")
    assert st.remove(t.id) and st.get(t.id) is None


def test_lifecycle_two_users_one_hub(hub_root):
    vikram = TeamHub(hub_root, "vikram", "Vikram")
    yokesh = TeamHub(hub_root, "yokesh", "Yokesh")
    vikram.initialise()
    vikram.heartbeat()
    yokesh.heartbeat()
    tasks_v = TaskStore(vikram.sub("tasks"))
    tasks_y = TaskStore(yokesh.sub("tasks"))

    # Vikram creates and assigns; Yokesh is told through his inbox.
    link = M.TaskLink("activity", "act1", "pub1", "P12513 · Lot 7 check", "P12513")
    task = M.Task("Back-check lot 7", owner="yokesh", due="2026-11-07", created_by="vikram",
                  updated_by="vikram", link=link)
    tasks_v.save(task)
    assert vikram.send_mention(["yokesh"], "Vikram assigned you: Back-check lot 7", "projectopener://task/" + task.id,
                               kind="task", task_id=task.id, title=task.title) == 1
    mine = tasks_y.for_owner("yokesh")
    assert [t.id for t in mine] == [task.id]
    notes = yokesh.mentions()
    assert notes[0]["kind"] == "task" and notes[0]["task_id"] == task.id and notes[0]["from"] == "vikram"

    # Yokesh marks it done on his PC; Vikram reads the same file and sees who did it.
    t = tasks_y.get(task.id)
    t.mark_done("yokesh")
    tasks_y.save(t)
    seen = tasks_v.get(task.id)
    assert seen.done and seen.done_by == "yokesh" and seen.updated_by == "yokesh"
    assert tasks_v.for_owner("yokesh") == []
    assert [x.id for x in tasks_v.for_owner("yokesh", include_done=True)] == [task.id]
    assert [x.id for x in tasks_v.for_link("activity", published_id="pub1")] == [task.id]
    assert tasks_v.for_link("project", local_id="act1") == []


def test_adopt_local_moves_offline_tasks(tmp_path, hub_root):
    local = TaskStore(tmp_path / "local-tasks")
    t1, t2 = M.Task("offline one"), M.Task("offline two")
    local.save(t1)
    local.save(t2)
    hub = TaskStore(hub_root / "tasks")
    hub.save(M.Task("already there", id=t2.id))          # same id on the hub wins (not overwritten)
    assert hub.adopt_local(local.root) == 2
    assert local.all() == []
    titles = sorted(t.title for t in hub.all())
    assert titles == ["already there", "offline one"]
    assert hub.adopt_local(hub.root) == 0


def test_when_text_relative():
    from datetime import datetime, timedelta
    now = datetime(2026, 11, 5, 15, 0).astimezone()
    assert when_text((now - timedelta(seconds=20)).isoformat(), now) == "just now"
    assert when_text((now - timedelta(minutes=5)).isoformat(), now) == "5 min ago"
    assert when_text((now - timedelta(hours=3)).isoformat(), now) == "12:00"
    assert when_text("", now) == ""
