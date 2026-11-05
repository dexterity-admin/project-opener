"""``app.watchers``: watcher rules, alerts, and the office-wide drive map (footlights).
Owner: builder 1 (CORE+HUB).

Runs ``core.watchers.WatcherEngine.tick`` on the pool every ``WATCH_TICK_S``;
hits go through ``lan.delivery.Dispatcher`` (toast via the facade, pulse,
inbox for mentions, Cliq) exactly once per event key.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from project_opener.quick.base import ApiBase
from project_opener.quick.listmodel import DictListModel

WATCHER_ROLES = ("watcherId", "name", "kind", "target", "events", "watcherEnabled", "notifyText", "lastHitText",
                 "activityId", "projectId")
ALERT_ROLES = ("alertKey", "ts", "tsText", "title", "detail", "level", "link", "unread", "watcherId")
ROOT_ROLES = ("rootName", "status", "statusLabel", "mapping", "uses", "seenBy", "since", "sinceText", "jobsAffected")


class WatchersApi(ApiBase):
    watchersChanged = Signal()
    alertsChanged = Signal()
    rootsChanged = Signal()
    alert = Signal(str, str, str, str)       # title, body, level, link

    def __init__(self, app: Any):
        super().__init__(app)
        self._watchers = DictListModel(WATCHER_ROLES, key="watcherId", parent=self)
        self._alerts = DictListModel(ALERT_ROLES, key="alertKey", parent=self)
        self._roots = DictListModel(ROOT_ROLES, key="rootName", parent=self)

    @Property(QObject, constant=True)
    def watchers(self) -> DictListModel:
        return self._watchers

    @Property(QObject, constant=True)
    def alerts(self) -> DictListModel:
        return self._alerts

    @Property(QObject, constant=True)
    def roots(self) -> DictListModel:
        """Drives on this PC merged with ``watch/*.json``: "nas01 down since 09:40, seen by 3 PCs, 14 jobs"."""
        return self._roots

    @Property(int, notify=alertsChanged)
    def unreadCount(self) -> int:
        return sum(1 for r in self._alerts.rows if r.get("unread"))

    @Slot(str, str, "QStringList", "QVariantMap", "QVariantMap", result=str)
    def create(self, kind: str, target: str, events: list[str], params: dict[str, Any],
               notify: dict[str, Any]) -> str:
        """notify: {toast, mentions, cliqDm, cliqChannel}; params may carry activityId/projectId."""
        return self.todo("WatchersApi.create")

    @Slot(str, "QVariantMap")
    def edit(self, watcher_id: str, fields: dict[str, Any]) -> None:
        self.todo("WatchersApi.edit")

    @Slot(str)
    def remove(self, watcher_id: str) -> None:
        self.todo("WatchersApi.remove")

    @Slot(str, bool)
    def setEnabled(self, watcher_id: str, on: bool) -> None:
        self.todo("WatchersApi.setEnabled")

    @Slot(str)
    def markRead(self, alert_key: str) -> None:
        self.todo("WatchersApi.markRead")

    @Slot()
    def recheckRoots(self) -> None:
        self.todo("WatchersApi.recheckRoots")
