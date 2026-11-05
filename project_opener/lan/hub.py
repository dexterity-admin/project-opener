"""Team Hub - collaboration over a plain shared folder.

The office already has SMB shares, so the hub needs no server process.  The
layout under the hub root is::

    hub.json                 identity + schema
    users/<user>.json        heartbeat: who is online, on which machine/version
    published/<id>.json      team projects anyone can clone or subscribe to
    inbox/<user>/<id>.json   projects sent directly to one colleague
    announcements.json       admin notices shown on every dashboard
    pulse/<user>.jsonl       opt-in activity feed (who launched what)
    updates/latest.json      LAN update mirror (see project_opener.update)

4.x adds (hub schema 2, docs/V4-ARCHITECTURE.md section 3.3 and docs/LAN-HUB.md)::

    groups.json              @groups (lan.groups)
    published/<id>.json      + "type" (project | activity), "for"; activities carry "activity"
    inbox/<user>/<id>.json   + "kind" (project | activity | mention | task)
    tasks/<id>.json          one file per task (core.tasks)
    watch/<user>.json        office-wide path health (lan.healthboard)
    delivered/<user>.json    alert de-duplication ledger (lan.delivery)
    profiles/<id>.json       shared launch profiles

Every writer owns its own files (per-user names) so there is no locking.
Shared files that several people may edit (published projects,
announcements) are small and written atomically; the last writer wins and the
``revision`` counter makes conflicts visible.
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from project_opener import constants as C
from project_opener.core import mentions as MN
from project_opener.core import models as M
from project_opener.core.jsonio import append_jsonl, read_json, read_jsonl, write_json_atomic

log = logging.getLogger(__name__)

HUB_SCHEMA = 1                 # files 3.2 also reads (published projects, project inbox entries)
HUB_SCHEMA_V4 = C.HUB_SCHEMA_V4  # hub.json and the files only 4.x reads
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._$-]{0,63}$")
PULSE_KINDS = ("launched", "published", "sent", "task", "mention", "watch")


def safe_name(name: str) -> bool:
    """A login / id that may name a file or folder on the hub (no separators, no "..")."""
    return bool(SAFE_NAME_RE.match(name or "")) and ".." not in name


@dataclass
class PublishedActivity:
    published_id: str
    author: str
    published_at: str
    revision: int
    activity: M.Activity
    description: str = ""
    for_targets: list[str] = field(default_factory=list)
    projects: list[dict[str, str]] = field(default_factory=list)
    author_name: str = ""
    path: Path | None = None


@dataclass
class Peer:
    user: str
    display_name: str = ""
    role: str = ""
    host: str = ""
    version: str = ""
    ts: float = 0.0
    current_project: str = ""
    status: str = ""
    source: str = "hub"   # hub | udp

    @property
    def online(self) -> bool:
        return (time.time() - self.ts) < C.HUB_STALE_S

    @property
    def label(self) -> str:
        return self.display_name or self.user


@dataclass
class PublishedProject:
    published_id: str
    author: str
    published_at: str
    revision: int
    project: M.Project
    description: str = ""
    path: Path | None = None


@dataclass
class InboxMessage:
    id: str
    sender: str
    sent_at: str
    message: str
    project: M.Project
    path: Path | None = None


@dataclass
class Announcement:
    id: str
    title: str
    body: str
    author: str
    ts: str
    level: str = "info"     # info | warning | critical
    expires: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class HubStatus:
    configured: bool = False
    reachable: bool = False
    path: str = ""
    message: str = ""
    peers_online: int = 0
    published: int = 0
    inbox: int = 0
    announcements: list[Announcement] = field(default_factory=list)


class TeamHub:
    def __init__(self, root: str | Path | None, user: str | None = None, display_name: str = "", role: str = ""):
        self.root = Path(root) if root else None
        self.user = user or M.current_user()
        self.display_name = display_name
        self.role = role
        self.host = M.current_host()
        self._last_error = ""
        # v4 presence fields written by ``heartbeat`` (set by quick.hub_api from Settings)
        self.email = ""
        self.cliq_id = ""
        self.cliq_linked = False
        self.current_activity = ""

    # --------------------------------------------------------------- basics
    @property
    def configured(self) -> bool:
        return self.root is not None and str(self.root).strip() != ""

    def reachable(self) -> bool:
        if not self.configured:
            return False
        try:
            return self.root.exists()  # type: ignore[union-attr]
        except OSError:
            return False

    def initialise(self) -> bool:
        """Create the folder layout. Safe to call repeatedly."""
        if not self.configured:
            return False
        try:
            for sub in ("users", "published", "inbox", "pulse", "updates", *self.V4_DIRS):
                (self.root / sub).mkdir(parents=True, exist_ok=True)  # type: ignore[operator]
            meta = self.root / "hub.json"  # type: ignore[operator]
            if not meta.exists():
                write_json_atomic(meta, {"schema": HUB_SCHEMA_V4, "name": "Dexterity Team Hub",
                                         "created_by": self.user, "created_at": M.now_iso()})
            else:
                d = read_json(meta, {}) or {}
                if isinstance(d, dict) and int(d.get("schema", 1) or 1) < HUB_SCHEMA_V4:
                    d["schema"] = HUB_SCHEMA_V4
                    d["upgraded_by"], d["upgraded_at"] = self.user, M.now_iso()
                    write_json_atomic(meta, d)
            return True
        except OSError as exc:
            self._last_error = str(exc)
            log.warning("hub init failed: %s", exc)
            return False

    def status(self) -> HubStatus:
        st = HubStatus(configured=self.configured, path=str(self.root or ""))
        if not self.configured:
            st.message = "No Team Hub folder set. Choose a shared folder in Settings."
            return st
        st.reachable = self.reachable()
        if not st.reachable:
            st.message = f"Hub folder not reachable: {self.root}"
            return st
        try:
            st.peers_online = sum(1 for p in self.peers() if p.online and p.user != self.user)
            st.published = len(list((self.root / "published").glob("*.json")))  # type: ignore[operator]
            st.inbox = len(self.inbox())
            st.announcements = self.announcements()
            st.message = "Connected"
        except OSError as exc:
            st.reachable = False
            st.message = str(exc)
        return st

    # ------------------------------------------------------------- presence
    def heartbeat(self, current_project: str = "", status: str = "", current_activity: str | None = None) -> None:
        if not self.configured:
            return
        try:
            (self.root / "users").mkdir(parents=True, exist_ok=True)  # type: ignore[operator]
            write_json_atomic(self.root / "users" / f"{self.user}.json", {  # type: ignore[operator]
                "user": self.user, "display_name": self.display_name, "role": self.role, "host": self.host,
                "version": C.VERSION, "ts": time.time(), "iso": M.now_iso(),
                "current_project": current_project, "status": status,
                "email": self.email, "cliq_id": self.cliq_id if self.cliq_linked else "",
                "cliq_linked": bool(self.cliq_linked and self.cliq_id),
                "current_activity": self.current_activity if current_activity is None else current_activity,
            })
        except OSError as exc:
            log.debug("heartbeat failed: %s", exc)

    def sign_off(self) -> None:
        if not self.configured:
            return
        try:
            p = self.root / "users" / f"{self.user}.json"  # type: ignore[operator]
            data = read_json(p, {}) or {}
            data["ts"] = 0
            data["status"] = "offline"
            write_json_atomic(p, data)
        except OSError:
            pass

    def display_name_for(self, user: str) -> str:
        """The display name a colleague chose, from their presence file; the login when unknown."""
        if not user:
            return ""
        if user == self.user and self.display_name:
            return self.display_name
        try:
            d = read_json(self.root / "users" / f"{user}.json", {}) if self.root else {}  # type: ignore[operator]
        except OSError:
            d = {}
        name = str(d.get("display_name", "")) if isinstance(d, dict) else ""
        return name or user

    def peers(self) -> list[Peer]:
        if not self.reachable():
            return []
        peers: list[Peer] = []
        try:
            for f in (self.root / "users").glob("*.json"):  # type: ignore[operator]
                d = read_json(f, {})
                if not isinstance(d, dict) or not d.get("user"):
                    continue
                peers.append(Peer(
                    user=str(d["user"]), display_name=str(d.get("display_name", "")), role=str(d.get("role", "")),
                    host=str(d.get("host", "")), version=str(d.get("version", "")), ts=float(d.get("ts", 0) or 0),
                    current_project=str(d.get("current_project", "")), status=str(d.get("status", "")),
                ))
        except OSError as exc:
            log.debug("peers failed: %s", exc)
        peers.sort(key=lambda p: (not p.online, p.label.lower()))
        return peers

    # ------------------------------------------------------------ publishing
    def publish(self, project: M.Project, portable_fn=None, description: str = "",
                for_targets: list[str] | None = None) -> PublishedProject | None:
        """Publish (or re-publish) a project for the whole team.

        ``for_targets`` (logins and group names) are recorded as ``"for"`` and each
        person they reach gets an inbox entry (kind "project", readable by 3.2)."""
        if not self.initialise():
            return None
        pid = project.origin.published_id or M.new_id()
        existing = read_json(self.root / "published" / f"{pid}.json", {}) or {}  # type: ignore[operator]
        revision = int(existing.get("revision", 0) or 0) + 1
        data = project.to_dict()
        if portable_fn:
            for it in data["items"]:
                it["path"] = portable_fn(it["path"])
        data["pinned_at"] = None
        data["auto_launch"] = False
        targets = MN.normalise_targets(for_targets or [])
        payload = {
            "schema": HUB_SCHEMA, "type": "project", "published_id": pid, "author": self.user,
            "author_name": self.display_name, "published_at": M.now_iso(), "revision": revision,
            "description": description or project.description, "for": targets, "project": data,
        }
        path = self.root / "published" / f"{pid}.json"  # type: ignore[operator]
        write_json_atomic(path, payload)
        project.origin = M.Origin(source="team", author=self.user, published_id=pid,
                                  published_at=payload["published_at"], revision=revision)
        reached = self.expand_targets(targets)
        for login in reached:
            self._write_inbox(login, {"kind": "project", "message": payload["description"], "project": data,
                                      "published_id": pid, "revision": revision}, schema=HUB_SCHEMA)
        self.pulse("published", f"{project.title} rev {revision}" + (f" (was rev {revision - 1})" if revision > 1 else ""),
                   kind="published", mentions=targets)
        return PublishedProject(pid, self.user, payload["published_at"], revision, M.Project.from_dict(data),
                                payload["description"], path)

    def unpublish(self, published_id: str) -> bool:
        if not self.reachable():
            return False
        p = self.root / "published" / f"{published_id}.json"  # type: ignore[operator]
        try:
            p.unlink()
            return True
        except OSError:
            return False

    def published(self) -> list[PublishedProject]:
        if not self.reachable():
            return []
        out: list[PublishedProject] = []
        try:
            for f in sorted((self.root / "published").glob("*.json")):  # type: ignore[operator]
                d = read_json(f, {})
                if not isinstance(d, dict) or not isinstance(d.get("project"), dict):
                    continue
                proj = M.Project.from_dict(d["project"])
                proj.origin = M.Origin(source="team", author=str(d.get("author", "")),
                                       published_id=str(d.get("published_id", f.stem)),
                                       published_at=str(d.get("published_at", "")), revision=int(d.get("revision", 1) or 1))
                out.append(PublishedProject(proj.origin.published_id, proj.origin.author, proj.origin.published_at,
                                            proj.origin.revision, proj, str(d.get("description", "")), f))
        except OSError as exc:
            log.debug("published listing failed: %s", exc)
        out.sort(key=lambda p: p.published_at, reverse=True)
        return out

    def newer_revision(self, project: M.Project) -> PublishedProject | None:
        """If a project cloned from the hub has a newer revision upstream, return it."""
        if project.origin.source != "team" or not project.origin.published_id:
            return None
        for pub in self.published():
            if pub.published_id == project.origin.published_id and pub.revision > project.origin.revision:
                return pub
        return None

    # ----------------------------------------------------------------- inbox
    def send(self, to_user: str, project: M.Project, message: str = "", portable_fn=None) -> bool:
        if not self.initialise():
            return False
        data = project.to_dict()
        if portable_fn:
            for it in data["items"]:
                it["path"] = portable_fn(it["path"])
        mid = M.new_id()
        folder = self.root / "inbox" / to_user  # type: ignore[operator]
        try:
            folder.mkdir(parents=True, exist_ok=True)
            write_json_atomic(folder / f"{mid}.json", {
                "schema": HUB_SCHEMA, "id": mid, "kind": "project", "from": self.user, "from_name": self.display_name,
                "to": to_user, "sent_at": M.now_iso(), "message": message, "project": data,
            })
            self.pulse("sent", f"{project.title} → {self.display_name_for(to_user)}", kind="sent", mentions=[to_user])
            return True
        except OSError as exc:
            log.warning("send failed: %s", exc)
            return False

    def inbox(self) -> list[InboxMessage]:
        if not self.reachable():
            return []
        out: list[InboxMessage] = []
        folder = self.root / "inbox" / self.user  # type: ignore[operator]
        try:
            for f in sorted(folder.glob("*.json")):
                d = read_json(f, {})
                if not isinstance(d, dict) or not isinstance(d.get("project"), dict):
                    continue
                proj = M.Project.from_dict(d["project"])
                proj.origin = M.Origin(source="inbox", author=str(d.get("from", "")))
                out.append(InboxMessage(str(d.get("id", f.stem)), str(d.get("from", "")), str(d.get("sent_at", "")),
                                        str(d.get("message", "")), proj, f))
        except OSError:
            pass
        out.sort(key=lambda m: m.sent_at, reverse=True)
        return out

    def dismiss_inbox(self, msg: InboxMessage) -> bool:
        """Delete the inbox file. False when it is locked or the hub is gone."""
        if not msg.path:
            return False
        try:
            msg.path.unlink()
            return True
        except FileNotFoundError:
            return True
        except OSError as exc:
            log.warning("dismiss_inbox failed: %s", exc)
            return False

    # --------------------------------------------------------- announcements
    def announcements(self, include_expired: bool = False) -> list[Announcement]:
        if not self.reachable():
            return []
        d = read_json(self.root / "announcements.json", {}) or {}  # type: ignore[operator]
        items = d.get("items", []) if isinstance(d, dict) else []
        out = []
        now = M.now_iso()
        for raw in items:
            if not isinstance(raw, dict):
                continue
            a = Announcement(str(raw.get("id", M.new_id())), str(raw.get("title", "")), str(raw.get("body", "")),
                             str(raw.get("author", "")), str(raw.get("ts", "")), str(raw.get("level", "info")),
                             str(raw.get("expires", "")))
            if not include_expired and a.expires and a.expires < now:
                continue
            out.append(a)
        out.sort(key=lambda a: a.ts, reverse=True)
        return out

    def announce(self, title: str, body: str, level: str = "info", expires: str = "",
                 mentions: list[str] | None = None) -> Announcement | None:
        """``mentions`` default to the @names in title and body; each person reached gets a mention entry."""
        if not self.initialise():
            return None
        raw = read_json(self.root / "announcements.json", {}) or {}  # type: ignore[operator]
        old = [x for x in (raw.get("items", []) if isinstance(raw, dict) else []) if isinstance(x, dict)]
        names = MN.normalise_targets(mentions if mentions is not None else MN.parse_mentions(f"{title} {body}"))
        a = Announcement(M.new_id(), title, body, self.user, M.now_iso(), level, expires)
        row = a.to_dict()
        row["author_name"] = self.display_name
        row["mentions"] = names
        write_json_atomic(self.root / "announcements.json",  # type: ignore[operator]
                          {"schema": HUB_SCHEMA, "items": [row, *old][:50]})
        if names:
            self.send_mention(self.expand_targets(names), f"{title}: {body}" if body else title,
                              "", title=title)
        return a

    def remove_announcement(self, ann_id: str) -> None:
        if not self.reachable():
            return
        raw = read_json(self.root / "announcements.json", {}) or {}  # type: ignore[operator]
        items = [x for x in (raw.get("items", []) if isinstance(raw, dict) else [])
                 if isinstance(x, dict) and str(x.get("id", "")) != ann_id]
        write_json_atomic(self.root / "announcements.json", {"schema": HUB_SCHEMA, "items": items})  # type: ignore[operator]

    # ----------------------------------------------------------------- pulse
    def pulse(self, event: str, detail: str = "", kind: str = "", mentions: list[str] | None = None,
              task_id: str = "", activity: str = "") -> None:
        """One feed row; 3.2 reads ``event`` and ``detail``, 4.x also ``kind``, ``mentions``, ``task_id``, ``activity``."""
        if not self.configured:
            return
        row: dict[str, Any] = {"ts": M.now_iso(), "user": self.user, "name": self.display_name, "event": event,
                               "detail": detail}
        k = kind or (event if event in PULSE_KINDS else "")
        if k:
            row["kind"] = k
        if mentions:
            row["mentions"] = MN.normalise_targets(mentions)
        if task_id:
            row["task_id"] = task_id
        if activity:
            row["activity"] = activity
        try:
            (self.root / "pulse").mkdir(parents=True, exist_ok=True)  # type: ignore[operator]
            append_jsonl(self.root / "pulse" / f"{self.user}.jsonl", row)  # type: ignore[operator]
        except OSError:
            pass

    def pulse_feed(self, limit: int = 40) -> list[dict[str, Any]]:
        if not self.reachable():
            return []
        rows: list[dict[str, Any]] = []
        try:
            for f in (self.root / "pulse").glob("*.jsonl"):  # type: ignore[operator]
                rows.extend(read_jsonl(f, limit=limit))
        except OSError:
            pass
        rows.sort(key=lambda r: str(r.get("ts", "")), reverse=True)
        return rows[:limit]

    # ------------------------------------------------------------------- v4
    # Owner: builder 1.  File formats: docs/V4-ARCHITECTURE.md section 3.3.  3.2 readers skip
    # what they do not know (published files without "project", inbox files without "project").
    V4_DIRS = ("tasks", "watch", "delivered", "profiles")

    def sub(self, name: str) -> Path | None:
        """``<hub>/<name>`` (tasks, watch, delivered, profiles, groups.json ...); None without a hub."""
        return (self.root / name) if self.configured else None  # type: ignore[operator]

    # ---- people
    def user_records(self) -> dict[str, dict[str, Any]]:
        """login -> the raw ``users/<login>.json`` (heartbeat) of everyone who ever ran 3.x/4.x on the hub."""
        if not self.reachable():
            return {}
        out: dict[str, dict[str, Any]] = {}
        try:
            for f in (self.root / "users").glob("*.json"):  # type: ignore[operator]
                d = read_json(f, {})
                if isinstance(d, dict):
                    out[str(d.get("user") or f.stem).lower()] = d
        except OSError:
            pass
        return out

    def known_users(self) -> list[str]:
        return sorted(self.user_records())

    def groups(self) -> list[M.Group]:
        from project_opener.lan.groups import GroupBook
        return GroupBook(self.root).all() if self.configured else []

    def expand_targets(self, targets: list[str], include_self: bool = False) -> list[str]:
        """Logins reached by ``targets`` (logins and group names), groups expanded one level.

        Unknown names are dropped when the hub knows any users (a typo reaches nobody);
        the sender is left out unless ``include_self``."""
        known = self.known_users()
        logins = MN.expand(targets, self.groups(), known or None, exclude="" if include_self else self.user)
        return [lg for lg in logins if safe_name(lg)]

    def cliq_ids_for(self, logins: list[str]) -> dict[str, str]:
        """login -> Cliq user id, for the people who linked Cliq (``cliq_linked`` in their heartbeat)."""
        recs = self.user_records()
        out = {}
        for lg in logins:
            d = recs.get(lg.lower(), {})
            if d.get("cliq_linked") and d.get("cliq_id"):
                out[lg] = str(d["cliq_id"])
        return out

    # ---- inbox entries of every kind
    def _write_inbox(self, to_user: str, fields: dict[str, Any], schema: int = HUB_SCHEMA_V4) -> str:
        """``inbox/<to_user>/<id>.json``; returns the id ("" when the name is unsafe or the write failed)."""
        if not self.configured or not safe_name(to_user):
            return ""
        mid = M.new_id()
        row = {"schema": schema, "id": mid, "from": self.user, "from_name": self.display_name, "to": to_user,
               "sent_at": M.now_iso(), **fields}
        try:
            folder = self.root / "inbox" / to_user  # type: ignore[operator]
            folder.mkdir(parents=True, exist_ok=True)
            write_json_atomic(folder / f"{mid}.json", row)
            return mid
        except OSError as exc:
            log.warning("inbox write for %s failed: %s", to_user, exc)
            return ""

    def inbox_entries(self) -> list[dict[str, Any]]:
        """Every entry in my inbox as a dict with ``kind`` filled in and ``_path``; newest first.

        Kinds: project (3.x and 4.x), activity, mention, task.  Unknown or broken files are skipped."""
        if not self.reachable():
            return []
        out: list[dict[str, Any]] = []
        folder = self.root / "inbox" / self.user  # type: ignore[operator]
        try:
            files = sorted(folder.glob("*.json"))
        except OSError:
            return out
        for f in files:
            d = read_json(f, None)
            if not isinstance(d, dict):
                continue
            kind = str(d.get("kind") or ("project" if isinstance(d.get("project"), dict) else ""))
            if kind in ("project",) and not isinstance(d.get("project"), dict):
                continue
            if kind == "activity" and not isinstance(d.get("activity"), dict):
                continue
            if kind not in ("project", "activity", "mention", "task"):
                continue
            d = dict(d)
            d["kind"] = kind
            d["id"] = str(d.get("id") or f.stem)
            d["_path"] = f
            out.append(d)
        out.sort(key=lambda r: str(r.get("sent_at", "")), reverse=True)
        return out

    def dismiss_entry(self, entry_id: str) -> bool:
        """Delete ``inbox/<me>/<id>.json``; True when it is gone."""
        if not self.configured or not safe_name(entry_id):
            return False
        p = self.root / "inbox" / self.user / f"{entry_id}.json"  # type: ignore[operator]
        try:
            p.unlink()
            return True
        except FileNotFoundError:
            return True
        except OSError as exc:
            log.warning("dismiss failed: %s", exc)
            return False

    # ---- published activities
    def publish_activity(self, activity: M.Activity, portable_fn=None, description: str = "",
                         for_targets: list[str] | None = None,
                         projects: list[M.Project] | None = None) -> PublishedActivity | None:
        """``published/<id>.json`` with ``"type": "activity"``, ``"activity": {...}`` and ``"for"``;
        each expanded target also gets an inbox entry (kind "activity").

        Paths go out portable exactly as projects' do (``portable_fn``: drive letter -> UNC).
        Anyone may republish a published activity (last writer wins; the revision counts up)."""
        if not self.initialise():
            return None
        pid = activity.origin.published_id or M.new_id()
        if not safe_name(pid):
            pid = M.new_id()
        path = self.root / "published" / f"{pid}.json"  # type: ignore[operator]
        existing = read_json(path, {}) or {}
        revision = int(existing.get("revision", 0) or 0) + 1 if isinstance(existing, dict) else 1
        data = activity.to_dict()
        if portable_fn:
            for it in data["items"]:
                it["path"] = portable_fn(it["path"])
        data.update(pinned_at=None, last_opened=None, open_count=0, favorite=False)
        data["origin"] = M.Origin(source="team", author=self.user, published_id=pid, revision=revision).to_dict()
        proj_rows = [{"id": p.id, "title": p.title, "job_number": p.job_number} for p in projects or []]
        if not proj_rows and isinstance(existing, dict) and isinstance(existing.get("projects"), list):
            proj_rows = [p for p in existing["projects"] if isinstance(p, dict)]   # a republish keeps the job spine
        targets = MN.normalise_targets(for_targets or [])
        payload = {
            "schema": HUB_SCHEMA_V4, "type": "activity", "published_id": pid, "author": self.user,
            "author_name": self.display_name, "published_at": M.now_iso(), "revision": revision,
            "description": description or activity.description, "for": targets, "activity": data,
            "projects": proj_rows,
        }
        write_json_atomic(path, payload)
        activity.origin = M.Origin(source="team", author=self.user, published_id=pid,
                                   published_at=payload["published_at"], revision=revision)
        for login in self.expand_targets(targets):
            self._write_inbox(login, {"kind": "activity", "message": payload["description"], "activity": data,
                                      "published_id": pid, "revision": revision, "projects": proj_rows})
        self.pulse("published", f"{activity.name} rev {revision}", kind="published", mentions=targets,
                   activity=activity.name)
        return PublishedActivity(pid, self.user, payload["published_at"], revision, M.Activity.from_dict(data),
                                 payload["description"], targets, proj_rows, self.display_name, path)

    def published_activities(self) -> list[PublishedActivity]:
        if not self.reachable():
            return []
        out: list[PublishedActivity] = []
        try:
            files = sorted((self.root / "published").glob("*.json"))  # type: ignore[operator]
        except OSError:
            return out
        for f in files:
            d = read_json(f, {})
            if not isinstance(d, dict) or d.get("type") != "activity" or not isinstance(d.get("activity"), dict):
                continue
            act = M.Activity.from_dict(d["activity"])
            pid = str(d.get("published_id") or f.stem)
            act.origin = M.Origin(source="team", author=str(d.get("author", "")), published_id=pid,
                                  published_at=str(d.get("published_at", "")), revision=int(d.get("revision", 1) or 1))
            projs = [{"id": str(p.get("id", "")), "title": str(p.get("title", "")),
                      "job_number": str(p.get("job_number", ""))}
                     for p in d.get("projects", []) or [] if isinstance(p, dict)]
            out.append(PublishedActivity(pid, act.origin.author, act.origin.published_at, act.origin.revision, act,
                                         str(d.get("description", "")), MN.normalise_targets(d.get("for") or []),
                                         projs, str(d.get("author_name", "")), f))
        out.sort(key=lambda p: p.published_at, reverse=True)
        return out

    def published_for(self) -> dict[str, list[str]]:
        """published id -> its ``for`` list (projects and activities)."""
        out: dict[str, list[str]] = {}
        if not self.reachable():
            return out
        try:
            for f in (self.root / "published").glob("*.json"):  # type: ignore[operator]
                d = read_json(f, {})
                if isinstance(d, dict):
                    out[str(d.get("published_id") or f.stem)] = MN.normalise_targets(d.get("for") or [])
        except OSError:
            pass
        return out

    def send_activity(self, to_users: list[str], activity: M.Activity, message: str = "", portable_fn=None) -> int:
        """Send an activity to people (already expanded logins); returns how many inboxes got it."""
        if not self.initialise():
            return 0
        data = activity.to_dict()
        if portable_fn:
            for it in data["items"]:
                it["path"] = portable_fn(it["path"])
        data.update(pinned_at=None, last_opened=None, open_count=0)
        n = sum(1 for lg in to_users if self._write_inbox(lg, {"kind": "activity", "message": message, "activity": data}))
        if n:
            self.pulse("sent", f"{activity.name} → {', '.join(self.display_name_for(u) for u in to_users)}",
                       kind="sent", mentions=to_users, activity=activity.name)
        return n

    # ---- mentions and task notes
    def send_mention(self, to_users: list[str], text: str, link: str = "", kind: str = "mention",
                     task_id: str = "", title: str = "") -> int:
        """Inbox entries without a project (kind mention | task); returns how many were written."""
        if not self.initialise():
            return 0
        kind = kind if kind in ("mention", "task") else "mention"
        fields: dict[str, Any] = {"kind": kind, "text": text, "link": link}
        if title:
            fields["title"] = title
        if kind == "task":
            fields["task_id"] = task_id
        n = 0
        for login in to_users:
            if login.lower() == self.user.lower():
                continue
            if self._write_inbox(login, fields):
                n += 1
        return n

    def mentions(self) -> list[dict[str, Any]]:
        """My inbox entries of kind mention/task, newest first."""
        return [e for e in self.inbox_entries() if e["kind"] in ("mention", "task")]

    # ---- shared launch profiles
    def publish_profile(self, profile: M.LaunchProfile) -> str:
        """``profiles/<id>.json`` (anyone may update; last writer wins); returns the published id."""
        if not self.initialise():
            return ""
        pid = profile.published_id if safe_name(profile.published_id) else profile.id
        if not safe_name(pid):
            pid = M.new_id()
        data = profile.to_dict()
        data.update(schema=HUB_SCHEMA_V4, published_id=pid, updated_by=self.user, updated_at=M.now_iso())
        write_json_atomic(self.root / "profiles" / f"{pid}.json", data)  # type: ignore[operator]
        profile.published_id = pid
        return pid

    def shared_profiles(self) -> list[M.LaunchProfile]:
        if not self.reachable():
            return []
        out = []
        try:
            for f in sorted((self.root / "profiles").glob("*.json")):  # type: ignore[operator]
                d = read_json(f, None)
                if isinstance(d, dict) and d.get("name"):
                    lp = M.LaunchProfile.from_dict(d)
                    lp.published_id = lp.published_id or f.stem
                    out.append(lp)
        except OSError:
            pass
        return out

    # --------------------------------------------------------------- updates
    def updates_dir(self) -> Path | None:
        return (self.root / "updates") if self.configured else None  # type: ignore[operator]

    def disk_usage(self) -> tuple[int, int] | None:
        if not self.reachable():
            return None
        try:
            st = os.statvfs(self.root) if hasattr(os, "statvfs") else None  # type: ignore[arg-type]
            if st:
                return st.f_frsize * st.f_bavail, st.f_frsize * st.f_blocks
            import shutil
            u = shutil.disk_usage(self.root)  # type: ignore[arg-type]
            return u.free, u.total
        except OSError:
            return None
