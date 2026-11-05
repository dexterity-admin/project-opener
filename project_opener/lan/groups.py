"""``groups.json`` on the hub: ``{"schema": 1, "groups": [Group, ...]}``.  Owner: builder 1 (CORE+HUB).

Anyone may edit; last writer wins; ``updated_by`` records who.  Writers
re-read, apply their one change, and write atomically, so two people editing
different groups within a minute both land unless they write in the same instant.
"""
from __future__ import annotations

from pathlib import Path

from project_opener.core import models as M


class GroupBook:
    def __init__(self, hub_root: Path | None):
        self.path = Path(hub_root) / "groups.json" if hub_root else None

    def all(self) -> list[M.Group]:
        raise NotImplementedError("GroupBook.all")

    def get(self, name: str) -> M.Group | None:
        raise NotImplementedError("GroupBook.get")

    def save(self, group: M.Group) -> None:
        raise NotImplementedError("GroupBook.save")

    def remove(self, name: str) -> bool:
        raise NotImplementedError("GroupBook.remove")
