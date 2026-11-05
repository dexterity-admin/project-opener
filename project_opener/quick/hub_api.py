"""``app.hub``: people, publishing with "for", inbox and mentions, groups, announcements, pulse, register.
Owner: builder 1 (CORE+HUB).

Wraps ``lan.hub.TeamHub`` (+ ``lan.groups``) on the pool; refreshes on the 3.2
heartbeat (``app.ctx.hub_changed``) and its own timer for groups and mentions.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from project_opener.quick.base import ApiBase, ro
from project_opener.quick.listmodel import DictListModel

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

    # -------------------------------------------------------------- slots
    @Slot()
    def refresh(self) -> None:
        self.todo("HubApi.refresh")

    @Slot(str)
    def setMentionQuery(self, text: str) -> None:
        self.todo("HubApi.setMentionQuery")

    @Slot(str, int, result="QVariantMap")
    def mentionAt(self, text: str, cursor: int) -> dict[str, Any]:
        """{start, query} when the caret is in a mention being typed, else {} (``core.mentions``)."""
        from project_opener.core import mentions
        found = mentions.query_at_cursor(text, cursor)
        return {"start": found[0], "query": found[1]} if found else {}

    @Slot(str, int, str, result="QVariantMap")
    def insertMention(self, text: str, cursor: int, login: str) -> dict[str, Any]:
        """{text, cursor} after replacing the mention being typed with ``@login ``."""
        from project_opener.core import mentions
        new_text, new_cursor = mentions.insert_mention(text, cursor, login)
        return {"text": new_text, "cursor": new_cursor}

    @Slot(str, str, "QStringList")
    def publishActivity(self, activity_id: str, description: str, for_targets: list[str]) -> None:
        self.todo("HubApi.publishActivity")

    @Slot(str, str, "QStringList")
    def publishProject(self, project_id: str, description: str, for_targets: list[str]) -> None:
        self.todo("HubApi.publishProject")

    @Slot(str)
    def unpublish(self, published_id: str) -> None:
        self.todo("HubApi.unpublish")

    @Slot(str, str, "QStringList", str)
    def send(self, kind: str, local_id: str, targets: list[str], message: str) -> None:
        """Send a project or activity to people/groups (inbox)."""
        self.todo("HubApi.send")

    @Slot(str, str, str, str)
    def announce(self, title: str, body: str, level: str, expires: str) -> None:
        self.todo("HubApi.announce")

    @Slot(str)
    def removeAnnouncement(self, announcement_id: str) -> None:
        self.todo("HubApi.removeAnnouncement")

    @Slot(str)
    def acceptInbox(self, message_id: str) -> None:
        self.todo("HubApi.acceptInbox")

    @Slot(str)
    def dismissInbox(self, message_id: str) -> None:
        self.todo("HubApi.dismissInbox")

    @Slot(str, result=str)
    def clonePublished(self, published_id: str) -> str:
        """Clone a published project or activity into the workspace; returns the new local id."""
        return self.todo("HubApi.clonePublished")

    @Slot(str, "QStringList", str)
    def saveGroup(self, name: str, members: list[str], color: str) -> None:
        self.todo("HubApi.saveGroup")

    @Slot(str)
    def deleteGroup(self, name: str) -> None:
        self.todo("HubApi.deleteGroup")

    @Slot(str, result=str)
    def groupFromProject(self, project_id: str) -> str:
        """"@P12513-team" from everyone holding this job (clones/inbox of its published id); returns the name."""
        return self.todo("HubApi.groupFromProject")
