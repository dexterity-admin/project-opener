"""Release check (a), two PCs on one hub: a task never drops out of Home's centre card while My tasks lists it.

Two causes were found with ``U:\\Vikram\\_Claude_Work\\temp\\fin2\\twopc.py`` (two real facades, one hub):

* a refresh that started before a local write landed read the old file set; applying it dropped a new task,
  or put an edited one back, until the next refresh (60 s);
* a task made before its activity was published carries no published id, so the other PC's clone of the
  activity never matched it: My tasks listed it, the card read "Add a task".

The pool is replaced by a queue the test runs by hand, so the interleavings are exact.
"""
from __future__ import annotations

import os

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


class PC(QObject):
    """One PC: real context, store, hub and TasksApi; ``run_async`` jobs wait in ``jobs`` until ``run``."""
    toast = Signal(str, str, str)

    def __init__(self, data_dir, hub_root, user, name):
        super().__init__()
        self.ctx = AppContext(data_dir)
        self.ctx.user = user
        self.ctx.settings.display_name = name
        self.ctx.settings.hub_path = str(hub_root)
        self.ctx.hub = TeamHub(hub_root, user, name)
        self.jobs: list[tuple] = []
        self.deferred = False
        self.hub = HubApi(self)
        self.tasks = TasksApi(self)
        self.watchers = WatchersApi(self)
        self.capture = None
        self.ctx.hub.heartbeat()

    def run_async(self, fn, done=None, fail=None):
        if self.deferred:
            self.jobs.append((fn, done, fail))
            return
        self._run(fn, done, fail)

    @staticmethod
    def _run(fn, done, fail):
        try:
            r = fn()
        except Exception as exc:  # noqa: BLE001
            if fail:
                fail(exc)
            return
        if done:
            done(r)

    def work(self, i):
        """Run job ``i``'s work now; returns a callable that delivers its result (the GUI-thread half)."""
        fn, done, fail = self.jobs.pop(i)
        try:
            r = fn()
        except Exception as exc:  # noqa: BLE001
            err = exc
            return lambda: fail and fail(err)
        return lambda: done and done(r)

    def run_on_gui(self, fn):
        fn()

    def open_link(self, kind, key):
        pass


def _activity(pc: PC, name="Lot 7 check") -> M.Activity:
    p = M.Project(name="As-built isometrics", job_number="P12513")
    pc.ctx.store.add(p)
    a = M.Activity(name=name, project_ids=[p.id])
    pc.ctx.store.add_activity(a)
    return a


def _card(pc: PC, act_id: str) -> list[str]:
    """Home's centre card: ActivitiesApi._open_tasks reads tasks.all rows by attachId."""
    return [r["title"] for r in pc.tasks.all.rows
            if r["attachKind"] == "activity" and r["attachId"] == act_id and not r["done"]]


def test_a_refresh_that_started_before_a_create_does_not_drop_it(qapp, tmp_path, hub_root):
    pc = PC(tmp_path / "a", hub_root, "vikram", "Vikram")
    act = _activity(pc)
    pc.tasks.refresh()
    pc.deferred = True
    pc.tasks.refresh()                                     # job 0: the refresh is in flight ...
    deliver_refresh = pc.work(0)                           # ... and has read the hub: no task yet
    pc.tasks.create("Back-check the lot", "vikram", "", "activity", act.id)
    assert _card(pc, act.id) == ["Back-check the lot"]
    deliver_refresh()                                      # the old read arrives after the create
    assert _card(pc, act.id) == ["Back-check the lot"]     # it used to vanish here for up to 60 s
    assert [r["title"] for r in pc.tasks.mine.rows] == ["Back-check the lot"]
    pc.work(0)()                                           # the write lands
    pc.deferred = False
    pc.tasks.refresh()                                     # a read after it: the file is the truth
    assert _card(pc, act.id) == ["Back-check the lot"]
    assert not pc.tasks._pending                           # nothing held once the hub agrees


def test_a_refresh_in_flight_does_not_undo_an_edit_or_bring_back_a_removal(qapp, tmp_path, hub_root):
    pc = PC(tmp_path / "a", hub_root, "vikram", "Vikram")
    act = _activity(pc)
    tid = pc.tasks.create("Old title", "vikram", "", "activity", act.id)
    gone = pc.tasks.create("To remove", "vikram", "", "activity", act.id)
    pc.tasks.refresh()
    pc.deferred = True
    pc.tasks.refresh()
    deliver_refresh = pc.work(0)                            # read: both tasks, old title
    pc.tasks.edit(tid, {"title": "New title"})
    pc.tasks.remove(gone)
    deliver_refresh()
    assert _card(pc, act.id) == ["New title"]
    while pc.jobs:
        pc.work(0)()
    pc.deferred = False
    pc.tasks.refresh()
    assert _card(pc, act.id) == ["New title"]


def test_the_hub_not_answering_once_keeps_the_team_tasks(qapp, tmp_path, hub_root, monkeypatch):
    pc = PC(tmp_path / "a", hub_root, "vikram", "Vikram")
    act = _activity(pc)
    pc.tasks.create("On the hub", "vikram", "", "activity", act.id)
    pc.tasks.refresh()
    monkeypatch.setattr(pc.ctx.hub, "reachable", lambda *a, **k: False)
    pc.tasks.refresh()
    assert _card(pc, act.id) == ["On the hub"]


def test_a_task_made_before_publishing_reaches_the_clone_on_the_other_pc(qapp, tmp_path, hub_root):
    a = PC(tmp_path / "a", hub_root, "vikram", "Vikram")
    b = PC(tmp_path / "b", hub_root, "yokesh", "Yokesh")
    act = _activity(a)
    a.tasks.create("Made before publishing", "yokesh", "", "activity", act.id)
    a.hub.publishActivity(act.id, "", [])
    pid = a.ctx.store.activity(act.id).origin.published_id
    assert pid
    b.hub._force_refresh()
    clone_id = b.hub.clonePublished(pid)
    assert clone_id
    b.hub._force_refresh()
    b.tasks.refresh()
    assert [r["title"] for r in b.tasks.mine.rows] == ["Made before publishing"]
    assert _card(b, clone_id) == ["Made before publishing"]          # the card used to read "Add a task"
    assert b.tasks.lineFor("activity", clone_id).startswith("Task: Made before publishing")
    a.tasks.refresh()
    assert _card(a, act.id) == ["Made before publishing"]            # and it stays on the publisher's card


def test_a_file_mid_rewrite_by_the_other_pc_does_not_drop_the_task(qapp, tmp_path, hub_root, monkeypatch):
    """Found in the two-process run (``temp\r4\two.sh``): B's atomic rewrite made A's read fail for an
    instant, and A's refresh dropped the task until the next one."""
    import project_opener.core.tasks as CT
    a = PC(tmp_path / "a", hub_root, "vikram", "Vikram")
    act = _activity(a)
    tid = a.tasks.create("Edited on the other PC", "vikram", "", "activity", act.id)
    a.tasks.refresh()
    a.tasks.refresh()                                      # past the pending write: the hub file is the truth
    assert not a.tasks._pending
    real = CT.read_json
    monkeypatch.setattr(CT, "read_json", lambda p, d=None: None if p.stem == tid else real(p, d))
    monkeypatch.setattr(CT.time, "sleep", lambda s: None)
    a.tasks.refresh()
    assert _card(a, act.id) == ["Edited on the other PC"]
    monkeypatch.setattr(CT, "read_json", real)
    (hub_root / "tasks" / f"{tid}.json").unlink(missing_ok=True)
    for p in hub_root.rglob(f"{tid}.json"):
        p.unlink()
    a.tasks.refresh()                                      # really removed: gone on the next read
    assert _card(a, act.id) == []
