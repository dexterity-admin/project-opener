"""``app.activities``: activities, projects, the launch dock and the Resume band.  Owner: builder 4 (SHELL).

Python owns every fact (names, order, statuses, timing); QML owns how a change
is shown.  Built on the 3.2 services in ``app.ctx`` (store, launcher, health)
and ``app.snapshots`` for the Resume band.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from project_opener.quick.base import ApiBase, ro
from project_opener.quick.listmodel import DictListModel

# Role names are part of the QML contract (docs/V4-ARCHITECTURE.md section 7.3).
ACTIVITY_ROLES = (
    "activityId", "name", "label", "icon", "dotColor", "spine", "projectTitle", "itemCount", "openCount",
    "lastOpened", "lastOpenedText", "pinned", "running", "captureOn", "openNow", "identifiedNow",
    "needsPathNow", "healthWorst", "healthText", "taskLine", "ownerName", "published",
)
PROJECT_ROLES = (
    "projectId", "name", "title", "spine", "client", "dotColor", "icon", "itemCount", "activityCount",
    "pinned", "healthWorst", "healthText", "lastOpenedText", "published",
)
ITEM_ROLES = (
    "itemId", "name", "path", "kind", "group", "projectId", "projectTitle", "health", "healthLabel",
    "profileName", "itemEnabled", "order",
)
DOCK_ROLES = ("order", "name", "path", "group", "status", "statusLabel", "message")


class ActivitiesApi(ApiBase):
    activitiesChanged = Signal()
    projectsChanged = Signal()
    currentChanged = Signal()
    resumeChanged = Signal()
    launchChanged = Signal()
    launchStarted = Signal(str)               # activity id
    launchFinished = Signal(str, str)         # activity id, summary ("4 opened · 2 not opened")
    confirmNeeded = Signal(str, str, int)     # request id, activity id, item count (open more than N)

    def __init__(self, app: Any):
        super().__init__(app)
        self._activities = DictListModel(ACTIVITY_ROLES, key="activityId", parent=self)
        self._projects = DictListModel(PROJECT_ROLES, key="projectId", parent=self)
        self._items = DictListModel(ITEM_ROLES, key="itemId", parent=self)
        self._dock = DictListModel(DOCK_ROLES, key="order", parent=self)
        self._current_id = ""
        self._current: dict[str, Any] = {}
        self._resume: dict[str, Any] = {}
        self._launching = False
        self._launch_progress = 0.0
        self._launch_summary = ""

    # ------------------------------------------------------------- models
    @Property(QObject, constant=True)
    def activities(self) -> DictListModel:
        """Every activity, in stage order (pinned, then recent)."""
        return self._activities

    @Property(QObject, constant=True)
    def projects(self) -> DictListModel:
        return self._projects

    @Property(QObject, constant=True)
    def items(self) -> DictListModel:
        """The current activity's items in launch order."""
        return self._items

    @Property(QObject, constant=True)
    def dock(self) -> DictListModel:
        """The launch dock's rows for the run in progress (or the last one)."""
        return self._dock

    # --------------------------------------------------------- properties
    currentId = ro(str, "_current_id", currentChanged)
    current = ro("QVariantMap", "_current", currentChanged)        # same keys as ACTIVITY_ROLES
    resume = ro("QVariantMap", "_resume", resumeChanged)           # {} or {activityId, title, count, takenAt, text}
    launching = ro(bool, "_launching", launchChanged)
    launchProgress = ro(float, "_launch_progress", launchChanged)  # 0..1
    launchSummary = ro(str, "_launch_summary", launchChanged)

    # -------------------------------------------------------------- slots
    def start(self) -> None:
        """Fill the models from the store and compute the Resume band (stale RunningMarkers)."""
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        """Rebuild the activity and project models from ``app.ctx.store`` (stub: empty until built)."""
        self._activities.reset([])
        self._projects.reset([])
        self.activitiesChanged.emit()
        self.projectsChanged.emit()

    @Slot(str)
    def select(self, activity_id: str) -> None:
        """Make ``activity_id`` the centre of the stage (fills ``current`` and ``items``)."""
        self.todo("ActivitiesApi.select")

    @Slot(str)
    def open(self, activity_id: str) -> None:
        """Open the activity: launch its items (dock rows settle), mark it running, start capture."""
        self.todo("ActivitiesApi.open")

    @Slot(str, bool)
    def answerConfirm(self, request_id: str, ok: bool) -> None:
        self.todo("ActivitiesApi.answerConfirm")

    @Slot(str)
    def openProject(self, project_id: str) -> None:
        """3.x behaviour: open a project's enabled items (no capture)."""
        self.todo("ActivitiesApi.openProject")

    @Slot(str, str, result=str)
    def create(self, name: str, project_id: str) -> str:
        """New empty activity attached to ``project_id`` (may be ""); returns its id."""
        return self.todo("ActivitiesApi.create")

    @Slot(str, "QVariantMap")
    def edit(self, activity_id: str, fields: dict[str, Any]) -> None:
        """Set name, shortName, icon, color, description, notes, projectIds, captureOn, resumeOnStart."""
        self.todo("ActivitiesApi.edit")

    @Slot(str)
    def remove(self, activity_id: str) -> None:
        self.todo("ActivitiesApi.remove")

    @Slot(str, result=str)
    def duplicate(self, activity_id: str) -> str:
        return self.todo("ActivitiesApi.duplicate")

    @Slot(str)
    def togglePin(self, activity_id: str) -> None:
        self.todo("ActivitiesApi.togglePin")

    @Slot(str, "QStringList")
    def addPaths(self, activity_id: str, paths: list[str]) -> None:
        """Add files/folders/links as items (Explorer verb, Send to, drop, the add-item sheet)."""
        self.todo("ActivitiesApi.addPaths")

    @Slot(str, str, str)
    def addProjectItem(self, activity_id: str, project_id: str, item_id: str) -> None:
        self.todo("ActivitiesApi.addProjectItem")

    @Slot(str, str)
    def removeItem(self, activity_id: str, item_id: str) -> None:
        self.todo("ActivitiesApi.removeItem")

    @Slot(str, str, int)
    def moveItem(self, activity_id: str, item_id: str, to_index: int) -> None:
        self.todo("ActivitiesApi.moveItem")

    @Slot(str, str, "QVariantMap")
    def editItem(self, activity_id: str, item_id: str, fields: dict[str, Any]) -> None:
        """path, label, kind, args, group, profileId, itemEnabled."""
        self.todo("ActivitiesApi.editItem")

    @Slot()
    def resumeNow(self) -> None:
        """The Resume band's button: restore the stale marker's latest snapshot (via ``app.capture``)."""
        self.todo("ActivitiesApi.resumeNow")

    @Slot()
    def dismissResume(self) -> None:
        self.todo("ActivitiesApi.dismissResume")

    @Slot()
    def closeDock(self) -> None:
        self.todo("ActivitiesApi.closeDock")

    @Slot(str)
    def mailBundle(self, activity_id: str) -> None:
        """Outlook: the activity's items as links (``core.mail``)."""
        self.todo("ActivitiesApi.mailBundle")

    @Slot(str, result=str)
    def link(self, activity_id: str) -> str:
        """``projectopener://activity/<id>`` for copy-link."""
        from project_opener.ipc import make_link
        return make_link("activity", activity_id)
