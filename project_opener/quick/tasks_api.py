"""``app.tasks``: My tasks on Home, the hub's Tasks tab, the task line on cards and the dock footer.
Owner: builder 1 (CORE+HUB).  Backed by ``core.tasks.TaskStore`` over the hub's ``tasks/`` (or the local
fallback folder when no hub is set).

Files are read and written on the pool; the models update optimistically on the
GUI thread so a new task shows at once.  When a hub becomes reachable, tasks made
offline move from the local folder to the hub (``TaskStore.adopt_local``).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from project_opener import constants as C
from project_opener.core import mail
from project_opener.core import mentions as MN
from project_opener.core import models as M
from project_opener.core.tasks import TaskStore, due_text, is_overdue, parse_due, sort_by_due, when_text
from project_opener.quick.base import ApiBase, ro
from project_opener.quick.listmodel import DictListModel

log = logging.getLogger(__name__)

TASK_ROLES = (
    "taskId", "title", "owner", "ownerName", "due", "dueText", "overdue", "done", "doneAt", "doneBy",
    "createdBy", "createdByName", "attachKind", "attachId", "attachTitle", "jobNumber", "note", "mine",
)


def task_link(task_id: str) -> str:
    from project_opener.ipc import make_link
    return make_link("task", task_id)


class TasksApi(ApiBase):
    tasksChanged = Signal()
    taskDone = Signal(str, str)             # task id, by login

    def __init__(self, app: Any):
        super().__init__(app)
        self._mine = DictListModel(TASK_ROLES, key="taskId", parent=self)
        self._all = DictListModel(TASK_ROLES, key="taskId", parent=self)
        self._open_count = 0
        self._mine_open_count = 0
        self._group_by = "owner"
        self._tasks: dict[str, M.Task] = {}
        self._known: dict[str, tuple[str, str]] | None = None    # id -> (owner, done_at) at the last refresh
        self._root: Path | None = None
        self._on_hub = False
        self._refreshing = False
        self._timer: QTimer | None = None

    @Property(QObject, constant=True)
    def mine(self) -> DictListModel:
        """My open tasks, due soonest first (Home strip)."""
        return self._mine

    @Property(QObject, constant=True)
    def all(self) -> DictListModel:
        """Every task, ordered by ``groupBy`` (owner | job), open before done."""
        return self._all

    openCount = ro(int, "_open_count", tasksChanged)
    mineOpenCount = ro(int, "_mine_open_count", tasksChanged)   # the rail's count
    groupBy = ro(str, "_group_by", tasksChanged)

    # ------------------------------------------------------------ helpers
    @property
    def ctx(self) -> Any:
        return self.app.ctx

    @property
    def me(self) -> str:
        return self.ctx.user

    def local_root(self) -> Path:
        return Path(self.ctx.store.root) / C.LOCAL_TASKS_DIR

    def _store(self) -> TaskStore:
        """The store refresh last settled on; before the first refresh, the hub's when one is configured."""
        if self._root is None and self.ctx.hub.configured:
            return TaskStore(self.ctx.hub.sub("tasks"))
        return TaskStore(self._root or self.local_root())

    def latest(self) -> list[M.Task]:
        """The tasks as of the last refresh (watchers' time checks read this)."""
        return list(self._tasks.values())

    def name_for(self, login: str) -> str:
        if not login:
            return ""
        try:
            return self.app.hub.name_for(login)
        except Exception:  # noqa: BLE001
            return login

    def _dispatcher(self) -> Any:
        try:
            return self.app.watchers.dispatcher()
        except Exception:  # noqa: BLE001
            return None

    def _toast(self, title: str, body: str = "", level: str = "info") -> None:
        try:
            self.app.toast.emit(title, body, level)
        except Exception:  # noqa: BLE001
            log.info("%s: %s", title, body)

    # ---------------------------------------------------------- lifecycle
    def start(self) -> None:
        self._timer = QTimer(self)
        self._timer.setInterval(C.HUB_TASKS_REFRESH_S * 1000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.ctx.hub_changed.connect(lambda _s: self.refresh())
        users = getattr(getattr(self.app, "hub", None), "usersChanged", None)
        if users is not None:
            users.connect(self._on_users)            # rows read "from Yokesh", never "from yokesh" (juror U2-2)
        self.refresh()

    def _on_users(self) -> None:
        if self._tasks:
            self._rebuild()

    def shutdown(self) -> None:
        if self._timer:
            self._timer.stop()

    # -------------------------------------------------------------- slots
    @Slot()
    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        hub = self.ctx.hub
        local = self.local_root()

        def work() -> tuple[Path, bool, list[M.Task], int]:
            moved = 0
            if hub.configured and hub.reachable():
                root = hub.sub("tasks")
                root.mkdir(parents=True, exist_ok=True)
                store = TaskStore(root)
                if local.exists():
                    moved = store.adopt_local(local)
                return root, True, store.all(), moved
            return local, False, TaskStore(local).all(), 0

        def done(res: tuple[Path, bool, list[M.Task], int]) -> None:
            self._refreshing = False
            root, on_hub, tasks, moved = res
            self._root, self._on_hub = root, on_hub
            if moved:
                self._toast("Tasks moved to the Team Hub", f"{moved} task{'s' if moved != 1 else ''}", "info")
            self._apply(tasks)

        def fail(exc: Exception) -> None:
            self._refreshing = False
            log.warning("task refresh failed: %s", exc)

        self.app.run_async(work, done, fail)

    def _apply(self, tasks: list[M.Task], detect: bool = True) -> None:
        self._tasks = {t.id: t for t in tasks}
        if detect:
            self._detect_changes(tasks)
        self._rebuild()

    def _detect_changes(self, tasks: list[M.Task]) -> None:
        """Assigned to me / done since the last refresh -> hub events for watchers, toasts for creators."""
        now = {t.id: (t.owner.lower(), t.done_at) for t in tasks}
        before = self._known
        self._known = now
        if before is None:
            return
        me = self.me.lower()
        assigned = [t for t in tasks if t.owner.lower() == me and t.updated_by.lower() != me
                    and before.get(t.id, ("", ""))[0] != me and not t.done]
        done = [t for t in tasks if t.done_at and before.get(t.id, ("", ""))[1] != t.done_at]
        for t in done:
            self.taskDone.emit(t.id, t.done_by)
        if assigned or done:
            try:
                self.app.watchers.push_hub_events(tasks_assigned=assigned, tasks_done=done)
            except Exception:  # noqa: BLE001
                log.debug("watchers not ready", exc_info=True)

    def _attach(self, task: M.Task) -> tuple[str, str]:
        """(local id, title) of what the task is attached to, as this workspace knows it."""
        link = task.link
        if not link:
            return "", ""
        store = self.ctx.store
        if link.kind == "activity":
            act = store.activity(link.local_id) if link.local_id else None
            if act is None and link.published_id:
                act = next((a for a in store.activities if a.origin.published_id == link.published_id), None)
            return (act.id if act else ""), link.title or (act.name if act else "")
        proj = store.get(link.local_id) if link.local_id else None
        if proj is None and link.published_id:
            proj = next((p for p in store.projects if p.origin.published_id == link.published_id), None)
        return (proj.id if proj else ""), link.title or (proj.title if proj else "")

    def _row(self, t: M.Task) -> dict[str, Any]:
        attach_id, attach_title = self._attach(t)
        return {"taskId": t.id, "title": t.title, "owner": t.owner, "ownerName": self.name_for(t.owner),
                "due": t.due, "dueText": due_text(t.due), "overdue": is_overdue(t), "done": t.done,
                # display text, as the task row prints them: "done 14:02 by Yokesh" (V4-SEAMS, builder 4 ask 6)
                "doneAt": when_text(t.done_at) if t.done_at else "",
                "doneBy": self.name_for(t.done_by) if t.done_by else "", "createdBy": t.created_by,
                "createdByName": self.name_for(t.created_by), "attachKind": t.link.kind if t.link else "",
                "attachId": attach_id, "attachTitle": attach_title,
                "jobNumber": t.link.job_number if t.link else "", "note": t.note,
                "mine": t.owner.lower() == self.me.lower()}

    def _rebuild(self) -> None:
        tasks = list(self._tasks.values())
        me = self.me.lower()
        mine = sort_by_due([t for t in tasks if t.owner.lower() == me and not t.done])
        self._mine.sync([self._row(t) for t in mine])
        rows = [self._row(t) for t in tasks]
        order = {t.id: i for i, t in enumerate(sort_by_due(tasks))}
        if self._group_by == "job":
            rows.sort(key=lambda r: (r["done"], (r["jobNumber"] or r["attachTitle"] or "~").lower(), order[r["taskId"]]))
        else:
            rows.sort(key=lambda r: (r["done"], (r["ownerName"] or "~").lower(), order[r["taskId"]]))
        self._all.sync(rows)
        self._open_count = sum(1 for t in tasks if not t.done)
        self._mine_open_count = len(mine)
        self.tasksChanged.emit()

    def _put(self, task: M.Task) -> None:
        """Show at once, write on the pool."""
        self._tasks[task.id] = task
        if self._known is not None:
            self._known[task.id] = (task.owner.lower(), task.done_at)
        self._rebuild()
        store, local = self._store(), TaskStore(self.local_root())
        copy = M.Task.from_dict(task.to_dict())

        def work() -> bool:
            try:
                store.save(copy)
                return True
            except OSError:
                if store.root == local.root:
                    raise
                local.save(copy)             # hub unreachable: keep it here; it moves on the next refresh
                return False

        self.app.run_async(work, None, lambda e: self._toast("Task not saved", str(e), "error"))

    def _notify(self, logins: list[str], text: str, task: M.Task, kind: str = "task") -> None:
        logins = [lg for lg in logins if lg and lg.lower() != self.me.lower()]
        dispatcher = self._dispatcher()
        if not logins or dispatcher is None or not self._on_hub:
            return
        hub = self.ctx.hub

        def work() -> None:
            reached = hub.expand_targets(logins)
            dispatcher.notify_people(reached, text, task_link(task.id), kind=kind, task_id=task.id, title=task.title)

        self.app.run_async(work)

    def _pulse(self, event: str, detail: str, task: M.Task, mentions: list[str] | None = None) -> None:
        hub = self.ctx.hub
        if self._on_hub and self.ctx.settings.hub_share_pulse:
            self.app.run_async(lambda: hub.pulse(event, detail, kind="task", mentions=mentions, task_id=task.id))

    def _link_for(self, kind: str, local_id: str) -> M.TaskLink | None:
        store = self.ctx.store
        if kind == "activity":
            act = store.activity(local_id)
            if act is None:
                return None
            proj = store.get(act.primary_project_id) if act.primary_project_id else None
            spine = (proj.job_number or proj.title) if proj else ""
            return M.TaskLink("activity", act.id, act.origin.published_id,
                              f"{spine} · {act.name}" if spine else act.name, proj.job_number if proj else "")
        if kind == "project":
            proj = store.get(local_id)
            if proj is None:
                return None
            return M.TaskLink("project", proj.id, proj.origin.published_id, proj.title, proj.job_number)
        return None

    @Slot(str)
    def setGroupBy(self, mode: str) -> None:  # noqa: N802
        mode = mode if mode in ("owner", "job") else "owner"
        if mode != self._group_by:
            self._group_by = mode
            self._rebuild()

    @Slot(str, str, str, str, str, result=str)
    def create(self, title: str, owner: str, due: str, attach_kind: str, attach_id: str) -> str:
        """Returns the task id.  Assigning someone else writes a "task" inbox entry and a Cliq DM."""
        title = (title or "").strip()
        if not title:
            return ""
        owner = MN.normalise_targets([owner])[0] if (owner or "").strip() else ""
        due = due.strip()[:10] if parse_due(due) else ""
        task = M.Task(title, owner, due, created_by=self.me, updated_by=self.me,
                      link=self._link_for(attach_kind, attach_id) if attach_id else None,
                      mentions=MN.parse_mentions(title))
        self._put(task)
        me_name = self.ctx.display_name()
        if owner and owner != self.me.lower():
            when = f", {due_text(due)}" if due else ""
            self._notify([owner], f"{me_name} assigned you: {title}{when}", task)
        others = [m for m in task.mentions if m != owner]
        if others:
            self._notify(others, f"{me_name} mentioned you in a task: {title}", task, kind="mention")
        self._pulse("task", f"{title} → {self.name_for(owner) or 'unassigned'}", task, [owner] if owner else None)
        return task.id

    @Slot(str, "QVariantMap")
    def edit(self, task_id: str, fields: dict[str, Any]) -> None:
        """title, owner, due, note, attachKind, attachId."""
        old = self._tasks.get(task_id)
        if old is None:
            return
        task = M.Task.from_dict(old.to_dict())
        f = dict(fields or {})
        if "title" in f and str(f["title"]).strip():
            task.title = str(f["title"]).strip()
        if "owner" in f:
            task.owner = MN.normalise_targets([str(f["owner"])])[0] if str(f["owner"]).strip() else ""
        if "due" in f:
            task.due = str(f["due"])[:10] if parse_due(str(f["due"])) else ""
        if "note" in f:
            task.note = str(f["note"])
        if "attachKind" in f or "attachId" in f:
            kind = str(f.get("attachKind", task.link.kind if task.link else "activity"))
            aid = str(f.get("attachId", ""))
            task.link = self._link_for(kind, aid) if aid else None
        task.mentions = MN.parse_mentions(f"{task.title} {task.note}")
        task.updated_by, task.updated_at = self.me, M.now_iso()
        self._put(task)
        if task.owner and task.owner != old.owner and task.owner != self.me.lower():
            self._notify([task.owner], f"{self.ctx.display_name()} assigned you: {task.title}", task)

    @Slot(str, bool)
    def setDone(self, task_id: str, done: bool) -> None:  # noqa: N802
        """Pulses "<name> finished <title>" and tells the creator (toast, Cliq DM)."""
        old = self._tasks.get(task_id)
        if old is None or old.done == bool(done):
            return
        task = M.Task.from_dict(old.to_dict())
        task.mark_done(self.me, bool(done))
        self._put(task)
        if done:
            text = f"{self.ctx.display_name()} finished {task.title}"
            self._pulse("task", f"finished {task.title}", task)
            self._notify([task.created_by], text, task)
            self.taskDone.emit(task.id, self.me)

    @Slot(str)
    def remove(self, task_id: str) -> None:
        if self._tasks.pop(task_id, None) is None:
            return
        if self._known is not None:
            self._known.pop(task_id, None)
        self._rebuild()
        store = self._store()
        self.app.run_async(lambda: store.remove(task_id))

    @Slot(str)
    def mailTask(self, task_id: str) -> None:  # noqa: N802
        task = self._tasks.get(task_id)
        if task is None:
            return
        draft = mail.task_draft(task, task_link(task.id), self.name_for(task.owner),
                                self.name_for(task.done_by) if task.done_by else "")
        client = self.ctx.settings.mail_client

        def done(ok: bool) -> None:
            if not ok:
                self._toast("No mail program answered", "Neither Outlook nor a mailto: handler opened.", "warning")

        self.app.run_async(lambda: mail.open_draft(draft, client), done)

    @Slot(str, str, result=str)
    def lineFor(self, kind: str, local_id: str) -> str:  # noqa: N802
        """"Task: back-check lot 7, due Fri" for a card or the dock footer; "" when none."""
        store = self.ctx.store
        obj: Any = store.activity(local_id) if kind == "activity" else store.get(local_id)
        pid = obj.origin.published_id if obj is not None else ""
        hits = [t for t in self._tasks.values() if not t.done and t.link and t.link.kind == kind
                and ((local_id and t.link.local_id == local_id) or (pid and t.link.published_id == pid))]
        if not hits:
            return ""
        first = sort_by_due(hits)[0]
        line = f"Task: {first.title}" + (f", {due_text(first.due)}" if first.due else "")
        if len(hits) > 1:
            line += f" (+{len(hits) - 1} more)"
        return line
