"""Tasks as one JSON file each (``<root>/<id>.json``).  Owner: builder 1 (CORE+HUB).

``root`` is the hub's ``tasks/`` folder, or ``data_dir()/tasks`` when no hub is
set (same format; nothing to migrate when a hub is added later except moving
files, which ``adopt_local`` does).  Anyone may write any task (everyone equal);
``updated_by``/``updated_at`` and the pulse record who.  Last writer wins.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from project_opener.core import models as M


class TaskStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def all(self) -> list[M.Task]:
        """Every readable task; corrupt files skipped (logged)."""
        raise NotImplementedError("TaskStore.all")

    def get(self, task_id: str) -> M.Task | None:
        raise NotImplementedError("TaskStore.get")

    def save(self, task: M.Task) -> None:
        """Atomic write of ``<id>.json``."""
        raise NotImplementedError("TaskStore.save")

    def remove(self, task_id: str) -> bool:
        raise NotImplementedError("TaskStore.remove")

    def for_owner(self, login: str, include_done: bool = False) -> list[M.Task]:
        """Due soonest first; no due date last; then created order."""
        raise NotImplementedError("TaskStore.for_owner")

    def for_link(self, kind: str, local_id: str = "", published_id: str = "") -> list[M.Task]:
        raise NotImplementedError("TaskStore.for_link")

    def adopt_local(self, local_root: Path) -> int:
        """Move tasks from the local fallback folder into this (hub) store; returns the count."""
        raise NotImplementedError("TaskStore.adopt_local")


def due_text(due: str, today: date | None = None) -> str:
    """"due today", "due Fri", "due 14 Nov", "2 days overdue"; "" when no due date."""
    raise NotImplementedError("due_text")


def is_overdue(task: M.Task, today: date | None = None) -> bool:
    raise NotImplementedError("is_overdue")
