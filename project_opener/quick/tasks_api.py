"""``app.tasks``: My tasks on Home, the hub's Tasks tab, the task line on cards and the dock footer.
Owner: builder 1 (CORE+HUB).  Backed by ``core.tasks.TaskStore`` over the hub's ``tasks/`` (or the local
fallback folder when no hub is set).
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from project_opener.quick.base import ApiBase, ro
from project_opener.quick.listmodel import DictListModel

TASK_ROLES = (
    "taskId", "title", "owner", "ownerName", "due", "dueText", "overdue", "done", "doneAt", "doneBy",
    "createdBy", "createdByName", "attachKind", "attachId", "attachTitle", "jobNumber", "note", "mine",
)


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

    @Slot()
    def refresh(self) -> None:
        self.todo("TasksApi.refresh")

    @Slot(str)
    def setGroupBy(self, mode: str) -> None:
        self.todo("TasksApi.setGroupBy")

    @Slot(str, str, str, str, str, result=str)
    def create(self, title: str, owner: str, due: str, attach_kind: str, attach_id: str) -> str:
        """Returns the task id.  Assigning someone else writes a "task" inbox entry and a Cliq DM."""
        return self.todo("TasksApi.create")

    @Slot(str, "QVariantMap")
    def edit(self, task_id: str, fields: dict[str, Any]) -> None:
        """title, owner, due, note, attachKind, attachId."""
        self.todo("TasksApi.edit")

    @Slot(str, bool)
    def setDone(self, task_id: str, done: bool) -> None:
        """Pulses "<name> finished <title>" and tells the creator (toast, Cliq DM)."""
        self.todo("TasksApi.setDone")

    @Slot(str)
    def remove(self, task_id: str) -> None:
        self.todo("TasksApi.remove")

    @Slot(str)
    def mailTask(self, task_id: str) -> None:
        self.todo("TasksApi.mailTask")

    @Slot(str, str, result=str)
    def lineFor(self, kind: str, local_id: str) -> str:
        """"Task: back-check lot 7, due Fri" for a card or the dock footer; "" when none."""
        return self.todo("TasksApi.lineFor")
