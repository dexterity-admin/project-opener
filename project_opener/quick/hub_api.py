"""``app.hub``: people, publishing with "for", inbox and mentions, groups, announcements, pulse, register.
Owner: builder 1 (CORE+HUB).

Wraps ``lan.hub.TeamHub`` (+ ``lan.groups``) on the pool; refreshes on the 3.2
heartbeat (``app.ctx.hub_changed``) and its own timer for groups and mentions.

Every hub read and write runs on the pool (``app.run_async``); models change on
the GUI thread in the ``done`` callbacks.  New inbox entries are toasted once per
user across PCs through the delivery ledger (``lan.delivery.Dispatcher.receive``).
"""
from __future__ import annotations

import logging
import time
import zlib
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from project_opener import constants as C
from project_opener.core import mentions as MN
from project_opener.core import models as M
from project_opener.core.tasks import when_text
from project_opener.lan.groups import GroupBook, clean_name
from project_opener.lan.hub import PublishedActivity, PublishedProject, TeamHub
from project_opener.quick.base import ApiBase, ro
from project_opener.quick.listmodel import DictListModel

log = logging.getLogger(__name__)

PEER_ROLES = ("login", "displayName", "role", "host", "online", "doing", "initials", "hue", "cliqLinked")
PUBLISHED_ROLES = (
    "publishedId", "type", "title", "spine", "author", "authorName", "revision", "publishedAt", "publishedText",
    "forText", "description", "isMine", "cloned", "itemCount",
)
INBOX_ROLES = ("messageId", "kind", "sender", "senderName", "sentAt", "sentText", "message", "title", "mentionsMe",
               "link")
ANNOUNCEMENT_ROLES = ("announcementId", "title", "body", "level", "author", "authorName", "ts", "tsText", "mine")
GROUP_ROLES = ("groupName", "members", "memberCount", "dotColor", "updatedBy")
MENTION_ROLES = ("login", "displayName", "role", "online", "isGroup", "memberCount")
PULSE_ROLES = ("ts", "tsText", "login", "displayName", "event", "detail", "mentionsMe")
REGISTER_ROLES = ("job", "event", "revision", "by", "when", "whenText")

TOAST_BACKLOG_S = 3 * 24 * 3600     # older unseen inbox entries are recorded silently, not toasted
MIN_REFRESH_GAP_S = 15


def initials(name: str) -> str:
    parts = [p for p in (name or "").replace(".", " ").replace("_", " ").split() if p]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else parts[0][1:2])).upper()


def hue(login: str) -> int:
    return zlib.crc32((login or "").lower().encode("utf-8")) % 360


def link_for(kind: str, key: str) -> str:
    """``projectopener://<kind>/<key>``; across PCs the key is a name (local ids differ per PC)."""
    from project_opener.ipc import make_link
    return make_link(kind, key)


class HubApi(ApiBase):
    hubChanged = Signal()
    peersChanged = Signal()
    inboxChanged = Signal()
    groupsChanged = Signal()
    mentioned = Signal(str, str, str)        # from login, text, link (toast + sidebar count)

    def __init__(self, app: Any):
        super().__init__(app)
        self._peers = DictListModel(PEER_ROLES, key="login", parent=self)
        self._published = DictListModel(PUBLISHED_ROLES, key="publishedId", parent=self)
        self._inbox = DictListModel(INBOX_ROLES, key="messageId", parent=self)
        self._announcements = DictListModel(ANNOUNCEMENT_ROLES, key="announcementId", parent=self)
        self._groups = DictListModel(GROUP_ROLES, key="groupName", parent=self)
        self._mention_candidates = DictListModel(MENTION_ROLES, key="login", parent=self)
        self._pulse = DictListModel(PULSE_ROLES, key="ts", parent=self)
        self._register = DictListModel(REGISTER_ROLES, key="job", parent=self)
        self._configured = False
        self._reachable = False
        self._status_text = ""
        self._peers_online = 0
        self._inbox_count = 0
        self._mention_count = 0
        # caches filled by refresh (GUI thread)
        self._users: dict[str, dict[str, Any]] = {}
        self._group_list: list[M.Group] = []
        self._entries: dict[str, dict[str, Any]] = {}
        self._pubs: dict[str, PublishedProject | PublishedActivity] = {}
        self._revisions: dict[str, int] | None = None     # published id -> revision at the last refresh
        self._query = ""
        self._refreshing = False
        self._last_refresh = 0.0
        self._timer: QTimer | None = None
        # The v4 presence fields (e-mail, Cliq id) ride on every heartbeat, including the first one
        # ctx.start writes before any hub call: without them colleagues cannot DM this user for a minute.
        self._hub()

    # ------------------------------------------------------------- models
    @Property(QObject, constant=True)
    def peers(self) -> DictListModel:
        return self._peers

    @Property(QObject, constant=True)
    def published(self) -> DictListModel:
        """Projects and activities on the hub (``type``: project | activity)."""
        return self._published

    @Property(QObject, constant=True)
    def inbox(self) -> DictListModel:
        """Sent items, mentions, task assignments (``kind``: project | activity | mention | task)."""
        return self._inbox

    @Property(QObject, constant=True)
    def announcements(self) -> DictListModel:
        return self._announcements

    @Property(QObject, constant=True)
    def groups(self) -> DictListModel:
        return self._groups

    @Property(QObject, constant=True)
    def mentionCandidates(self) -> DictListModel:
        """The @ picker: people and groups narrowed by ``setMentionQuery``; online first."""
        return self._mention_candidates

    @Property(QObject, constant=True)
    def pulse(self) -> DictListModel:
        return self._pulse

    @Property(QObject, constant=True)
    def register(self) -> DictListModel:
        """The Activity register: Event · Rev · By · When under each job."""
        return self._register

    # --------------------------------------------------------- properties
    configured = ro(bool, "_configured", hubChanged)
    reachable = ro(bool, "_reachable", hubChanged)
    statusText = ro(str, "_status_text", hubChanged)
    peersOnline = ro(int, "_peers_online", peersChanged)
    inboxCount = ro(int, "_inbox_count", inboxChanged)
    mentionCount = ro(int, "_mention_count", inboxChanged)

    # ------------------------------------------------------------ helpers
    @property
    def ctx(self) -> Any:
        return self.app.ctx

    @property
    def me(self) -> str:
        return self.ctx.user

    def _hub(self) -> TeamHub:
        """The context's hub with this PC's v4 presence fields set from Settings."""
        hub = self.ctx.hub
        st = self.ctx.settings
        hub.email = st.email
        hub.cliq_id = st.cliq_user_id
        hub.cliq_linked = bool(st.cliq_user_id and st.notify_cliq_default)
        # (an app without a capture API, as in the hub tests, simply has no current activity)
        hub.current_activity = str(getattr(getattr(self.app, "capture", None), "runningName", "") or "")
        return hub

    def _dispatcher(self) -> Any:
        return self.app.watchers.dispatcher()

    def _portable(self) -> Any:
        return self.ctx.resolver.portable

    def name_for(self, login: str) -> str:
        if not login:
            return ""
        if login == self.me:
            return self.ctx.display_name()
        d = self._users.get(login.lower(), {})
        return str(d.get("display_name") or "") or login

    def _toast(self, title: str, body: str = "", level: str = "info") -> None:
        try:
            self.app.toast.emit(title, body, level)
        except Exception:  # noqa: BLE001
            log.info("%s: %s", title, body)

    # ---------------------------------------------------------- lifecycle
    def start(self) -> None:
        self.ctx.hub_changed.connect(lambda _s: self.refresh())
        changed = getattr(getattr(self.app, "settings", None), "changed", None)
        if changed is not None:
            changed.connect(lambda _key: self._hub())                    # e-mail / Cliq id / hub path edits
        self.ctx.peers_changed.connect(lambda _p: self._sync_peers())
        self._timer = QTimer(self)
        self._timer.setInterval(C.HUB_TASKS_REFRESH_S * 1000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def shutdown(self) -> None:
        if self._timer:
            self._timer.stop()

    # -------------------------------------------------------------- slots
    @Slot()
    def refresh(self) -> None:
        if self._refreshing or time.monotonic() - self._last_refresh < MIN_REFRESH_GAP_S and self._last_refresh:
            return
        self._refreshing = True
        hub = self._hub()
        dispatcher = self._dispatcher() if hub.configured else None

        def work() -> dict[str, Any]:
            if not hub.configured:
                return {"configured": False}
            if not hub.reachable():
                return {"configured": True, "reachable": False}
            hub.initialise()
            entries = hub.inbox_entries()
            fresh = dispatcher.receive(entries) if dispatcher else []
            return {
                "configured": True, "reachable": True, "users": hub.user_records(), "groups": hub.groups(),
                "projects": hub.published(), "activities": hub.published_activities(), "fors": hub.published_for(),
                "entries": entries, "fresh": fresh, "announcements": hub.announcements(),
                "ann_raw": _announcement_extras(hub), "pulse": hub.pulse_feed(60),
            }

        def done(res: dict[str, Any]) -> None:
            self._refreshing = False
            self._last_refresh = time.monotonic()
            self._apply(res)

        def fail(exc: Exception) -> None:
            self._refreshing = False
            log.warning("hub refresh failed: %s", exc)
            self._set_status(hub.configured, False, f"Hub refresh failed: {exc}")

        self.app.run_async(work, done, fail)

    def _set_status(self, configured: bool, reachable: bool, text: str) -> None:
        changed = (self._configured, self._reachable, self._status_text) != (configured, reachable, text)
        self._configured, self._reachable, self._status_text = configured, reachable, text
        if changed:
            self.hubChanged.emit()

    def _apply(self, res: dict[str, Any]) -> None:
        if not res.get("configured"):
            self._set_status(False, False, "No Team Hub folder set. Choose a shared folder in Settings.")
            return
        if not res.get("reachable"):
            self._set_status(True, False, f"Hub folder not reachable: {self.ctx.hub.root}")
            return
        self._users = res["users"]
        self._group_list = res["groups"]
        self._set_status(True, True, "Connected")
        self._sync_peers()
        self._sync_groups()
        self._sync_published(res["projects"], res["activities"], res["fors"])
        self._sync_inbox(res["entries"])
        self._sync_announcements(res["announcements"], res["ann_raw"])
        self._sync_pulse(res["pulse"])
        self.setMentionQuery(self._query)
        self._announce_fresh(res["fresh"])

    # ---- models
    def _sync_peers(self) -> None:
        rows = []
        online = 0
        for p in self.ctx.peers:
            rec = self._users.get(p.user.lower(), {})
            doing = str(rec.get("current_activity") or "") or p.current_project
            if p.user.lower() == self.me.lower():
                continue                 # the Office footlight lists colleagues only (V4-SEAMS, builder 4 ask 5)
            if p.online:
                online += 1
            rows.append({"login": p.user, "displayName": p.label, "role": p.role, "host": p.host, "online": p.online,
                         "doing": doing, "initials": initials(p.label), "hue": hue(p.user),
                         "cliqLinked": bool(rec.get("cliq_linked"))})
        self._peers.sync(rows)
        if self._peers_online != online:
            self._peers_online = online
        self.peersChanged.emit()

    def _sync_groups(self) -> None:
        self._groups.sync([{"groupName": g.name, "members": list(g.members), "memberCount": len(g.members),
                            "dotColor": g.color, "updatedBy": self.name_for(g.updated_by)} for g in self._group_list])
        self.groupsChanged.emit()

    def _local_clone_ids(self) -> set[str]:
        store = self.ctx.store
        return {p.origin.published_id for p in store.projects if p.origin.published_id} | \
               {a.origin.published_id for a in store.activities if a.origin.published_id}

    def _sync_published(self, projects: list[PublishedProject], activities: list[PublishedActivity],
                        fors: dict[str, list[str]]) -> None:
        cloned = self._local_clone_ids()
        rows: list[dict[str, Any]] = []
        self._pubs = {}
        register: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        for pub in projects:
            self._pubs[pub.published_id] = pub
            proj = pub.project
            spine = proj.job_number or proj.title
            rows.append(self._pub_row(pub.published_id, "project", proj.title, spine, pub.author, pub.revision,
                                      pub.published_at, fors.get(pub.published_id, []), pub.description,
                                      pub.published_id in cloned, len(proj.items)))
            register.append(self._register_row(spine, pub.revision, pub.author, pub.published_at))
            events.append({"published_id": pub.published_id, "type": "project", "title": proj.title,
                           "author": pub.author, "author_name": self.name_for(pub.author), "revision": pub.revision})
        for pa in activities:
            self._pubs[pa.published_id] = pa
            act = pa.activity
            spine = pa.projects[0]["job_number"] or pa.projects[0]["title"] if pa.projects else ""
            title = f"{spine} · {act.name}" if spine else act.name
            rows.append(self._pub_row(pa.published_id, "activity", act.name, spine, pa.author, pa.revision,
                                      pa.published_at, pa.for_targets, pa.description, pa.published_id in cloned,
                                      len(act.items)))
            register.append(self._register_row(spine or act.name, pa.revision, pa.author, pa.published_at))
            events.append({"published_id": pa.published_id, "type": "activity", "title": title,
                           "author": pa.author, "author_name": self.name_for(pa.author), "revision": pa.revision})
        rows.sort(key=lambda r: r["publishedAt"], reverse=True)
        self._published.sync(rows)
        register.sort(key=lambda r: r["when"], reverse=True)
        self._register.reset(register)
        current = {e["published_id"]: int(e["revision"]) for e in events}
        if self._revisions is not None:
            new = [e for e in events if e["author"] != self.me
                   and current[e["published_id"]] > self._revisions.get(e["published_id"], 0)]
            if new:
                self._push_hub_events(published=new)
        self._revisions = current

    def _pub_row(self, pid: str, type_: str, title: str, spine: str, author: str, revision: int, at: str,
                 fors: list[str], description: str, cloned: bool, count: int) -> dict[str, Any]:
        return {"publishedId": pid, "type": type_, "title": title, "spine": spine, "author": author,
                "authorName": self.name_for(author), "revision": revision, "publishedAt": at,
                "publishedText": when_text(at), "forText": ", ".join(f"@{t}" for t in fors),
                "description": description, "isMine": author == self.me, "cloned": cloned, "itemCount": count}

    def _register_row(self, job: str, revision: int, author: str, at: str) -> dict[str, Any]:
        return {"job": job, "event": "Published" if revision <= 1 else "Republished", "revision": revision,
                "by": self.name_for(author), "when": at, "whenText": when_text(at)}

    def _sync_inbox(self, entries: list[dict[str, Any]]) -> None:
        self._entries = {e["id"]: e for e in entries}
        rows = []
        mentions = 0
        for e in entries:
            row = self._inbox_row(e)
            if row["kind"] in ("mention", "task"):
                mentions += 1
            rows.append(row)
        self._inbox.sync(rows)
        self._inbox_count, self._mention_count = len(rows), mentions
        self.inboxChanged.emit()

    def _inbox_row(self, e: dict[str, Any]) -> dict[str, Any]:
        kind = e["kind"]
        message = str(e.get("text") or e.get("message") or "")
        if kind == "project":
            title = M.Project.from_dict(e["project"]).title
        elif kind == "activity":
            title = str(e["activity"].get("name", "Activity"))
        else:
            title = str(e.get("title") or message.split("\n", 1)[0][:80])
        link = str(e.get("link") or "")
        if not link and kind == "task" and e.get("task_id"):
            link = link_for("task", str(e["task_id"]))
        mentions_me = kind in ("mention", "task") or self.me.lower() in MN.parse_mentions(message)
        sender = str(e.get("from", ""))
        return {"messageId": e["id"], "kind": kind, "sender": sender,
                "senderName": str(e.get("from_name") or "") or self.name_for(sender),
                "sentAt": str(e.get("sent_at", "")), "sentText": when_text(str(e.get("sent_at", ""))),
                "message": message, "title": title, "mentionsMe": mentions_me, "link": link}

    def _sync_announcements(self, items: list[Any], extras: dict[str, dict[str, Any]]) -> None:
        rows = []
        for a in items:
            ex = extras.get(a.id, {})
            rows.append({"announcementId": a.id, "title": a.title, "body": a.body, "level": a.level,
                         "author": a.author, "authorName": str(ex.get("author_name") or "") or self.name_for(a.author),
                         "ts": a.ts, "tsText": when_text(a.ts), "mine": a.author == self.me})
        self._announcements.sync(rows)

    def _sync_pulse(self, rows_in: list[dict[str, Any]]) -> None:
        rows = []
        seen: set[str] = set()
        for r in rows_in:
            ts = str(r.get("ts", ""))
            login = str(r.get("user", ""))
            key = ts if ts not in seen else f"{ts}#{login}#{len(seen)}"   # the key role must be unique
            seen.add(key)
            mentions = [str(m).lower() for m in r.get("mentions", []) or []] if isinstance(r.get("mentions"), list) else []
            rows.append({"ts": key, "tsText": when_text(ts), "login": login,
                         "displayName": str(r.get("name") or "") or self.name_for(login),
                         "event": str(r.get("event", "")), "detail": str(r.get("detail", "")),
                         "mentionsMe": self.me.lower() in mentions or self.me.lower() in MN.parse_mentions(
                             str(r.get("detail", "")))})
        if rows != self._pulse.rows:
            self._pulse.reset(rows)

    def _announce_fresh(self, fresh: list[dict[str, Any]]) -> None:
        now = time.time()
        mentions = []
        for e in fresh:
            dt = M.parse_iso(e.get("sent_at"))
            if dt is None or now - dt.timestamp() > TOAST_BACKLOG_S:
                continue
            row = self._inbox_row(e)
            if row["kind"] in ("mention", "task"):
                self.mentioned.emit(row["sender"], row["message"] or row["title"], row["link"])
                mentions.append({"id": e["id"], "from": row["sender"], "from_name": row["senderName"],
                                 "text": row["message"], "link": row["link"]})
            else:
                self._toast(f"{row['senderName']} sent you {row['title']}", row["message"], "info")
        if mentions:
            self._push_hub_events(mentions=mentions)

    def _push_hub_events(self, **kw: Any) -> None:
        try:
            self.app.watchers.push_hub_events(**kw)
        except Exception:  # noqa: BLE001
            log.debug("watchers not ready for hub events", exc_info=True)

    # ---- @ picker
    @Slot(str)
    def setMentionQuery(self, text: str) -> None:  # noqa: N802
        self._query = text or ""
        q = self._query.strip().lstrip("@").lower()
        online = {p.user.lower(): p.online for p in self.ctx.peers}
        rows = []
        for login, rec in self._users.items():
            name = str(rec.get("display_name") or "") or login
            if q and q not in login and q not in name.lower():
                continue
            rows.append({"login": login, "displayName": name, "role": str(rec.get("role", "")),
                         "online": bool(online.get(login)), "isGroup": False, "memberCount": 0})
        for g in self._group_list:
            if q and q not in g.name:
                continue
            # the picker prints "group · 4 · <role>": the role of a group row is its member names
            # ("Priya, Ravi, Yokesh, you"; V4-SEAMS, builder 4 ask 7)
            members = [("you" if m.lower() == self.me.lower() else self.name_for(m)) for m in g.members]
            members.sort(key=lambda n: (n == "you", n.lower()))
            rows.append({"login": g.name, "displayName": f"@{g.name}", "role": ", ".join(members), "online": False,
                         "isGroup": True, "memberCount": len(g.members)})
        rows.sort(key=lambda r: (not r["online"], r["isGroup"], not r["login"].startswith(q),
                                 r["displayName"].lower()))
        self._mention_candidates.sync(rows[:30])

    @Slot(str, int, result="QVariantMap")
    def mentionAt(self, text: str, cursor: int) -> dict[str, Any]:  # noqa: N802
        """{start, query} when the caret is in a mention being typed, else {} (``core.mentions``)."""
        found = MN.query_at_cursor(text, cursor)
        return {"start": found[0], "query": found[1]} if found else {}

    @Slot(str, int, str, result="QVariantMap")
    def insertMention(self, text: str, cursor: int, login: str) -> dict[str, Any]:  # noqa: N802
        """{text, cursor} after replacing the mention being typed with ``@login ``."""
        new_text, new_cursor = MN.insert_mention(text, cursor, login)
        return {"text": new_text, "cursor": new_cursor}

    # ---- publishing
    @Slot(str, str, "QStringList")
    def publishActivity(self, activity_id: str, description: str, for_targets: list[str]) -> None:  # noqa: N802
        store = self.ctx.store
        act = store.activity(activity_id)
        if act is None:
            self._toast("Publish failed", "That activity no longer exists.", "error")
            return
        copy = M.Activity.from_dict(act.to_dict())
        projects = [p for p in (store.get(pid) for pid in act.project_ids) if p is not None]
        hub, portable, dispatcher = self._hub(), self._portable(), self._dispatcher()
        targets = list(for_targets or []) + MN.parse_mentions(description)

        def work() -> Any:
            pub = hub.publish_activity(copy, portable, description, targets, projects)
            if pub and targets:
                reached = hub.expand_targets(targets)
                dispatcher.notify_people(reached, f"{hub.display_name or hub.user} published {copy.name} for you",
                                         link_for("activity", copy.name), title=copy.name, inbox=False)
            return pub

        def done(pub: Any) -> None:
            if not pub:
                self._toast("Publish failed", "The hub folder is not writable.", "error")
                return
            live = store.activity(activity_id)
            if live is not None:
                live.origin = copy.origin
                store.update_activity(live)
            self._toast(f"Published {copy.name}", f"Revision {pub.revision}" +
                        (f" for {', '.join('@' + t for t in pub.for_targets)}" if pub.for_targets else ""), "success")
            self._force_refresh()

        self.app.run_async(work, done, lambda e: self._toast("Publish failed", str(e), "error"))

    @Slot(str, str, "QStringList")
    def publishProject(self, project_id: str, description: str, for_targets: list[str]) -> None:  # noqa: N802
        store = self.ctx.store
        proj = store.get(project_id)
        if proj is None:
            self._toast("Publish failed", "That project no longer exists.", "error")
            return
        copy = M.Project.from_dict(proj.to_dict())
        hub, portable, dispatcher = self._hub(), self._portable(), self._dispatcher()
        targets = list(for_targets or []) + MN.parse_mentions(description)

        def work() -> Any:
            pub = hub.publish(copy, portable, description, targets)
            if pub and targets:
                dispatcher.notify_people(hub.expand_targets(targets),
                                         f"{hub.display_name or hub.user} published {copy.title} for you",
                                         link_for("open", copy.name), title=copy.title, inbox=False)
            return pub

        def done(pub: Any) -> None:
            if not pub:
                self._toast("Publish failed", "The hub folder is not writable.", "error")
                return
            live = store.get(project_id)
            if live is not None:
                live.origin = copy.origin
                store.update(live)
            self._toast(f"Published {copy.title}", f"Revision {pub.revision}", "success")
            self._force_refresh()

        self.app.run_async(work, done, lambda e: self._toast("Publish failed", str(e), "error"))

    @Slot(str)
    def unpublish(self, published_id: str) -> None:
        hub = self._hub()
        store = self.ctx.store

        def done(ok: bool) -> None:
            if not ok:
                self._toast("Unpublish failed", "The hub folder is not writable or the file is locked.", "error")
                return
            for p in store.projects:
                if p.origin.published_id == published_id and p.origin.author == self.me:
                    p.origin = M.Origin(source="local", author=self.me)
                    store.update(p)
            for a in store.activities:
                if a.origin.published_id == published_id and a.origin.author == self.me:
                    a.origin = M.Origin(source="local", author=self.me)
                    store.update_activity(a)
            self._published.remove(published_id)
            self._force_refresh()

        self.app.run_async(lambda: hub.unpublish(published_id), done)

    @Slot(str, str, "QStringList", str)
    def send(self, kind: str, local_id: str, targets: list[str], message: str) -> None:
        """Send a project or activity to people/groups (inbox)."""
        store = self.ctx.store
        obj: Any = store.activity(local_id) if kind == "activity" else store.get(local_id)
        if obj is None:
            self._toast("Send failed", f"That {kind} no longer exists.", "error")
            return
        copy = obj.__class__.from_dict(obj.to_dict())
        hub, portable, dispatcher = self._hub(), self._portable(), self._dispatcher()
        names = list(targets or []) + MN.parse_mentions(message)

        def work() -> list[str]:
            logins = hub.expand_targets(names)
            if kind == "activity":
                sent = logins if hub.send_activity(logins, copy, message, portable) else []
            else:
                sent = [lg for lg in logins if hub.send(lg, copy, message, portable)]
            if sent:
                title = copy.name if kind == "activity" else copy.title
                dispatcher.notify_people(sent, f"{hub.display_name or hub.user} sent you {title}",
                                         "", title=title, inbox=False)
            return sent

        def done(sent: list[str]) -> None:
            if not sent:
                self._toast("Nothing sent", "No known colleague matched those names.", "warning")
                return
            self._toast("Sent", ", ".join(self.name_for(s) for s in sent), "success")

        self.app.run_async(work, done, lambda e: self._toast("Send failed", str(e), "error"))

    # ---- announcements
    @Slot(str, str, str, str)
    def announce(self, title: str, body: str, level: str, expires: str) -> None:
        hub, dispatcher = self._hub(), self._dispatcher()
        names = MN.parse_mentions(f"{title} {body}")

        def work() -> Any:
            a = hub.announce(title, body, level or "info", expires or "", names)
            if a and names:
                dispatcher.notify_people(hub.expand_targets(names), f"{title}: {body}" if body else title,
                                         "", title=title, inbox=False)
            return a

        self.app.run_async(work, lambda a: self._force_refresh() if a else
                           self._toast("Announcement failed", "The hub folder is not writable.", "error"))

    @Slot(str)
    def removeAnnouncement(self, announcement_id: str) -> None:  # noqa: N802
        hub = self._hub()
        self._announcements.remove(announcement_id)
        self.app.run_async(lambda: hub.remove_announcement(announcement_id), lambda _r: self._force_refresh())

    # ---- inbox
    @Slot(str)
    def acceptInbox(self, message_id: str) -> None:  # noqa: N802
        e = self._entries.get(message_id)
        if e is None:
            return
        kind = e["kind"]
        if kind == "project":
            proj = M.Project.from_dict(e["project"])
            clone = proj.clone(proj.name)
            pid = str(e.get("published_id") or "")
            clone.origin = M.Origin(source="team" if pid else "inbox", author=str(e.get("from", "")), published_id=pid,
                                    revision=int(e.get("revision", 0) or 0))
            self.ctx.store.add(clone)
            self._toast("Added to your workspace", clone.name, "success")
        elif kind == "activity":
            act = M.Activity.from_dict(e["activity"])
            pid = str(e.get("published_id") or "")
            origin = M.Origin(source="team" if pid else "inbox", author=str(e.get("from", "")), published_id=pid,
                              revision=int(e.get("revision", 0) or 0))
            added = self.adopt_activity(act, origin, e.get("projects") or [])
            self._toast("Added to your workspace", added.name, "success")
        else:
            link = str(e.get("link") or "") or (link_for("task", str(e["task_id"])) if e.get("task_id") else "")
            if link:
                try:
                    from project_opener.ipc import parse_link
                    lk, key = parse_link(link)
                    self.app.open_link(lk, key)
                except Exception:  # noqa: BLE001
                    log.debug("could not open %s", link, exc_info=True)
        self.dismissInbox(message_id)

    @Slot(str)
    def dismissInbox(self, message_id: str) -> None:  # noqa: N802
        hub = self._hub()
        self._entries.pop(message_id, None)
        if self._inbox.remove(message_id):
            self._inbox_count = self._inbox.count()
            self._mention_count = sum(1 for r in self._inbox.rows if r["kind"] in ("mention", "task"))
            self.inboxChanged.emit()

        def done(ok: bool) -> None:
            if not ok:
                self._toast("Could not dismiss", "The inbox file is locked or the hub is unreachable.", "error")
                self._force_refresh()

        self.app.run_async(lambda: hub.dismiss_entry(message_id), done)

    @Slot(str, result=str)
    def clonePublished(self, published_id: str) -> str:  # noqa: N802
        """Clone a published project or activity into the workspace; returns the new local id."""
        pub = self._pubs.get(published_id)
        if pub is None:
            return ""
        origin = M.Origin(source="team", author=pub.author, published_id=pub.published_id,
                          published_at=pub.published_at, revision=pub.revision)
        if isinstance(pub, PublishedActivity):
            act = self.adopt_activity(pub.activity, origin, pub.projects)
            new_id = act.id
        else:
            clone = pub.project.clone(pub.project.name)
            clone.origin = origin
            self.ctx.store.add(clone)
            new_id = clone.id
        i = self._published.indexOf(published_id)
        if i >= 0:
            self._published.update(i, cloned=True)
        self._toast("Cloned to your workspace", "", "success")
        return new_id

    def adopt_activity(self, act: M.Activity, origin: M.Origin, projects: list[dict[str, Any]]) -> M.Activity:
        """Add a received activity: fresh ids, links to local projects where they can be proven.

        A project link survives when this workspace has the same project id, or exactly one
        project with the job number the publisher recorded; an item link survives when that
        project has the item (same id, else exactly one item with the same path).  Anything
        else becomes a plain item of no project - never a guessed link."""
        store = self.ctx.store
        jobs = {str(p.get("id", "")): str(p.get("job_number", "")) for p in projects if isinstance(p, dict)}

        def local_project(pid: str) -> M.Project | None:
            if store.get(pid):
                return store.get(pid)
            job = jobs.get(pid, "")
            if job:
                hits = [p for p in store.projects if p.job_number and p.job_number.lower() == job.lower()]
                if len(hits) == 1:
                    return hits[0]
            return None

        clone = act.clone(act.name)
        clone.origin = origin
        clone.project_ids = [p.id for p in (local_project(pid) for pid in act.project_ids) if p is not None]
        for it in clone.items:
            proj = local_project(it.project_id) if it.project_id else None
            if proj is None:
                it.project_id, it.source_item_id = "", ""
                continue
            it.project_id = proj.id
            if not any(src.id == it.source_item_id for src in proj.items):
                same = [src for src in proj.items if src.path.strip().lower() == it.path.strip().lower()]
                it.source_item_id = same[0].id if len(same) == 1 else ""
        store.add_activity(clone)
        return clone

    # ---- groups
    @Slot(str, "QStringList", str)
    def saveGroup(self, name: str, members: list[str], color: str) -> None:  # noqa: N802
        hub = self._hub()
        group = M.Group(name, list(members or []), color or "", created_by=self.me, updated_by=self.me)

        def work() -> None:
            GroupBook(hub.root).save(group, by=self.me)

        self.app.run_async(work, lambda _r: self._reload_groups(),
                           lambda e: self._toast("Group not saved", str(e), "error"))

    @Slot(str)
    def deleteGroup(self, name: str) -> None:  # noqa: N802
        hub = self._hub()
        self._groups.remove(clean_name(name))
        self.app.run_async(lambda: GroupBook(hub.root).remove(name), lambda _r: self._reload_groups())

    @Slot(str, result=str)
    def groupFromProject(self, project_id: str) -> str:  # noqa: N802
        """"@P12513-team" from everyone holding this job (clones/inbox of its published id); returns the name.

        "Holding" is read from the hub's own records: the publisher, the ``for`` list of
        the project's published file, and everyone whose pulse mentions the job number
        or title (launched, published, sent).  The group always includes me."""
        proj = self.ctx.store.get(project_id)
        if proj is None:
            return ""
        name = clean_name(f"{proj.job_number or proj.name}-team")
        if not name:
            return ""
        hub = self._hub()
        me = self.me
        needles = [n.lower() for n in (proj.job_number, proj.title, proj.name) if n]
        pid = proj.origin.published_id

        def work() -> int:
            members = {me.lower()}
            if pid:
                pub = next((p for p in hub.published() if p.published_id == pid), None)
                if pub:
                    members.add(pub.author.lower())
                members |= set(hub.expand_targets(hub.published_for().get(pid, []), include_self=True))
            for row in hub.pulse_feed(limit=2000):
                detail = str(row.get("detail", "")).lower()
                if any(n in detail for n in needles) and row.get("user"):
                    members.add(str(row["user"]).lower())
            known = set(hub.known_users())
            final = sorted(m for m in members if not known or m in known or m == me.lower())
            GroupBook(hub.root).save(M.Group(name, final, proj.color, created_by=me, updated_by=me), by=me)
            return len(final)

        def done(n: int) -> None:
            self._toast(f"Group @{name}", f"{n} member{'s' if n != 1 else ''}", "success")
            self._reload_groups()

        self.app.run_async(work, done, lambda e: self._toast("Group not saved", str(e), "error"))
        return name

    def _reload_groups(self) -> None:
        hub = self._hub()

        def done(groups: list[M.Group]) -> None:
            self._group_list = groups
            self._sync_groups()
            self.setMentionQuery(self._query)

        self.app.run_async(hub.groups, done)

    def _force_refresh(self) -> None:
        self._last_refresh = 0.0
        self.refresh()


def _announcement_extras(hub: TeamHub) -> dict[str, dict[str, Any]]:
    """id -> the raw announcement row (v4 fields such as ``author_name``, ``mentions``)."""
    from project_opener.core.jsonio import read_json
    d = read_json(hub.root / "announcements.json", {}) if hub.root else {}  # type: ignore[operator]
    items = d.get("items", []) if isinstance(d, dict) else []
    return {str(x.get("id", "")): x for x in items if isinstance(x, dict)}
