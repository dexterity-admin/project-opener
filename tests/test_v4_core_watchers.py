"""Watcher engine: folder diff, health, hub and time watchers; exactly-once delivery."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from project_opener.core import models as M
from project_opener.core.pathvars import PathResolver
from project_opener.core.watchers import FolderState, HubEvents, WatcherEngine, diff_listing
from project_opener.lan.delivery import DeliveredLedger, Dispatcher
from project_opener.lan.hub import TeamHub

NOW = datetime(2026, 11, 5, 9, 40).astimezone()


def engine(tmp_path, variables=None):
    return WatcherEngine(tmp_path / "watch-state", PathResolver(variables or {}, drive_map={}))


def touch(path, text="x", mtime=None):
    path.write_text(text, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def test_diff_listing_pure():
    old = FolderState({"a": (1, 1.0), "b": (2, 2.0), "c": (3, 3.0)})
    new = FolderState({"a": (1, 1.0), "b": (2, 9.0), "d": (4, 4.0)})
    assert diff_listing(old, new) == (["d"], ["b"], ["c"])


def test_folder_new_changed_gone(tmp_path):
    folder = tmp_path / "Revision C"
    folder.mkdir()
    touch(folder / "ISO-001.pdf", mtime=1_000_000)
    touch(folder / "ISO-002.pdf", mtime=1_000_000)
    touch(folder / "notes.txt", mtime=1_000_000)
    w = M.Watcher("Rev C", kind="folder", target=str(folder), params={"pattern": "*.pdf"}, interval_s=10)
    eng = engine(tmp_path)
    assert eng.tick([w], NOW) == []                       # first listing only records
    touch(folder / "ISO-003.pdf", mtime=1_000_100)        # new
    touch(folder / "ISO-001.pdf", "changed", mtime=1_000_200)   # changed
    (folder / "ISO-002.pdf").unlink()                     # gone
    touch(folder / "ignored.txt")                         # not matching the pattern
    assert eng.tick([w], NOW + timedelta(seconds=5)) == []   # interval not up yet
    events = eng.tick([w], NOW + timedelta(seconds=11))
    got = sorted((e.event, os.path.basename(e.path)) for e in events)
    assert got == [("changed", "ISO-001.pdf"), ("gone", "ISO-002.pdf"), ("new", "ISO-003.pdf")]
    assert all(e.key.startswith(w.id + ":") for e in events)
    assert eng.tick([w], NOW + timedelta(seconds=30)) == []  # nothing new since


def test_folder_events_filter_recursion_and_collapse(tmp_path):
    folder = tmp_path / "drop"
    (folder / "sub").mkdir(parents=True)
    w = M.Watcher("drop", kind="folder", target=str(folder), events=["new"], params={"recursive": True})
    eng = engine(tmp_path)
    eng.tick([w], NOW)
    for i in range(8):
        touch(folder / "sub" / f"sheet-{i}.pdf")
    events = eng.tick([w], NOW + timedelta(minutes=2))
    assert len(events) == 1 and events[0].title == "8 new files in drop"
    assert "and 3 more" in events[0].detail


def test_unreachable_folder_is_silent_and_keeps_state(tmp_path):
    folder = tmp_path / "share"
    folder.mkdir()
    touch(folder / "a.pdf")
    w = M.Watcher("share", kind="folder", target=str(folder))
    eng = engine(tmp_path)
    eng.tick([w], NOW)
    os.rename(folder, tmp_path / "share-offline")          # the share goes away
    assert eng.tick([w], NOW + timedelta(minutes=2)) == []  # no flood of "gone"
    os.rename(tmp_path / "share-offline", folder)          # back, unchanged
    assert eng.tick([w], NOW + timedelta(minutes=4)) == []


def test_folder_target_with_variable(tmp_path):
    folder = tmp_path / "P12513"
    folder.mkdir()
    w = M.Watcher("v", kind="folder", target="{JOB}")
    eng = engine(tmp_path, {"{JOB}": str(folder)})
    eng.tick([w], NOW)
    touch(folder / "x.pdf")
    assert [e.event for e in eng.tick([w], NOW + timedelta(minutes=2))] == ["new"]
    unknown = M.Watcher("u", kind="folder", target="{NOPE}\\x")
    assert eng.tick([unknown], NOW) == []


def test_failing_watcher_does_not_stop_others(tmp_path, monkeypatch):
    eng = engine(tmp_path)
    bad = M.Watcher("bad", kind="folder", target=str(tmp_path))
    good = M.Watcher("good", kind="time", events=["reminder"], params={"at": "2026-11-05T09:00"})
    monkeypatch.setattr(eng, "poll_folder", lambda *a: 1 / 0)
    events = eng.tick([bad, good], NOW)
    assert [e.event for e in events] == ["reminder"]


def test_health_down_and_up(tmp_path):
    eng = engine(tmp_path)
    w = M.Watcher("nas", kind="health", target="\\\\nas01")
    assert eng.tick([w], NOW, roots={"\\\\nas01": "ok", "Z:": "ok"}) == []
    down = eng.tick([w], NOW + timedelta(minutes=1), roots={"\\\\nas01": "offline", "Z:": "missing"})
    assert [(e.event, e.path, e.level) for e in down] == [("down", "\\\\nas01", "critical")]
    assert eng.tick([w], NOW + timedelta(minutes=2), roots={"\\\\nas01": "offline"}) == []
    up = eng.tick([w], NOW + timedelta(minutes=3), roots={"\\\\nas01": "ok"})
    assert [e.event for e in up] == ["up"]


def test_hub_watcher_matches_target(tmp_path):
    eng = engine(tmp_path)
    w = M.Watcher("P12513", kind="hub", target="P12513")
    t = M.Task("Lot 7", owner="yokesh", link=M.TaskLink("activity", "a", "", "P12513 · Lot 7", "P12513"))
    t2 = M.Task("Other job", owner="yokesh")
    t.mark_done("yokesh")
    hub = HubEvents(published=[{"published_id": "p1", "title": "P12513 · Checking", "author": "rahul", "revision": 3},
                               {"published_id": "p2", "title": "DM-GAD", "author": "rahul", "revision": 1}],
                    tasks_done=[t, t2], mentions=[{"id": "m1", "from": "priya", "text": "see P12513 lot 7"}])
    events = eng.tick([w], NOW, hub=hub)
    assert sorted(e.event for e in events) == ["mention", "published", "task_done"]
    assert {e.key for e in events} == {f"{w.id}:published:p1:3", f"{w.id}:task_done:{t.id}:{t.done_at}",
                                       f"{w.id}:mention:m1"}


def test_time_due_stale_reminder(tmp_path):
    eng = engine(tmp_path)
    w = M.Watcher("me", kind="time", params={"stale_days": 30, "at": "2026-11-01T08:00", "every_days": 7,
                                             "text": "weekly back-up"})
    today = M.Task("today", owner="me", due="2026-11-05")
    late = M.Task("late", owner="me", due="2026-11-01")
    later = M.Task("later", owner="me", due="2026-11-20")
    old = M.Activity("Old job", last_opened=(NOW - timedelta(days=40)).isoformat())
    fresh = M.Activity("Fresh", last_opened=(NOW - timedelta(days=2)).isoformat())
    events = eng.tick([w], NOW, tasks=[today, late, later], activities=[old, fresh])
    titles = sorted(e.title for e in events)
    assert titles == ["Due today: today", "Old job not opened for 40 days", "Overdue: late", "me"]
    rem = next(e for e in events if e.event == "reminder")
    assert f"{w.id}:reminder:2026-11-01T08:00" in rem.key
    # a week later the next occurrence has a new key; the same day does not
    again = eng.tick([w], NOW + timedelta(hours=1), tasks=[], activities=[])
    assert next(e for e in again if e.event == "reminder").key == rem.key
    week = eng.tick([w], NOW + timedelta(days=7), tasks=[], activities=[])
    assert next(e for e in week if e.event == "reminder").key != rem.key


def test_delivery_exactly_once_across_ticks_and_pcs(tmp_path, hub_root):
    hub = TeamHub(hub_root, "vikram", "Vikram")
    hub.initialise()
    ledger_path = hub_root / "delivered" / "vikram.json"
    pc1 = Dispatcher(hub, DeliveredLedger(ledger_path), None, tmp_path / "pc1" / "alerts.jsonl")
    pc2 = Dispatcher(hub, DeliveredLedger(ledger_path), None, tmp_path / "pc2" / "alerts.jsonl")

    folder = tmp_path / "f"
    folder.mkdir()
    w = M.Watcher("f", kind="folder", target=str(folder))
    e1, e2 = engine(tmp_path / "e1"), engine(tmp_path / "e2")     # the same watcher on two PCs
    e1.tick([w], NOW)
    e2.tick([w], NOW)
    touch(folder / "new.pdf", mtime=1_000_000)
    ev1 = e1.tick([w], NOW + timedelta(minutes=2))
    ev2 = e2.tick([w], NOW + timedelta(minutes=2))
    assert [e.key for e in ev1] == [e.key for e in ev2]
    assert pc1.deliver(ev1[0], w.notify).new is True
    assert pc1.deliver(ev1[0], w.notify).new is False          # the same tick twice
    assert pc2.deliver(ev2[0], w.notify).new is False          # my other PC
    assert len(pc1.alerts()) == 1 and pc2.alerts() == []
    pc1.mark_read(ev1[0].key)
    assert pc1.alerts()[0]["read"] is True


def test_ledger_keeps_newest_2000(tmp_path):
    led = DeliveredLedger(tmp_path / "d.json")
    led.add_many([f"k{i}" for i in range(2100)])
    led.add("last")
    assert led.seen("last") and led.seen("k2099")
    import json
    assert len(json.loads((tmp_path / "d.json").read_text(encoding="utf-8"))["keys"]) == 2000


def test_delivery_mentions_reach_inboxes_and_pulse(tmp_path, hub_root):
    hub = TeamHub(hub_root, "vikram", "Vikram")
    hub.initialise()
    for u in ("vikram", "priya", "yokesh"):
        TeamHub(hub_root, u).heartbeat()
    from project_opener.lan.groups import GroupBook
    GroupBook(hub_root).save(M.Group("checkers", ["priya", "yokesh", "vikram"]))
    disp = Dispatcher(hub, DeliveredLedger(tmp_path / "d.json"), None, tmp_path / "alerts.jsonl")
    ev = M.WatchEvent("w1", "new", "New in Rev C: ISO-003.pdf", "ISO-003.pdf", key="w1:new:iso-003.pdf:1:1.0")
    d = disp.deliver(ev, M.Notify(mentions=["@checkers", "@nobody"]))
    assert sorted(d.inboxes) == ["priya", "yokesh"]
    assert TeamHub(hub_root, "priya").mentions()[0]["text"].startswith("New in Rev C")
    rows = hub.pulse_feed()
    assert rows[0]["kind"] == "watch" and rows[0]["mentions"] == ["checkers", "nobody"]
