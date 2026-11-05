"""Data model for workspaces.

A *Project* is a named bundle of *Items* (files, folders, links, apps,
commands).  *Launch sets* are named subsets of a project's items that open
together - the successor of v2 "activities" and of v1 "checked files".

Version 4 adds (bottom of this module): *Activity* (the thing you open; items
drawn from any projects), *Snapshot*/*Checkpoint* (what was open), *Task*,
*Watcher*, *Group*, *LaunchProfile* and the records the hub and the capture
engine exchange.  In schema 4 a project's launch sets are kept only as a
frozen mirror for 3.2 readers; ``core.migrate`` turns them into activities.

Version 4 adds (bottom of this module, see docs/V4-ARCHITECTURE.md section 3):
*Activity* (the thing you open; items drawn from any projects), *Snapshot*
and *Checkpoint* (what was open), *Task*, *Watcher*, *Group*, *LaunchProfile*
and the small records the hub and the capture engine exchange.  In schema 4
launch sets are kept on projects only as a frozen mirror for 3.2 readers.

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
    profile_id: str = ""      # v4: LaunchProfile.id for kind "app" ("" = plain args)

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
            "added_at": self.added_at, "profile_id": self.profile_id,
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
            profile_id=str(d.get("profile_id", "") or ""),
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

    @property
    def spine(self) -> str:
        """What the office reads first: the job number, else the client, else nothing."""
        return self.job_number.strip() or self.client.strip()

    @property
    def title(self) -> str:
        """"P12513 · As-built isometrics": the job number (or client) first, then the name."""
        spine = self.spine
        return f"{spine} · {self.name}" if spine and spine.lower() not in self.name.lower() else self.name

    def items_for_set(self, launch_set: LaunchSet) -> list[Item]:
        """The set's items in its launch order (the order of ``item_ids``)."""
        by_id = {i.id: i for i in self.items}
        return [by_id[i] for i in launch_set.item_ids if i in by_id]

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


# ========================================================================= v4
# Everything below is new in schema 4 (docs/V4-ARCHITECTURE.md section 3).  Same
# rules as above: plain dataclasses, ``to_dict``/``from_dict`` round-trip, and
# ``from_dict`` never raises on bad input (hub files come from other PCs).

SNAPSHOT_STATUSES: tuple[str, ...] = ("identified", "ambiguous", "unidentified", "unsaved")
CHECKPOINT_KINDS: tuple[str, ...] = ("manual", "auto", "close")
WATCHER_KINDS: tuple[str, ...] = ("folder", "health", "hub", "time")
WATCHER_EVENTS: dict[str, tuple[str, ...]] = {
    "folder": ("new", "changed", "gone"),
    "health": ("down", "up"),
    "hub": ("published", "task_assigned", "task_done", "mention"),
    "time": ("due", "stale", "reminder"),
}
TASK_LINK_KINDS: tuple[str, ...] = ("activity", "project")
PROFILE_APPS: tuple[str, ...] = ("navisworks", "microstation", "autocad", "caesar", "other")
CHECKPOINTS_KEPT = 10


def _s(d: dict[str, Any], key: str, default: str = "") -> str:
    v = d.get(key, default)
    return default if v is None else str(v)


def _i(d: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(d.get(key, default) or 0)
    except (TypeError, ValueError):
        return default


def _f(d: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(d.get(key, default) or 0.0)
    except (TypeError, ValueError):
        return default


def _strs(v: Any) -> list[str]:
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)):
        return []
    return [str(x) for x in v if x is not None and str(x).strip()]


def _rect(v: Any) -> list[int]:
    """[left, top, right, bottom]; anything else becomes [0, 0, 0, 0]."""
    if isinstance(v, (list, tuple)) and len(v) == 4:
        try:
            return [int(x) for x in v]
        except (TypeError, ValueError):
            pass
    return [0, 0, 0, 0]


def _color_or(v: Any, default: str = "") -> str:
    c = str(v or "")
    return c if c.startswith("#") and len(c) in (7, 9) else default


def _dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


# ------------------------------------------------------------------ activity
@dataclass
class ActivityItem(Item):
    """An item of an activity: a full ``Item`` (the launcher and health checks
    take it unchanged) plus where it came from.

    ``project_id``/``source_item_id`` link it to a project item when it was drawn
    from one; the store keeps path/label/args/kind/profile in step when that
    project item is edited.  Both are "" for things captured from the desktop
    that belong to no project.
    """
    project_id: str = ""
    source_item_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["project_id"] = self.project_id
        d["source_item_id"] = self.source_item_id
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ActivityItem:
        d = _dict(d)
        base = Item.from_dict(d)
        return cls.from_item(base, _s(d, "project_id"), _s(d, "source_item_id"))

    @classmethod
    def from_item(cls, item: Item, project_id: str = "", source_item_id: str = "") -> ActivityItem:
        return cls(path=item.path, kind=item.kind, label=item.label, args=item.args, enabled=item.enabled,
                   group=item.group, id=item.id, added_at=item.added_at, profile_id=item.profile_id,
                   project_id=project_id, source_item_id=source_item_id)


@dataclass
class Activity:
    """The thing you open (brief section 2): items from any projects, in launch order."""
    name: str
    id: str = field(default_factory=new_id)
    short_name: str = ""               # the pill's label; "" = derived from name (``label``)
    description: str = ""
    notes: str = ""
    icon: str = ""                     # Phosphor name ("ph.ruler"); "" = shell default; 3.x "fa5s.*" kept verbatim
    color: str = ""                    # "" = the first project's colour (identity dot)
    project_ids: list[str] = field(default_factory=list)     # first = the activity's job (its spine)
    items: list[ActivityItem] = field(default_factory=list)  # launch order
    owner: str = field(default_factory=current_user)
    created_by: str = field(default_factory=current_user)
    pinned_at: str | None = None
    favorite: bool = False
    capture_enabled: bool = True       # per-activity capture switch (the global one is in Settings)
    resume_on_start: bool = True       # offer the Resume band after an unclean shutdown (never automatic)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    last_opened: str | None = None
    open_count: int = 0
    origin: Origin = field(default_factory=Origin)

    @property
    def pinned(self) -> bool:
        return bool(self.pinned_at)

    @property
    def label(self) -> str:
        """Short label for the pill and the tray: ``short_name`` or the name cut at 18 characters."""
        if self.short_name.strip():
            return self.short_name.strip()
        n = self.name.strip()
        return n if len(n) <= 18 else n[:17].rstrip() + "…"

    @property
    def primary_project_id(self) -> str:
        return self.project_ids[0] if self.project_ids else ""

    @property
    def enabled_items(self) -> list[ActivityItem]:
        return [i for i in self.items if i.enabled]

    def item_by_id(self, item_id: str) -> ActivityItem | None:
        return next((i for i in self.items if i.id == item_id), None)

    def item_by_path(self, path: str) -> ActivityItem | None:
        low = (path or "").strip().rstrip("\\/").lower()
        return next((i for i in self.items if i.path.strip().rstrip("\\/").lower() == low), None)

    def touch(self) -> None:
        self.updated_at = now_iso()

    def mark_opened(self) -> None:
        self.last_opened = now_iso()
        self.open_count += 1

    def search_blob(self) -> str:
        parts = [self.name, self.short_name, self.description, self.notes]
        parts += [i.display_name for i in self.items] + [i.path for i in self.items]
        return " ".join(p for p in parts if p).lower()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "short_name": self.short_name, "description": self.description,
            "notes": self.notes, "icon": self.icon, "color": self.color, "project_ids": list(self.project_ids),
            "items": [i.to_dict() for i in self.items], "owner": self.owner, "created_by": self.created_by,
            "pinned_at": self.pinned_at, "favorite": self.favorite, "capture_enabled": self.capture_enabled,
            "resume_on_start": self.resume_on_start, "created_at": self.created_at, "updated_at": self.updated_at,
            "last_opened": self.last_opened, "open_count": self.open_count, "origin": self.origin.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Activity:
        d = _dict(d)
        pinned_at = d.get("pinned_at")
        return cls(
            id=_s(d, "id") or new_id(),
            name=_s(d, "name", "Untitled").strip() or "Untitled",
            short_name=_s(d, "short_name"),
            description=_s(d, "description"),
            notes=_s(d, "notes"),
            icon=_s(d, "icon"),
            color=_color_or(d.get("color")),
            project_ids=_strs(d.get("project_ids")),
            items=[ActivityItem.from_dict(x) for x in d.get("items", []) or [] if isinstance(x, dict)],
            owner=_s(d, "owner") or current_user(),
            created_by=_s(d, "created_by") or _s(d, "owner") or current_user(),
            pinned_at=str(pinned_at) if pinned_at else None,
            favorite=bool(d.get("favorite", False)),
            capture_enabled=bool(d.get("capture_enabled", True)),
            resume_on_start=bool(d.get("resume_on_start", True)),
            created_at=_s(d, "created_at") or now_iso(),
            updated_at=_s(d, "updated_at") or now_iso(),
            last_opened=str(d["last_opened"]) if d.get("last_opened") else None,
            open_count=_i(d, "open_count"),
            origin=Origin.from_dict(d.get("origin") if isinstance(d.get("origin"), dict) else None),
        )

    def clone(self, new_name: str | None = None) -> Activity:
        """Deep copy with fresh ids for the activity and its items (duplicate / clone from the hub)."""
        d = self.to_dict()
        d.update(id=new_id(), name=new_name or f"{self.name} (copy)", pinned_at=None, last_opened=None,
                 open_count=0, created_at=now_iso(), updated_at=now_iso(), owner=current_user(),
                 created_by=current_user(), origin=Origin().to_dict())
        for it in d["items"]:
            it["id"] = new_id()
        return Activity.from_dict(d)


# ------------------------------------------------------------- capture data
@dataclass
class Monitor:
    device: str = ""                   # "\\\\.\\DISPLAY1"
    rect: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    work: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    dpi: int = 96
    primary: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"device": self.device, "rect": list(self.rect), "work": list(self.work), "dpi": self.dpi,
                "primary": self.primary}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Monitor:
        d = _dict(d)
        return cls(_s(d, "device"), _rect(d.get("rect")), _rect(d.get("work")), _i(d, "dpi", 96) or 96,
                   bool(d.get("primary", False)))


@dataclass
class WindowPlacement:
    """GetWindowPlacement in screen coordinates, plus the monitor it was on."""
    show_cmd: int = 1                  # 1 normal, 2 minimised, 3 maximised
    normal_rect: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    window_rect: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    monitor: str = ""
    monitor_rect: list[int] = field(default_factory=lambda: [0, 0, 0, 0])

    @property
    def maximised(self) -> bool:
        return self.show_cmd == 3

    def to_dict(self) -> dict[str, Any]:
        return {"show_cmd": self.show_cmd, "normal_rect": list(self.normal_rect),
                "window_rect": list(self.window_rect), "monitor": self.monitor,
                "monitor_rect": list(self.monitor_rect)}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> WindowPlacement | None:
        if not isinstance(d, dict):
            return None
        return cls(_i(d, "show_cmd", 1) or 1, _rect(d.get("normal_rect")), _rect(d.get("window_rect")),
                   _s(d, "monitor"), _rect(d.get("monitor_rect")))


@dataclass
class SnapshotEntry:
    """One top-level window as the capture engine saw it.

    ``status``: ``identified`` (a path or URL it can prove), ``ambiguous`` (a
    title matching several candidate paths, listed in ``candidates``),
    ``unidentified`` (title and process only) or ``unsaved`` (a document with no
    file yet).  Nothing here is ever guessed (brief section 3.1, honesty rule).
    """
    key: str                           # identity: "path:<lowercase path>" | "url:<url>" | "win:<process>|<title>"
    status: str = "unidentified"
    kind: str = ""                     # file | folder | url | app | "" (unknown)
    path: str = ""                     # file/folder path or URL; "" unless identified
    title: str = ""
    process: str = ""                  # "EXCEL.EXE"
    exe: str = ""
    window_class: str = ""
    app: str = ""                      # friendly name: "Excel", "Explorer", "PDF-XChange Editor"
    identified_by: str = ""            # shell | office-com | uia | title+items | title+recent | title-path | manual
    doc_name: str = ""
    candidates: list[str] = field(default_factory=list)
    note: str = ""                     # "active tab only" | "Protected View" | "unsaved - cannot be restored"
    item_id: str = ""                  # the activity item it matches; "" = not an item yet ("new")
    placement: WindowPlacement | None = None
    hwnd: int = 0                      # runtime only; meaningless after a restart
    pid: int = 0
    first_seen: str = field(default_factory=now_iso)

    @property
    def identified(self) -> bool:
        return self.status == "identified" and bool(self.path)

    @property
    def needs_path(self) -> bool:
        return self.status in ("unidentified", "ambiguous")

    @property
    def is_new(self) -> bool:
        """Identified but not yet one of the activity's items ("Save 2 new as items")."""
        return self.identified and not self.item_id

    def to_item(self, project_id: str = "") -> ActivityItem:
        kind = self.kind if self.kind in ITEM_KINDS else guess_kind(self.path)
        return ActivityItem(path=self.path, kind=kind, project_id=project_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "status": self.status, "kind": self.kind, "path": self.path, "title": self.title,
            "process": self.process, "exe": self.exe, "window_class": self.window_class, "app": self.app,
            "identified_by": self.identified_by, "doc_name": self.doc_name, "candidates": list(self.candidates),
            "note": self.note, "item_id": self.item_id,
            "placement": self.placement.to_dict() if self.placement else None,
            "hwnd": self.hwnd, "pid": self.pid, "first_seen": self.first_seen,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SnapshotEntry:
        d = _dict(d)
        status = _s(d, "status", "unidentified")
        if status not in SNAPSHOT_STATUSES:
            status = "unidentified"
        return cls(
            key=_s(d, "key") or f"win:{_s(d, 'process')}|{_s(d, 'title')}",
            status=status, kind=_s(d, "kind"), path=_s(d, "path"), title=_s(d, "title"),
            process=_s(d, "process"), exe=_s(d, "exe"), window_class=_s(d, "window_class"), app=_s(d, "app"),
            identified_by=_s(d, "identified_by"), doc_name=_s(d, "doc_name"), candidates=_strs(d.get("candidates")),
            note=_s(d, "note"), item_id=_s(d, "item_id"), placement=WindowPlacement.from_dict(d.get("placement")),
            hwnd=_i(d, "hwnd"), pid=_i(d, "pid"), first_seen=_s(d, "first_seen") or now_iso(),
        )


@dataclass
class Snapshot:
    """What was open at one moment while an activity ran."""
    activity_id: str
    taken_at: str = field(default_factory=now_iso)
    full: bool = False                 # a full re-identification pass (vs. incremental)
    monitors: list[Monitor] = field(default_factory=list)
    entries: list[SnapshotEntry] = field(default_factory=list)
    # When this run of the activity was first captured: entries whose ``first_seen`` is later were opened
    # while the activity ran; the first pass stamps what was already open with exactly this time.
    # "" = not recorded (snapshots written before 4.0's polish round).
    session_start: str = ""

    @property
    def open_count(self) -> int:
        return len(self.entries)

    @property
    def identified_count(self) -> int:
        return sum(1 for e in self.entries if e.identified)

    @property
    def needs_path_count(self) -> int:
        return sum(1 for e in self.entries if e.needs_path)

    @property
    def new_entries(self) -> list[SnapshotEntry]:
        return [e for e in self.entries if e.is_new]

    @property
    def restorable(self) -> list[SnapshotEntry]:
        return [e for e in self.entries if e.identified]

    def opened_since_start(self, entry: SnapshotEntry) -> bool:
        """Whether ``entry`` was first seen after this run's first pass (False when that is not recorded)."""
        return bool(self.session_start) and entry.first_seen > self.session_start

    def entry(self, key: str) -> SnapshotEntry | None:
        return next((e for e in self.entries if e.key == key), None)

    def to_dict(self) -> dict[str, Any]:
        return {"activity_id": self.activity_id, "taken_at": self.taken_at, "full": self.full,
                "monitors": [m.to_dict() for m in self.monitors], "entries": [e.to_dict() for e in self.entries],
                "session_start": self.session_start}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Snapshot:
        d = _dict(d)
        return cls(
            activity_id=_s(d, "activity_id"), taken_at=_s(d, "taken_at") or now_iso(), full=bool(d.get("full", False)),
            monitors=[Monitor.from_dict(m) for m in d.get("monitors", []) or [] if isinstance(m, dict)],
            entries=[SnapshotEntry.from_dict(e) for e in d.get("entries", []) or [] if isinstance(e, dict)],
            session_start=_s(d, "session_start"),
        )


@dataclass
class Checkpoint:
    """A snapshot kept in the activity's history (last ``CHECKPOINTS_KEPT``), each restorable."""
    activity_id: str
    snapshot: Snapshot
    id: str = field(default_factory=new_id)
    taken_at: str = field(default_factory=now_iso)
    kind: str = "manual"               # manual (Snapshot now) | auto (watcher) | close (activity ended)
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "activity_id": self.activity_id, "taken_at": self.taken_at, "kind": self.kind,
                "label": self.label, "snapshot": self.snapshot.to_dict()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Checkpoint:
        d = _dict(d)
        kind = _s(d, "kind", "manual")
        aid = _s(d, "activity_id")
        snap = Snapshot.from_dict(d.get("snapshot") or {})
        if not snap.activity_id:
            snap.activity_id = aid
        return cls(activity_id=aid, snapshot=snap, id=_s(d, "id") or new_id(),
                   taken_at=_s(d, "taken_at") or snap.taken_at, kind=kind if kind in CHECKPOINT_KINDS else "manual",
                   label=_s(d, "label"))


@dataclass
class RunningMarker:
    """Written when an activity starts, removed when it ends cleanly.

    A marker left at start-up whose ``pid``/``process_started`` is not a live
    Project Opener process means the PC went down while the activity ran: Home
    offers Resume (never automatic).
    """
    activity_id: str
    started_at: str = field(default_factory=now_iso)
    last_seen: str = field(default_factory=now_iso)
    pid: int = 0
    process_started: float = 0.0       # psutil create_time of the app process (pid reuse guard)
    host: str = field(default_factory=current_host)

    def to_dict(self) -> dict[str, Any]:
        return {"activity_id": self.activity_id, "started_at": self.started_at, "last_seen": self.last_seen,
                "pid": self.pid, "process_started": self.process_started, "host": self.host}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunningMarker:
        d = _dict(d)
        return cls(_s(d, "activity_id"), _s(d, "started_at") or now_iso(), _s(d, "last_seen") or now_iso(),
                   _i(d, "pid"), _f(d, "process_started"), _s(d, "host"))


# --------------------------------------------------------------------- tasks
@dataclass
class TaskLink:
    """What a task is attached to.  Local ids differ per PC, so the hub id travels too."""
    kind: str = "activity"             # activity | project
    local_id: str = ""                 # id in the creator's workspace
    published_id: str = ""             # hub published/<id>.json, "" when not published
    title: str = ""                    # as the creator saw it: "P12513 · Lot 7 check"
    job_number: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "local_id": self.local_id, "published_id": self.published_id,
                "title": self.title, "job_number": self.job_number}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> TaskLink | None:
        if not isinstance(d, dict):
            return None
        kind = _s(d, "kind", "activity")
        return cls(kind if kind in TASK_LINK_KINDS else "activity", _s(d, "local_id"), _s(d, "published_id"),
                   _s(d, "title"), _s(d, "job_number"))


@dataclass
class Task:
    """A free-form to-do on the hub (``tasks/<id>.json``): anyone creates and assigns; the record shows who."""
    title: str
    owner: str = ""                    # login; "" = unassigned
    due: str = ""                      # "YYYY-MM-DD" (local date) or ""
    id: str = field(default_factory=new_id)
    created_by: str = field(default_factory=current_user)
    created_at: str = field(default_factory=now_iso)
    updated_by: str = field(default_factory=current_user)
    updated_at: str = field(default_factory=now_iso)
    done_at: str = ""
    done_by: str = ""
    link: TaskLink | None = None
    note: str = ""
    mentions: list[str] = field(default_factory=list)   # "@priya", "@checkers" found in title or note

    @property
    def done(self) -> bool:
        return bool(self.done_at)

    def mark_done(self, by: str | None = None, done: bool = True) -> None:
        who = by or current_user()
        self.done_at = now_iso() if done else ""
        self.done_by = who if done else ""
        self.updated_by, self.updated_at = who, now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {"schema": 1, "id": self.id, "title": self.title, "owner": self.owner, "due": self.due,
                "created_by": self.created_by, "created_at": self.created_at, "updated_by": self.updated_by,
                "updated_at": self.updated_at, "done_at": self.done_at, "done_by": self.done_by,
                "link": self.link.to_dict() if self.link else None, "note": self.note,
                "mentions": list(self.mentions)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Task:
        d = _dict(d)
        return cls(title=_s(d, "title", "Untitled task").strip() or "Untitled task", owner=_s(d, "owner"),
                   due=_s(d, "due")[:10], id=_s(d, "id") or new_id(), created_by=_s(d, "created_by"),
                   created_at=_s(d, "created_at") or now_iso(), updated_by=_s(d, "updated_by"),
                   updated_at=_s(d, "updated_at") or now_iso(), done_at=_s(d, "done_at"), done_by=_s(d, "done_by"),
                   link=TaskLink.from_dict(d.get("link")), note=_s(d, "note"), mentions=_strs(d.get("mentions")))


# ------------------------------------------------------------------ watchers
@dataclass
class Notify:
    """Who hears about a watcher hit.  A toast shows whenever ``toast`` is on."""
    toast: bool = True
    mentions: list[str] = field(default_factory=list)  # "@priya", "@checkers": written to their inboxes
    cliq_dm: bool = False              # DM the watcher's owner (and mentioned people who linked Cliq)
    cliq_channel: str = ""             # also post to this channel ("" = no)

    def to_dict(self) -> dict[str, Any]:
        return {"toast": self.toast, "mentions": list(self.mentions), "cliq_dm": self.cliq_dm,
                "cliq_channel": self.cliq_channel}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> Notify:
        d = _dict(d)
        return cls(bool(d.get("toast", True)), _strs(d.get("mentions")), bool(d.get("cliq_dm", False)),
                   _s(d, "cliq_channel"))


@dataclass
class Watcher:
    """A rule (brief section 3.4).  ``target`` and ``params`` by kind:

    * folder: target = the folder (variables allowed); params ``pattern`` (glob, "*"), ``recursive`` (False)
    * health: target = a root ("\\\\nas01", "Z:", "{SERVER_ROOT}") or "" for every root this PC uses
    * hub:    target = "" or a published id / login that narrows the events
    * time:   target = ""; params ``at`` (ISO datetime), ``every_days``, ``stale_days``, ``task_id``
    """
    name: str
    kind: str = "folder"
    target: str = ""
    events: list[str] = field(default_factory=list)
    id: str = field(default_factory=new_id)
    interval_s: int = 60               # folder polling period (minimum 10); ignored by event-driven kinds
    params: dict[str, Any] = field(default_factory=dict)
    notify: Notify = field(default_factory=Notify)
    activity_id: str = ""
    project_id: str = ""
    enabled: bool = True
    created_by: str = field(default_factory=current_user)
    created_at: str = field(default_factory=now_iso)

    def __post_init__(self) -> None:
        if not self.events:
            self.events = list(WATCHER_EVENTS.get(self.kind, ()))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "kind": self.kind, "target": self.target,
                "events": list(self.events), "interval_s": self.interval_s, "params": dict(self.params),
                "notify": self.notify.to_dict(), "activity_id": self.activity_id, "project_id": self.project_id,
                "enabled": self.enabled, "created_by": self.created_by, "created_at": self.created_at}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Watcher:
        d = _dict(d)
        kind = _s(d, "kind", "folder")
        if kind not in WATCHER_KINDS:
            kind = "folder"
        allowed = WATCHER_EVENTS[kind]
        events = [e for e in _strs(d.get("events")) if e in allowed] or list(allowed)
        return cls(name=_s(d, "name", "Watcher") or "Watcher", kind=kind, target=_s(d, "target"), events=events,
                   id=_s(d, "id") or new_id(), interval_s=max(10, _i(d, "interval_s", 60) or 60),
                   params=dict(_dict(d.get("params"))), notify=Notify.from_dict(d.get("notify")),
                   activity_id=_s(d, "activity_id"), project_id=_s(d, "project_id"),
                   enabled=bool(d.get("enabled", True)), created_by=_s(d, "created_by"),
                   created_at=_s(d, "created_at") or now_iso())


@dataclass
class WatchEvent:
    """One hit.  ``key`` is the de-duplication key (``delivered/<user>.json`` on the hub)."""
    watcher_id: str
    event: str                         # one of WATCHER_EVENTS[kind]
    title: str
    detail: str = ""
    path: str = ""
    link: str = ""                     # projectopener://... to act on it
    level: str = "info"                # info | warning | critical
    ts: str = field(default_factory=now_iso)
    key: str = ""

    def __post_init__(self) -> None:
        if not self.key:
            self.key = f"{self.watcher_id}:{self.event}:{self.path}:{self.ts}"

    def to_dict(self) -> dict[str, Any]:
        return {"watcher_id": self.watcher_id, "event": self.event, "title": self.title, "detail": self.detail,
                "path": self.path, "link": self.link, "level": self.level, "ts": self.ts, "key": self.key}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WatchEvent:
        d = _dict(d)
        return cls(_s(d, "watcher_id"), _s(d, "event"), _s(d, "title"), _s(d, "detail"), _s(d, "path"),
                   _s(d, "link"), _s(d, "level", "info") or "info", _s(d, "ts") or now_iso(), _s(d, "key"))


# -------------------------------------------------------------------- groups
@dataclass
class Group:
    """``@checkers``: a name and its members, in the hub's ``groups.json`` (anyone may edit)."""
    name: str                          # without the "@"; letters, digits, "-", "_", "."
    members: list[str] = field(default_factory=list)   # logins, no "@"
    color: str = ""
    created_by: str = field(default_factory=current_user)
    updated_by: str = field(default_factory=current_user)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "members": list(self.members), "color": self.color,
                "created_by": self.created_by, "updated_by": self.updated_by, "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Group:
        d = _dict(d)
        members: list[str] = []
        for m in _strs(d.get("members")):
            m = m.lstrip("@").strip()
            if m and m not in members:
                members.append(m)
        return cls(_s(d, "name").lstrip("@").strip() or "group", members, _color_or(d.get("color")),
                   _s(d, "created_by"), _s(d, "updated_by"), _s(d, "updated_at") or now_iso())


# ----------------------------------------------------------------- profiles
@dataclass
class LaunchProfile:
    """A named way to start a CAD application (brief section 3.6): arguments, folder, environment."""
    name: str
    app: str = "other"                 # navisworks | microstation | autocad | caesar | other
    exe: str = ""                      # "" = the item's own path
    args: str = ""                     # may contain {VARIABLES} and {ITEM} (the item's resolved path)
    cwd: str = ""
    env: dict[str, str] = field(default_factory=dict)
    description: str = ""
    id: str = field(default_factory=new_id)
    author: str = field(default_factory=current_user)
    published_id: str = ""             # hub profiles/<id>.json when shared
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "app": self.app, "exe": self.exe, "args": self.args,
                "cwd": self.cwd, "env": dict(self.env), "description": self.description, "author": self.author,
                "published_id": self.published_id, "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LaunchProfile:
        d = _dict(d)
        app = _s(d, "app", "other")
        env = {str(k): str(v) for k, v in _dict(d.get("env")).items()}
        return cls(name=_s(d, "name", "Profile") or "Profile", app=app if app in PROFILE_APPS else "other",
                   exe=_s(d, "exe"), args=_s(d, "args"), cwd=_s(d, "cwd"), env=env,
                   description=_s(d, "description"), id=_s(d, "id") or new_id(), author=_s(d, "author"),
                   published_id=_s(d, "published_id"), updated_at=_s(d, "updated_at") or now_iso())


# ------------------------------------------------------------ office health
@dataclass
class RootObservation:
    root: str                          # "\\\\nas01" | "Z:" | "{SERVER_ROOT}"
    status: str = "ok"                 # ok | missing | offline | variable
    since: str = ""                    # when this PC first saw the current status
    jobs: list[str] = field(default_factory=list)   # job numbers / project titles using it on this PC
    items: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"root": self.root, "status": self.status, "since": self.since, "jobs": list(self.jobs),
                "items": self.items}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RootObservation:
        d = _dict(d)
        return cls(_s(d, "root"), _s(d, "status", "ok") or "ok", _s(d, "since"), _strs(d.get("jobs")), _i(d, "items"))


@dataclass
class HealthObservation:
    """``watch/<user>.json``: the path health one PC observed (brief section 3.4)."""
    user: str = field(default_factory=current_user)
    host: str = field(default_factory=current_host)
    ts: str = field(default_factory=now_iso)
    roots: list[RootObservation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": 1, "user": self.user, "host": self.host, "ts": self.ts,
                "roots": [r.to_dict() for r in self.roots]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HealthObservation:
        d = _dict(d)
        return cls(_s(d, "user"), _s(d, "host"), _s(d, "ts") or now_iso(),
                   [RootObservation.from_dict(r) for r in d.get("roots", []) or [] if isinstance(r, dict)])


# ----------------------------------------------------------------- workspace
@dataclass
class Workspace:
    """``workspace.json`` schema 4 as one object (``WorkspaceStore`` keeps the lists)."""
    projects: list[Project] = field(default_factory=list)
    activities: list[Activity] = field(default_factory=list)
    profiles: list[LaunchProfile] = field(default_factory=list)
    watchers: list[Watcher] = field(default_factory=list)
    migration: dict[str, Any] = field(default_factory=dict)   # report of the 3 -> 4 migration, kept for support
    schema: int = 4

    def to_dict(self, app_version: str = "") -> dict[str, Any]:
        return {"schema": self.schema, "app_version": app_version, "saved_at": now_iso(),
                "projects": [p.to_dict() for p in self.projects],
                "activities": [a.to_dict() for a in self.activities],
                "profiles": [p.to_dict() for p in self.profiles],
                "watchers": [w.to_dict() for w in self.watchers],
                "migration": dict(self.migration)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Workspace:
        d = _dict(d)

        def objs(key: str, fn: Any) -> list[Any]:
            return [fn(x) for x in d.get(key, []) or [] if isinstance(x, dict)]

        return cls(projects=objs("projects", Project.from_dict), activities=objs("activities", Activity.from_dict),
                   profiles=objs("profiles", LaunchProfile.from_dict), watchers=objs("watchers", Watcher.from_dict),
                   migration=dict(_dict(d.get("migration"))), schema=_i(d, "schema", 3) or 3)
