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

Every writer owns its own files (per-user names) so there is no locking.
Shared files that several people may edit (published projects,
announcements) are small and written atomically; the last writer wins and the
``revision`` counter makes conflicts visible.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from project_opener import constants as C
from project_opener.core import models as M
from project_opener.core.jsonio import append_jsonl, read_json, read_jsonl, write_json_atomic

log = logging.getLogger(__name__)

HUB_SCHEMA = 1


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
            for sub in ("users", "published", "inbox", "pulse", "updates"):
                (self.root / sub).mkdir(parents=True, exist_ok=True)  # type: ignore[operator]
            meta = self.root / "hub.json"  # type: ignore[operator]
            if not meta.exists():
                write_json_atomic(meta, {"schema": HUB_SCHEMA, "name": "Dexterity Team Hub",
                                         "created_by": self.user, "created_at": M.now_iso()})
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
    def heartbeat(self, current_project: str = "", status: str = "") -> None:
        if not self.configured:
            return
        try:
            (self.root / "users").mkdir(parents=True, exist_ok=True)  # type: ignore[operator]
            write_json_atomic(self.root / "users" / f"{self.user}.json", {  # type: ignore[operator]
                "user": self.user, "display_name": self.display_name, "role": self.role, "host": self.host,
                "version": C.VERSION, "ts": time.time(), "iso": M.now_iso(),
                "current_project": current_project, "status": status,
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
    def publish(self, project: M.Project, portable_fn=None, description: str = "") -> PublishedProject | None:
        """Publish (or re-publish) a project for the whole team."""
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
        payload = {
            "schema": HUB_SCHEMA, "published_id": pid, "author": self.user, "author_name": self.display_name,
            "published_at": M.now_iso(), "revision": revision, "description": description or project.description,
            "project": data,
        }
        path = self.root / "published" / f"{pid}.json"  # type: ignore[operator]
        write_json_atomic(path, payload)
        project.origin = M.Origin(source="team", author=self.user, published_id=pid,
                                  published_at=payload["published_at"], revision=revision)
        self.pulse("published", f"{project.title} rev {revision}" + (f" (was rev {revision - 1})" if revision > 1 else ""))
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
                "schema": HUB_SCHEMA, "id": mid, "from": self.user, "from_name": self.display_name, "to": to_user,
                "sent_at": M.now_iso(), "message": message, "project": data,
            })
            self.pulse("sent", f"{project.title} → {self.display_name_for(to_user)}")
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

    def announce(self, title: str, body: str, level: str = "info", expires: str = "") -> Announcement | None:
        if not self.initialise():
            return None
        items = [a.to_dict() for a in self.announcements(include_expired=True)]
        a = Announcement(M.new_id(), title, body, self.user, M.now_iso(), level, expires)
        items.insert(0, a.to_dict())
        write_json_atomic(self.root / "announcements.json", {"schema": HUB_SCHEMA, "items": items[:50]})  # type: ignore[operator]
        return a

    def remove_announcement(self, ann_id: str) -> None:
        if not self.reachable():
            return
        items = [a.to_dict() for a in self.announcements(include_expired=True) if a.id != ann_id]
        write_json_atomic(self.root / "announcements.json", {"schema": HUB_SCHEMA, "items": items})  # type: ignore[operator]

    # ----------------------------------------------------------------- pulse
    def pulse(self, event: str, detail: str = "") -> None:
        if not self.configured:
            return
        try:
            (self.root / "pulse").mkdir(parents=True, exist_ok=True)  # type: ignore[operator]
            append_jsonl(self.root / "pulse" / f"{self.user}.jsonl",  # type: ignore[operator]
                         {"ts": M.now_iso(), "user": self.user, "name": self.display_name, "event": event, "detail": detail})
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
