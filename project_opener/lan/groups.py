"""``groups.json`` on the hub: ``{"schema": 1, "groups": [Group, ...]}``.  Owner: builder 1 (CORE+HUB).

Anyone may edit; last writer wins; ``updated_by`` records who.  Writers
re-read, apply their one change, and write atomically, so two people editing
different groups within a minute both land unless they write in the same instant.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from project_opener.core import models as M
from project_opener.core.jsonio import read_json, write_json_atomic

log = logging.getLogger(__name__)

GROUP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def clean_name(name: str) -> str:
    """"@P12513 team" -> "p12513-team" (the form mentions use); "" when nothing usable is left."""
    n = re.sub(r"\s+", "-", (name or "").strip().lstrip("@").strip()).lower()
    n = re.sub(r"[^a-z0-9._-]", "", n).strip(".-_")
    return n[:64] if n and GROUP_NAME_RE.match(n) else ""


class GroupBook:
    def __init__(self, hub_root: Path | None):
        self.path = Path(hub_root) / "groups.json" if hub_root else None

    def all(self) -> list[M.Group]:
        if self.path is None:
            return []
        d = read_json(self.path, {}) or {}
        raw = d.get("groups", []) if isinstance(d, dict) else []
        out: list[M.Group] = []
        seen: set[str] = set()
        for g in raw if isinstance(raw, list) else []:
            if not isinstance(g, dict):
                continue
            grp = M.Group.from_dict(g)
            grp.name = clean_name(grp.name) or grp.name.lower()
            grp.members = [m.lower() for m in grp.members]
            if grp.name in seen:
                continue
            seen.add(grp.name)
            out.append(grp)
        out.sort(key=lambda g: g.name)
        return out

    def get(self, name: str) -> M.Group | None:
        key = clean_name(name)
        return next((g for g in self.all() if g.name == key), None)

    def _write(self, groups: list[M.Group]) -> None:
        assert self.path is not None
        write_json_atomic(self.path, {"schema": 1, "groups": [g.to_dict() for g in groups]})

    def save(self, group: M.Group, by: str | None = None) -> None:
        """Insert or replace by name (re-read first; one change per write)."""
        if self.path is None:
            raise OSError("no Team Hub configured")
        name = clean_name(group.name)
        if not name:
            raise ValueError(f"not a usable group name: {group.name!r}")
        group.name = name
        members: list[str] = []
        for m in group.members:
            m = m.strip().lstrip("@").lower()
            if m and m not in members:
                members.append(m)
        group.members = members
        groups = self.all()
        old = next((g for g in groups if g.name == name), None)
        if old is not None:
            group.created_by = old.created_by or group.created_by
        group.updated_by = by or group.updated_by or M.current_user()
        group.updated_at = M.now_iso()
        self._write([g for g in groups if g.name != name] + [group])

    def remove(self, name: str) -> bool:
        if self.path is None:
            return False
        key = clean_name(name)
        groups = self.all()
        keep = [g for g in groups if g.name != key]
        if len(keep) == len(groups):
            return False
        self._write(keep)
        return True
