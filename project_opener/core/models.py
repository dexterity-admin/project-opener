"""Data model for workspaces.

A *Project* is a named bundle of *Items* (files, folders, links, apps,
commands).  *Launch sets* are named subsets of a project's items that open
together - the successor of v2 "activities" and of v1 "checked files".

Every model is a plain dataclass with ``to_dict``/``from_dict`` so the store,
the Team Hub and the tests can round-trip them without Qt.
"""
from __future__ import annotations

import getpass
import socket
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

ItemKind = str  # "file" | "folder" | "url" | "app" | "command"
ITEM_KINDS: tuple[str, ...] = ("file", "folder", "url", "app", "command")

DEFAULT_COLOR = "#3B82F6"
PALETTE: tuple[str, ...] = (
    "#3B82F6", "#6366F1", "#8B5CF6", "#EC4899", "#EF4444", "#F97316",
    "#F59E0B", "#10B981", "#14B8A6", "#06B6D4", "#64748B", "#A16207",
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def current_user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - exotic environments
        return "user"


def current_host() -> str:
    try:
        return socket.gethostname()
    except Exception:  # pragma: no cover
        return "host"


def guess_kind(path: str) -> ItemKind:
    """Classify a raw path/URL string.  Pure string logic; no filesystem."""
    p = (path or "").strip()
    low = p.lower()
    if low.startswith(("http://", "https://", "ftp://", "mailto:", "ms-teams:", "onenote:")):
        return "url"
    if low.startswith("cmd:") or low.startswith("ps:"):
        return "command"
    if low.endswith((".exe", ".bat", ".cmd", ".lnk", ".msi")):
        return "app"
    stripped = low.rstrip("\\/")
    tail = stripped.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    if "." in tail and not tail.startswith("."):
        return "file"
    return "folder"


@dataclass
class Item:
    path: str
    kind: ItemKind = "file"
    label: str = ""
    args: str = ""
    enabled: bool = True
    group: str = ""
    id: str = field(default_factory=new_id)
    added_at: str = field(default_factory=now_iso)

    @property
    def display_name(self) -> str:
        if self.label:
            return self.label
        p = self.path.rstrip("\\/")
        tail = p.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        return tail or p

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "path": self.path, "kind": self.kind, "label": self.label,
            "args": self.args, "enabled": self.enabled, "group": self.group,
            "added_at": self.added_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Item:
        path = str(d.get("path", "")).strip()
        kind = d.get("kind") or d.get("type") or guess_kind(path)
        if kind == "exe":
            kind = "app"
        if kind not in ITEM_KINDS:
            kind = guess_kind(path)
        return cls(
            id=str(d.get("id") or new_id()),
            path=path,
            kind=kind,
            label=str(d.get("label", "") or ""),
            args=str(d.get("args", "") or ""),
            enabled=bool(d.get("enabled", d.get("selected", True))),
            group=str(d.get("group", "") or ""),
            added_at=str(d.get("added_at") or now_iso()),
        )


@dataclass
class LaunchSet:
    name: str
    item_ids: list[str] = field(default_factory=list)
    id: str = field(default_factory=new_id)
    icon: str = "fa5s.rocket"

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "item_ids": list(self.item_ids), "icon": self.icon}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LaunchSet:
        return cls(
            id=str(d.get("id") or new_id()),
            name=str(d.get("name", "Launch set")),
            item_ids=[str(i) for i in d.get("item_ids", [])],
            icon=str(d.get("icon", "fa5s.rocket")),
        )


@dataclass
class Origin:
    """Where a project came from, so the Team view can show provenance."""
    source: str = "local"      # local | team | inbox | import
    author: str = ""
    published_id: str = ""
    published_at: str = ""
    revision: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "author": self.author, "published_id": self.published_id,
                "published_at": self.published_at, "revision": self.revision}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> Origin:
        d = d or {}
        return cls(
            source=str(d.get("source", "local")), author=str(d.get("author", "")),
            published_id=str(d.get("published_id", "")), published_at=str(d.get("published_at", "")),
            revision=int(d.get("revision", 0) or 0),
        )


@dataclass
class Project:
    name: str
    id: str = field(default_factory=new_id)
    description: str = ""
    notes: str = ""
    color: str = DEFAULT_COLOR
    icon: str = "fa5s.folder"
    tags: list[str] = field(default_factory=list)
    client: str = ""
    job_number: str = ""
    items: list[Item] = field(default_factory=list)
    launch_sets: list[LaunchSet] = field(default_factory=list)
    pinned_at: str | None = None
    favorite: bool = False
    auto_launch: bool = False
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    last_opened: str | None = None
    open_count: int = 0
    origin: Origin = field(default_factory=Origin)

    # ------------------------------------------------------------------ helpers
    @property
    def pinned(self) -> bool:
        return bool(self.pinned_at)

    @property
    def enabled_items(self) -> list[Item]:
        return [i for i in self.items if i.enabled]

    def item_by_id(self, item_id: str) -> Item | None:
        return next((i for i in self.items if i.id == item_id), None)

    def items_for_set(self, launch_set: LaunchSet) -> list[Item]:
        wanted = set(launch_set.item_ids)
        return [i for i in self.items if i.id in wanted]

    def touch(self) -> None:
        self.updated_at = now_iso()

    def mark_opened(self) -> None:
        self.last_opened = now_iso()
        self.open_count += 1

    def groups(self) -> list[str]:
        seen: list[str] = []
        for i in self.items:
            g = i.group or ""
            if g not in seen:
                seen.append(g)
        return seen

    def search_blob(self) -> str:
        parts = [self.name, self.description, self.notes, self.client, self.job_number, " ".join(self.tags)]
        parts += [i.display_name for i in self.items] + [i.path for i in self.items]
        parts += [s.name for s in self.launch_sets]
        return " ".join(p for p in parts if p).lower()

    # ------------------------------------------------------------- serialise
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "description": self.description, "notes": self.notes,
            "color": self.color, "icon": self.icon, "tags": list(self.tags), "client": self.client,
            "job_number": self.job_number,
            "items": [i.to_dict() for i in self.items],
            "launch_sets": [s.to_dict() for s in self.launch_sets],
            "pinned_at": self.pinned_at, "favorite": self.favorite, "auto_launch": self.auto_launch,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "last_opened": self.last_opened, "open_count": self.open_count,
            "origin": self.origin.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Project:
        items = [Item.from_dict(x) for x in d.get("items", []) if isinstance(x, dict)]
        sets = [LaunchSet.from_dict(x) for x in d.get("launch_sets", []) if isinstance(x, dict)]
        pinned_at = d.get("pinned_at")
        color = str(d.get("color") or DEFAULT_COLOR)
        if not color.startswith("#") or len(color) not in (7, 9):
            color = DEFAULT_COLOR
        return cls(
            id=str(d.get("id") or new_id()),
            name=str(d.get("name", "Untitled")).strip() or "Untitled",
            description=str(d.get("description", "") or ""),
            notes=str(d.get("notes", "") or ""),
            color=color,
            icon=str(d.get("icon") or "fa5s.folder"),
            tags=[str(t) for t in d.get("tags", []) if str(t).strip()],
            client=str(d.get("client", "") or ""),
            job_number=str(d.get("job_number", "") or ""),
            items=items,
            launch_sets=sets,
            pinned_at=str(pinned_at) if pinned_at else None,
            favorite=bool(d.get("favorite", False)),
            auto_launch=bool(d.get("auto_launch", False)),
            created_at=str(d.get("created_at") or now_iso()),
            updated_at=str(d.get("updated_at") or now_iso()),
            last_opened=str(d["last_opened"]) if d.get("last_opened") else None,
            open_count=int(d.get("open_count", 0) or 0),
            origin=Origin.from_dict(d.get("origin")),
        )

    def clone(self, new_name: str | None = None) -> Project:
        """Deep copy with fresh ids (used for duplicate / clone-from-team)."""
        d = self.to_dict()
        d["id"] = new_id()
        d["name"] = new_name or f"{self.name} (copy)"
        d["pinned_at"] = None
        d["auto_launch"] = False
        d["last_opened"] = None
        d["open_count"] = 0
        d["created_at"] = now_iso()
        id_map = {}
        for it in d["items"]:
            nid = new_id()
            id_map[it["id"]] = nid
            it["id"] = nid
        for s in d["launch_sets"]:
            s["id"] = new_id()
            s["item_ids"] = [id_map.get(i, i) for i in s["item_ids"]]
        return Project.from_dict(d)


# --------------------------------------------------------------------- legacy
def project_from_v1(name: str, data: dict[str, Any]) -> Project:
    """Convert a Project Opener 1.x project (files + notes + color)."""
    items = []
    for raw in data.get("files", []):
        if isinstance(raw, str):
            items.append(Item(path=raw, kind=guess_kind(raw)))
        elif isinstance(raw, dict) and raw.get("path"):
            items.append(Item(path=str(raw["path"]), kind=guess_kind(str(raw["path"])),
                              enabled=bool(raw.get("selected", True))))
    pinned = data.get("pinned")
    pinned_at = None
    if isinstance(pinned, (int, float)) and pinned > 0:
        dt = parse_iso(pinned)
        pinned_at = dt.isoformat(timespec="seconds") if dt else now_iso()
    last = parse_iso(data.get("last_opened"))
    color = str(data.get("color") or DEFAULT_COLOR)
    if color.lower() in ("#e0e0e0", "#ffffff", "#f3f4f6"):
        color = DEFAULT_COLOR
    if len(color) == 9:  # #AARRGGBB -> #RRGGBB
        color = "#" + color[3:]
    return Project(
        name=name, notes=str(data.get("notes", "") or ""), color=color, items=items,
        pinned_at=pinned_at, last_opened=last.isoformat(timespec="seconds") if last else None,
        origin=Origin(source="import", author=current_user()),
    )


def project_from_v2(name: str, data: dict[str, Any], author: str = "") -> Project:
    """Convert a Project Opener 2.x project (activities with typed items)."""
    items: list[Item] = []
    sets: list[LaunchSet] = []
    for act in data.get("activities", []):
        if not isinstance(act, dict):
            continue
        ids = []
        for raw in act.get("items", []):
            if not isinstance(raw, dict) or not raw.get("path"):
                continue
            it = Item.from_dict(raw)
            it.group = str(act.get("name", ""))
            items.append(it)
            ids.append(it.id)
        sets.append(LaunchSet(name=str(act.get("name", "Activity")), item_ids=ids))
    return Project(
        name=str(data.get("name") or name), description=str(data.get("description", "") or ""),
        items=items, launch_sets=sets,
        origin=Origin(source="import", author=author or current_user()),
    )


def dedupe_name(name: str, existing: Iterable[str]) -> str:
    taken = {e.lower() for e in existing}
    if name.lower() not in taken:
        return name
    n = 2
    while f"{name} ({n})".lower() in taken:
        n += 1
    return f"{name} ({n})"
