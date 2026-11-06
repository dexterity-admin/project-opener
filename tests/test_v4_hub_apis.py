"""app.hub / app.tasks / app.watchers wired to the core, two simulated users on one hub folder.

The facade is replaced by a small fake (real 3.2 ``AppContext``, synchronous ``run_async``)
so the tests do not depend on the other builders' sub-APIs.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from project_opener.core import models as M  # noqa: E402
from project_opener.lan.hub import TeamHub  # noqa: E402
from project_opener.quick.hub_api import HubApi  # noqa: E402
from project_opener.quick.tasks_api import TasksApi  # noqa: E402
from project_opener.quick.watchers_api import WatchersApi  # noqa: E402
from project_opener.ui.context import AppContext  # noqa: E402


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
        self.ctx.settings.hub_path = str(hub_root) if hub_root else ""
        self.ctx.hub = TeamHub(hub_root, user, name) if hub_root else TeamHub(None, user, name)
        self.toasts: list[tuple[str, str, str]] = []
        self.links: list[tuple[str, str]] = []
        self.toast.connect(lambda t, b, lv: self.toasts.append((t, b, lv)))
        self.hub = HubApi(self)
        self.tasks = TasksApi(self)
        self.watchers = WatchersApi(self)
        self.capture = None
        if hub_root:
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
        self.links.append((kind, key))

    def sync(self):
        """Refresh everything now (as the timers would)."""
        self.ctx.peers = self.ctx.hub.peers()
        self.hub._force_refresh()
        self.tasks.refresh()


@pytest.fixture
def office(qapp, tmp_path, hub_root):
    vikram = FakeApp(tmp_path / "v", hub_root, "vikram", "Vikram")
    yokesh = FakeApp(tmp_path / "y", hub_root, "yokesh", "Yokesh")
    priya = FakeApp(tmp_path / "p", hub_root, "priya", "Priya")
    for a in (vikram, yokesh, priya):
        a.sync()
    return vikram, yokesh, priya


def test_task_lifecycle_across_two_users(office):
    vikram, yokesh, priya = office
    proj = vikram.ctx.store.add(M.Project("Lot 7", job_number="P12513"))
    act = vikram.ctx.store.add_activity(M.Activity("Lot 7 check", project_ids=[proj.id]))
    tid = vikram.tasks.create("Back-check lot 7 with @priya", "@Yokesh", "2026-11-07", "activity", act.id)
    assert tid and vikram.tasks.all.count() == 1 and vikram.tasks.openCount == 1
    assert vikram.tasks.lineFor("activity", act.id).startswith("Task: Back-check lot 7 with @priya, ")
    assert vikram.tasks.mine.count() == 0                        # assigned to Yokesh, not me

    mentioned: list[tuple[str, str, str]] = []
    yokesh.hub.mentioned.connect(lambda f, t, link: mentioned.append((f, t, link)))
    yokesh.sync()
    row = yokesh.tasks.mine.get(0)
    assert row["taskId"] == tid and row["ownerName"] == "Yokesh" and row["createdByName"] == "Vikram"
    assert row["attachTitle"] == "P12513 · Lot 7 check" and row["jobNumber"] == "P12513"
    assert yokesh.tasks.mineOpenCount == 1
    assert yokesh.hub.mentionCount == 1 and yokesh.hub.inbox.get(0)["kind"] == "task"
    assert mentioned and mentioned[0][0] == "vikram" and mentioned[0][2] == f"projectopener://task/{tid}"
    yokesh.sync()
    assert len(mentioned) == 1                                   # toasted once only
    priya.sync()
    assert priya.hub.inbox.get(0)["kind"] == "mention"           # @priya in the title

    done: list[tuple[str, str]] = []
    vikram.tasks.taskDone.connect(lambda i, by: done.append((i, by)))
    yokesh.tasks.setDone(tid, True)
    assert yokesh.tasks.mine.count() == 0
    vikram.sync()
    r = vikram.tasks.all.get(0)
    assert r["done"] and r["doneBy"] == "Yokesh" and r["doneAt"]       # display text (V4-SEAMS builder 4 ask 6)
    assert done == [(tid, "yokesh")]
    assert vikram.tasks.lineFor("activity", act.id) == ""
    vikram.hub._force_refresh()
    assert any(x["kind"] == "task" and "finished" in x["message"] for x in vikram.hub.inbox.rows)
    pulses = [p["detail"] for p in vikram.hub.pulse.rows]
    assert "finished Back-check lot 7 with @priya" in pulses


def test_task_edit_group_by_and_remove(office):
    vikram, yokesh, _ = office
    a = vikram.tasks.create("A", "", "2026-11-20", "", "")
    b = vikram.tasks.create("B", "vikram", "2026-11-06", "", "")
    assert [r["title"] for r in vikram.tasks.mine.rows] == ["B"]
    vikram.tasks.edit(a, {"owner": "vikram", "due": "2026-11-05", "note": "first"})
    assert [r["title"] for r in vikram.tasks.mine.rows] == ["A", "B"]
    vikram.tasks.setGroupBy("job")
    assert vikram.tasks.groupBy == "job"
    vikram.tasks.remove(b)
    vikram.tasks.refresh()
    assert [r["taskId"] for r in vikram.tasks.all.rows] == [a]


def test_tasks_without_a_hub_stay_local_then_move(qapp, tmp_path, hub_root):
    solo = FakeApp(tmp_path / "solo", None, "vikram", "Vikram")
    solo.tasks.refresh()
    tid = solo.tasks.create("Offline task", "vikram", "", "", "")
    assert (tmp_path / "solo" / "tasks" / f"{tid}.json").exists()
    solo.ctx.hub = TeamHub(hub_root, "vikram", "Vikram")       # a hub is configured later
    solo.tasks.refresh()
    assert (hub_root / "tasks" / f"{tid}.json").exists()
    assert not (tmp_path / "solo" / "tasks" / f"{tid}.json").exists()
    assert any("moved to the Team Hub" in t[0] for t in solo.toasts)


def test_publish_activity_for_group_accept_maps_job(office):
    vikram, yokesh, priya = office
    vikram.hub.saveGroup("Checkers", ["yokesh", "priya"], "#10B981")
    assert [r["groupName"] for r in vikram.hub.groups.rows] == ["checkers"]
    proj = vikram.ctx.store.add(M.Project("Lot 7", job_number="P12513", items=[M.Item("C:\\iso.pdf", id="it1")]))
    act = vikram.ctx.store.add_activity(M.Activity("Lot 7 check", project_ids=[proj.id], items=[
        M.ActivityItem("C:\\iso.pdf", project_id=proj.id, source_item_id="it1"),
        M.ActivityItem("C:\\captured.txt")]))
    vikram.hub.publishActivity(act.id, "Rev C for @rahul", ["@checkers"])
    assert vikram.ctx.store.activity(act.id).origin.published_id
    assert any(t[0] == "Published Lot 7 check" for t in vikram.toasts)
    assert vikram.hub.published.get(0)["type"] == "activity" and vikram.hub.published.get(0)["isMine"]
    assert vikram.hub.register.get(0)["job"] == "P12513 · Lot 7 check"        # the activity's title (T2-3)

    # Yokesh holds the same job under another id: the link is kept by job number
    mine = yokesh.ctx.store.add(M.Project("P12513 local", job_number="P12513",
                                          items=[M.Item("C:\\iso.pdf", id="other")]))
    yokesh.sync()
    entry = next(r for r in yokesh.hub.inbox.rows if r["kind"] == "activity")
    assert entry["title"] == "Lot 7 check" and entry["senderName"] == "Vikram"
    yokesh.hub.acceptInbox(entry["messageId"])
    got = yokesh.ctx.store.activity_by_name("Lot 7 check")
    assert got.project_ids == [mine.id] and got.origin.source == "team"
    assert [(i.project_id, i.source_item_id) for i in got.items] == [(mine.id, "other"), ("", "")]
    assert yokesh.hub.inbox.indexOf(entry["messageId"]) < 0

    # Priya clones it from the published list instead
    priya.sync()
    pid = priya.hub.published.get(0)["publishedId"]
    new_id = priya.hub.clonePublished(pid)
    assert priya.ctx.store.activity(new_id).project_ids == []      # she has no P12513 project: no guessed link
    priya.hub._force_refresh()
    assert priya.hub.published.get(0)["cloned"] is True


def test_mention_picker_and_group_from_project(office):
    vikram, yokesh, priya = office
    vikram.hub.saveGroup("checkers", ["yokesh"], "")
    vikram.hub.setMentionQuery("yo")
    assert [r["login"] for r in vikram.hub.mentionCandidates.rows] == ["yokesh"]
    vikram.hub.setMentionQuery("")
    logins = {r["login"]: r["isGroup"] for r in vikram.hub.mentionCandidates.rows}
    assert logins["checkers"] is True and logins["priya"] is False
    assert vikram.hub.mentionAt("hi @yo", 6) == {"start": 3, "query": "yo"}
    assert vikram.hub.insertMention("hi @yo", 6, "yokesh") == {"text": "hi @yokesh ", "cursor": 11}

    proj = vikram.ctx.store.add(M.Project("Lot 7", job_number="P12513"))
    yokesh.ctx.hub.pulse("launched", "P12513 · Lot 7 check")     # evidence that Yokesh holds the job
    name = vikram.hub.groupFromProject(proj.id)
    assert name == "p12513-team"
    vikram.hub._force_refresh()
    row = vikram.hub.groups.get(vikram.hub.groups.indexOf("p12513-team"))
    assert row["members"] == ["vikram", "yokesh"]
    vikram.hub.deleteGroup("p12513-team")
    assert vikram.hub.groups.indexOf("p12513-team") < 0


def test_announce_send_dismiss(office):
    vikram, yokesh, priya = office
    vikram.hub.announce("Server move", "@yokesh nas01 off at 6", "warning", "")
    assert vikram.hub.announcements.get(0)["mine"] is True
    yokesh.sync()
    assert yokesh.hub.announcements.get(0)["authorName"] == "Vikram"
    note = next(r for r in yokesh.hub.inbox.rows if r["kind"] == "mention")
    yokesh.hub.dismissInbox(note["messageId"])
    yokesh.sync()
    assert all(r["messageId"] != note["messageId"] for r in yokesh.hub.inbox.rows)

    proj = vikram.ctx.store.add(M.Project("DM-GAD"))
    vikram.hub.send("project", proj.id, ["priya", "ghost"], "for you")
    priya.sync()
    sent = next(r for r in priya.hub.inbox.rows if r["kind"] == "project")
    assert sent["title"] == "DM-GAD" and sent["message"] == "for you"
    assert ("Vikram sent you DM-GAD", "for you", "info") in priya.toasts
    priya.hub.acceptInbox(sent["messageId"])
    assert priya.ctx.store.by_name("DM-GAD") is not None


def test_folder_watcher_alert_once_and_mark_read(office, tmp_path):
    vikram, _, _ = office
    folder = tmp_path / "RevC"
    folder.mkdir()
    wid = vikram.watchers.create("folder", str(folder), ["new"], {"intervalS": 10},
                                 {"toast": True, "mentions": ["@yokesh"], "cliqDm": False})
    row = vikram.watchers.watchers.get(0)
    assert row["watcherId"] == wid and row["notifyText"] == "Toast · @yokesh" and row["name"] == "Watch RevC"
    alerts: list[tuple] = []
    vikram.watchers.alert.connect(lambda *a: alerts.append(a))
    vikram.watchers.tick()                               # first listing records only
    (folder / "ISO-003.pdf").write_text("x", encoding="utf-8")
    vikram.watchers.engine()._last_run.clear()
    vikram.watchers.tick()
    assert len(alerts) == 1 and alerts[0][0] == "New in RevC: ISO-003.pdf"
    assert vikram.watchers.unreadCount == 1
    vikram.watchers.engine()._last_run.clear()
    vikram.watchers.tick()
    assert len(alerts) == 1
    key = vikram.watchers.alerts.get(0)["alertKey"]
    vikram.watchers.markRead(key)
    assert vikram.watchers.unreadCount == 0
    vikram.watchers.setEnabled(wid, False)
    assert vikram.watchers.watchers.get(0)["watcherEnabled"] is False
    vikram.watchers.edit(wid, {"name": "Rev C sheets", "notify": {"toast": False}})
    assert vikram.watchers.watchers.get(0)["notifyText"] == "Alert list only"
    vikram.watchers.remove(wid)
    assert vikram.watchers.watchers.count() == 0


def test_hub_watcher_sees_task_assigned(office):
    vikram, yokesh, _ = office
    yokesh.watchers.create("hub", "", ["task_assigned"], {}, {"toast": True})
    yokesh.watchers.tick()
    vikram.tasks.create("Check lot 8", "yokesh", "", "", "")
    yokesh.sync()
    alerts: list[tuple] = []
    yokesh.watchers.alert.connect(lambda *a: alerts.append(a))
    yokesh.watchers.tick()
    assert [a[0] for a in alerts] == ["Task for yokesh: Check lot 8"]


def test_time_watcher_due_today(office):
    vikram, _, _ = office
    today = datetime.now().date().isoformat()
    vikram.tasks.create("Submit lot 7", "vikram", today, "", "")
    vikram.watchers.create("time", "", ["due"], {}, {"toast": True})
    vikram.watchers.tick()
    assert vikram.watchers.alerts.get(0)["title"] == "Due today: Submit lot 7"


def test_root_rows_merge_office_view(office):
    from project_opener.core.health import RootHealth
    from project_opener.lan.healthboard import OfficeRoot
    vikram, _, _ = office
    t0 = (datetime.now().astimezone() - timedelta(minutes=30)).isoformat(timespec="seconds")
    local = [RootHealth("\\\\nas01", "ok", ["p1"], 4, {"Z:": "\\\\nas01\\Project"})]
    office_rows = [OfficeRoot("\\\\nas01", "offline", t0, ["priya", "yokesh"], ["P12513", "P13000"], ["vikram"]),
                   OfficeRoot("\\\\nas09", "offline", t0, ["priya"], ["X1"])]
    rows = vikram.watchers._root_rows(local, office_rows, {})
    assert [r["rootName"] for r in rows] == ["\\\\nas01", "\\\\nas09"]
    assert rows[0]["status"] == "offline" and rows[0]["seenBy"] == 2 and rows[0]["jobsAffected"] == 2
    assert rows[0]["mapping"] == "Z: → \\\\nas01\\Project" and "seen by 2 PCs" in rows[0]["statusLabel"]
