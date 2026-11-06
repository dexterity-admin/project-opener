"""``app.activities``: activities, projects, the launch dock and the Resume band.  Owner: builder 4 (SHELL).

Python owns every fact (names, order, statuses, timing); QML owns how a change
is shown.  Built on the 3.2 services in ``app.ctx`` (store, launcher, health)
and ``app.snapshots`` for the Resume band.

Beyond the contract (docs/V4-ARCHITECTURE.md 7.3) this object also serves the
project pages, because no other sub-API owns projects: ``projectItems``,
``currentProject``, ``allItems`` (the editor's cross-project picker),
``profiles`` and the project slots (``createProject`` ... ``openProjectItem``).
Calls into other builders' sub-APIs are guarded: an error there is logged and
this object keeps its own state, never raising into QML.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from project_opener.core import health as H
from project_opener.core import models as M
from project_opener.quick.base import ApiBase, ro
from project_opener.quick.listmodel import DictListModel
from project_opener.ui import text as T

log = logging.getLogger(__name__)

# Role names are part of the QML contract (docs/V4-ARCHITECTURE.md section 7.3); the extra roles after the
# contract's are additive (the stage's centre scene and the cards read them).
ACTIVITY_ROLES = (
    "activityId", "name", "label", "icon", "dotColor", "spine", "projectTitle", "itemCount", "openCount",
    "lastOpened", "lastOpenedText", "pinned", "running", "captureOn", "openNow", "identifiedNow",
    "needsPathNow", "healthWorst", "healthText", "taskLine", "ownerName", "published",
    # additive
    "title", "subtitle", "description", "previewNames", "previewGlyphs", "previewMore", "problems", "okCount", "pausedAt",
    "pausedText", "projectCount", "shortName", "captureText", "resumeOnStart", "notes", "projectIds",
    # round 2: one capture-state word set (U4), the drive-down fact (C2), the watcher's figure (C4), open tasks
    "captureState", "driveDown", "driveText", "newFiles", "openTasks",
)
PROJECT_ROLES = (
    "projectId", "name", "title", "spine", "client", "dotColor", "icon", "itemCount", "activityCount",
    "pinned", "healthWorst", "healthText", "lastOpenedText", "published",
    # additive
    "subtitle", "tags", "favorite", "healthLine", "jobNumber", "description",
)
ITEM_ROLES = (
    "itemId", "name", "path", "kind", "group", "projectId", "projectTitle", "health", "healthLabel",
    "profileName", "itemEnabled", "order",
    # additive
    "glyph", "resolved", "profileId", "args", "label", "healthLevel", "linked",
)
DOCK_ROLES = ("order", "name", "path", "group", "status", "statusLabel", "message", "level", "glyph")
PICK_ROLES = ("itemKey", "name", "path", "kind", "group", "projectId", "projectTitle", "glyph", "inCurrent")
PROFILE_ROLES = ("profileId", "name", "appName", "description")

KIND_GLYPH = {"folder": "folder", "url": "link", "app": "app-window", "command": "terminal-window"}
EXT_GLYPH = {
    ".pdf": "file-pdf", ".xlsx": "table", ".xls": "table", ".xlsm": "table", ".csv": "table",
    ".docx": "file-text", ".doc": "file-text", ".txt": "file-text", ".nwd": "cube", ".nwf": "cube",
    ".nwc": "cube", ".dgn": "cube", ".dwg": "cube", ".i01": "file", ".pptx": "presentation",
}
PREVIEW_N = 5
PROBLEMS_N = 3


def item_glyph(kind: str, path: str) -> str:
    if kind in KIND_GLYPH:
        return KIND_GLYPH[kind]
    return EXT_GLYPH.get(os.path.splitext(path or "")[1].lower(), "file")


def _bool(v: Any) -> bool:
    if isinstance(v, str):
        return v.lower() in ("1", "true", "yes", "on")
    return bool(v)


class ActivitiesApi(ApiBase):
    activitiesChanged = Signal()
    projectsChanged = Signal()
    currentChanged = Signal()
    resumeChanged = Signal()
    launchChanged = Signal()
    progressChanged = Signal()                # launchProgress alone: a row settling re-binds the bar, not the dock
    launchStarted = Signal(str)               # activity id
    launchFinished = Signal(str, str)         # activity id, summary ("4 opened · 2 not opened")
    confirmNeeded = Signal(str, str, int)     # request id, activity id, item count (open more than N)
    projectChanged = Signal()                 # currentProject / projectItems
    created = Signal(str, str)                # kind ("activity" | "project"), id: the shell opens its page

    def __init__(self, app: Any):
        super().__init__(app)
        self._activities = DictListModel(ACTIVITY_ROLES, key="activityId", parent=self)
        self._projects = DictListModel(PROJECT_ROLES, key="projectId", parent=self)
        self._items = DictListModel(ITEM_ROLES, key="itemId", parent=self)
        self._dock = DictListModel(DOCK_ROLES, key="order", parent=self)
        self._project_items = DictListModel(ITEM_ROLES, key="itemId", parent=self)
        self._all_items = DictListModel(PICK_ROLES, key="itemKey", parent=self)
        self._profiles = DictListModel(PROFILE_ROLES, key="profileId", parent=self)
        self._current_id = ""
        self._current: dict[str, Any] = {}
        self._resume: dict[str, Any] = {}
        self._launching = False
        self._launch_progress = 0.0
        self._launch_summary = ""
        self._dock_open = False
        self._dock_id = ""
        self._dock_title = ""
        self._dock_line = ""
        self._dock_color = ""
        self._dock_task = ""
        self._dock_started_at = ""
        self._project_id = ""
        self._project: dict[str, Any] = {}
        self._project_query = ""
        self._project_tag = ""
        self._health: dict[str, dict[str, H.ItemHealth]] = {}   # activity id -> item id -> health
        self._pending: dict[str, tuple[str, str]] = {}           # confirm request id -> (kind, id)
        self._run: Any = None
        self._resume_dismissed: set[str] = set()
        self._path_health: dict[str, H.ItemHealth] = {}           # lower-case path -> health (live rows)
        self._path_pending: set[str] = set()
        self._health_rev = 0
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(0)
        self._refresh_timer.timeout.connect(self.refresh)
        app.ctx.store.subscribe(self._on_store_event)
        app.ctx.health_updated.connect(lambda _pid: self._refresh_timer.start())

    # ------------------------------------------------------------- models
    @Property(QObject, constant=True)
    def activities(self) -> DictListModel:
        """Every activity, in stage order (running, pinned, then recent)."""
        return self._activities

    @Property(QObject, constant=True)
    def projects(self) -> DictListModel:
        """Projects after the Projects page's search and tag filter."""
        return self._projects

    @Property(QObject, constant=True)
    def items(self) -> DictListModel:
        """The current activity's items in launch order."""
        return self._items

    @Property(QObject, constant=True)
    def dock(self) -> DictListModel:
        """The launch dock's rows for the run in progress (or the last one)."""
        return self._dock

    @Property(QObject, constant=True)
    def projectItems(self) -> DictListModel:  # noqa: N802
        """The current project's items (the project page)."""
        return self._project_items

    @Property(QObject, constant=True)
    def allItems(self) -> DictListModel:  # noqa: N802
        """Every project item, for the activity editor's cross-project picker."""
        return self._all_items

    @Property(QObject, constant=True)
    def profiles(self) -> DictListModel:
        """CAD launch profiles (``store.profiles``) for application items."""
        return self._profiles

    # --------------------------------------------------------- properties
    currentId = ro(str, "_current_id", currentChanged)
    current = ro("QVariantMap", "_current", currentChanged)        # same keys as ACTIVITY_ROLES
    resume = ro("QVariantMap", "_resume", resumeChanged)           # {} or {activityId, title, count, takenAt, text}
    launching = ro(bool, "_launching", launchChanged)
    launchProgress = ro(float, "_launch_progress", progressChanged)  # 0..1
    launchSummary = ro(str, "_launch_summary", launchChanged)
    dockOpen = ro(bool, "_dock_open", launchChanged)
    dockId = ro(str, "_dock_id", launchChanged)
    dockTitle = ro(str, "_dock_title", launchChanged)
    dockLine = ro(str, "_dock_line", launchChanged)
    dockColor = ro(str, "_dock_color", launchChanged)
    dockTaskLine = ro(str, "_dock_task", launchChanged)
    dockStartedText = ro(str, "_dock_started_at", launchChanged)
    currentProjectId = ro(str, "_project_id", projectChanged)
    currentProject = ro("QVariantMap", "_project", projectChanged)
    projectQuery = ro(str, "_project_query", projectsChanged)
    projectTag = ro(str, "_project_tag", projectsChanged)
    healthChanged = Signal()
    healthRev = ro(int, "_health_rev", healthChanged)

    @Property(int, notify=activitiesChanged)
    def activityCount(self) -> int:  # noqa: N802
        return len(self.app.ctx.store.activities)

    @Property(int, notify=projectsChanged)
    def projectCount(self) -> int:  # noqa: N802
        return len(self.app.ctx.store.projects)

    @Property("QStringList", notify=projectsChanged)
    def allTags(self) -> list[str]:  # noqa: N802
        return self.app.ctx.store.all_tags()

    @Property("QStringList", notify=projectsChanged)
    def projectIcons(self) -> list[str]:  # noqa: N802
        return list(PROJECT_ICONS)

    # ---------------------------------------------------- reading helpers
    def _store(self) -> Any:
        return self.app.ctx.store

    def _cap(self, name: str, default: Any = None) -> Any:
        """A property of ``app.capture`` (builder 2); the default while the facade is still being built."""
        try:
            return getattr(self.app.capture, name)
        except Exception:  # noqa: BLE001
            return default

    def _task_line(self, kind: str, local_id: str) -> str:
        try:
            return str(self.app.tasks.lineFor(kind, local_id) or "")
        except Exception:  # noqa: BLE001  (the tasks folder may be unreadable; the card simply has no line)
            return ""

    def _name_for(self, login: str) -> str:
        if login == self.app.ctx.user:
            return self.app.ctx.display_name()
        try:
            return self.app.ctx.hub.display_name_for(login)
        except Exception:  # noqa: BLE001
            return login

    def _project_health(self, project: M.Project) -> list[str]:
        h = self.app.ctx.health_for(project.id)
        if h is None:
            return []
        return [st.status for it in project.items if (st := h.status_for(it.id)) is not None]

    def _item_health(self, activity_id: str, item: M.Item) -> H.ItemHealth | None:
        return self._health.get(activity_id, {}).get(item.id)

    def _color_for(self, act: M.Activity, projects: dict[str, M.Project]) -> str:
        if act.color:
            return act.color
        for pid in act.project_ids + [i.project_id for i in act.items]:
            if pid in projects:
                return projects[pid].color
        return self.app.ui.tokens.get("text_faint", "#8A958E") if hasattr(self.app, "ui") else "#8A958E"

    def _stale(self) -> dict[str, M.RunningMarker]:
        try:
            marks = self.app.snapshots.stale_markers()
        except Exception:  # noqa: BLE001
            return {}
        return {m.activity_id: m for m in marks}

    # ------------------------------------------------------------- facts
    def _offline_roots(self) -> dict[str, dict[str, Any]]:
        """Roots the office-wide drive map reports not reachable (app.watchers.roots: the one source for
        "down since"), keyed by folded root."""
        try:
            rows = self.app.watchers.roots.rows
        except (AttributeError, RuntimeError):
            return {}
        return {str(r.get("rootName", "")).lower(): r for r in rows
                if r.get("rootName") and str(r.get("status", "")).lower() not in ("ok", "")}

    def _root_of(self, path: str) -> str:
        from project_opener.core.health import path_root, root_key
        try:
            path = self.app.ctx.resolver.resolve(path).resolved or path
        except Exception:  # noqa: BLE001
            pass
        root = path_root(path)
        if not root:
            return ""
        try:
            folded, _share = root_key(root, self.app.ctx.resolver.drive_map)
        except Exception:  # noqa: BLE001
            folded = root
        return folded.lower()

    def _drive_fact(self, act: M.Activity, offline: dict[str, dict[str, Any]]) -> tuple[bool, str]:
        """(a root this activity uses is down, "\nas01 down since 14:40")."""
        if not offline:
            return False, ""
        for it in act.items:
            r = offline.get(self._root_of(it.path))
            if r is not None:
                since = str(r.get("sinceText", "")).split(" · ")[0]
                return True, T.join_facts(str(r.get("rootName", "")), since)
        return False, ""

    def _open_tasks(self, act_id: str) -> list[dict[str, Any]]:
        try:
            rows = self.app.tasks.all.rows
        except (AttributeError, RuntimeError):
            return []
        out = [{"taskId": r.get("taskId", ""), "title": r.get("title", ""), "dueText": r.get("dueText", ""),
                "overdue": bool(r.get("overdue"))}
               for r in rows if r.get("attachKind") == "activity" and r.get("attachId") == act_id and not r.get("done")]
        return out[:3]

    def _new_files(self, act: M.Activity) -> dict[str, Any]:
        try:
            fact = self.app.watchers.new_files(act.id, lambda p: act.item_by_path(p) is not None)
        except Exception:  # noqa: BLE001
            return {}
        if fact:
            fact = {**fact, "timeText": T.clock(fact.get("time", ""))}
        return fact

    def capture_state(self, act: M.Activity, running: bool) -> str:
        if not self.app.ctx.settings.capture_enabled or not act.capture_enabled:
            return "off"
        if running:
            return "paused" if self._cap("state", "") == "paused" else "watching"
        return "idle"

    # ------------------------------------------------------------- rows
    def activity_row(self, act: M.Activity, projects: dict[str, M.Project] | None = None,
                     stale: dict[str, M.RunningMarker] | None = None) -> dict[str, Any]:
        projects = projects if projects is not None else {p.id: p for p in self._store().projects}
        stale = stale if stale is not None else {}
        primary = projects.get(act.primary_project_id)
        spine = primary.spine if primary else ""
        pids = list(dict.fromkeys([p for p in act.project_ids if p in projects]
                                  + [i.project_id for i in act.items if i.project_id in projects]))
        statuses = [h.status for i in act.items if (h := self._item_health(act.id, i)) is not None]
        problems = []
        for it in act.items:
            h = self._item_health(act.id, it)
            if h is not None and h.status != "ok":
                level, word = T.STATUS_META.get(h.status, ("warn", "Not found"))
                problems.append({"name": it.display_name, "level": level, "label": word})
        problems.sort(key=lambda p: {"bad": 0, "warn": 1}.get(p["level"], 2))
        running = self._cap("runningId", "") == act.id
        global_capture = bool(self.app.ctx.settings.capture_enabled)
        capture_on = act.capture_enabled and global_capture
        if running:
            open_now = int(self._cap("openCount", 0) or 0)
            ident = int(self._cap("identifiedCount", 0) or 0)
            needs = int(self._cap("needsPathCount", 0) or 0)
        else:
            open_now = ident = needs = 0
        marker = stale.get(act.id)
        paused_at = ""
        if marker is not None:
            snap = None
            try:
                snap = self.app.snapshots.latest(act.id)
            except Exception:  # noqa: BLE001
                pass
            paused_at = (snap.taken_at if snap else "") or marker.last_seen
        opened = f"opened {act.open_count}×, last {T.relative_time(act.last_opened).lower()}" if act.last_opened \
            else "never opened"
        client = primary.client if primary and primary.client and primary.job_number else ""
        from_projects = f"from {T.plural(len(pids), 'project')}" if len(pids) > 1 else ""
        count = T.plural(len(act.items), "item") + (f" {from_projects}" if from_projects else "")
        subtitle = T.join_facts(client, count, opened)
        names = [i.display_name for i in act.items]
        state = self.capture_state(act, running)
        last = ""
        if state != "watching":
            try:
                snap = self.app.snapshots.latest(act.id)
                last = snap.taken_at if snap is not None and snap.entries else ""
            except Exception:  # noqa: BLE001
                last = ""
        capture_text = T.capture_line(state, last, open_now, ident)
        task = self._task_line("activity", act.id)
        drive_down, drive_text = self._drive_fact(act, self._offline_roots())
        return {
            "activityId": act.id, "name": act.name, "label": act.label,
            "icon": _icon(act.icon), "dotColor": self._color_for(act, projects), "spine": spine,
            "projectTitle": primary.title if primary else ("" if not pids else projects[pids[0]].title),
            "itemCount": len(act.items), "openCount": act.open_count, "lastOpened": act.last_opened or "",
            "lastOpenedText": T.health_line(len(act.items), len(act.enabled_items), act.last_opened),
            "pinned": act.pinned, "running": running, "captureOn": capture_on, "openNow": open_now,
            "identifiedNow": ident, "needsPathNow": needs,
            "healthWorst": T.worst_status(statuses), "healthText": T.health_summary(statuses),
            "taskLine": task, "ownerName": self._name_for(act.owner), "published": bool(act.origin.published_id),
            "title": T.activity_title(act.name, spine), "subtitle": subtitle, "description": act.description,
            "previewNames": names[:PREVIEW_N], "previewMore": max(0, len(names) - PREVIEW_N),
            "previewGlyphs": [item_glyph(i.kind, i.path) for i in act.items[:PREVIEW_N]],
            "problems": problems[:PROBLEMS_N], "okCount": sum(1 for s in statuses if s == "ok"),
            "pausedAt": paused_at, "pausedText": f"paused at {T.clock(paused_at)}" if paused_at else "",
            "projectCount": len(pids), "shortName": act.short_name, "captureText": capture_text,
            "resumeOnStart": act.resume_on_start, "notes": act.notes, "projectIds": list(act.project_ids),
            "captureState": state, "driveDown": drive_down, "driveText": drive_text,
            "newFiles": self._new_files(act), "openTasks": self._open_tasks(act.id),
        }

    def item_row(self, item: M.Item, order: int, owner_id: str, projects: dict[str, M.Project],
                 health: H.ItemHealth | None) -> dict[str, Any]:
        pid = getattr(item, "project_id", "") or ""
        proj = projects.get(pid)
        status = health.status if health else ""
        level, word = T.STATUS_META.get(status, ("neutral", "")) if status else ("neutral", "")
        prof = self._store().profile(item.profile_id) if item.profile_id else None
        return {
            "itemId": item.id, "name": item.display_name, "path": item.path, "kind": item.kind, "group": item.group,
            "projectId": pid, "projectTitle": proj.title if proj else "", "health": status, "healthLabel": word,
            "profileName": prof.name if prof else "", "itemEnabled": item.enabled, "order": order,
            "glyph": item_glyph(item.kind, item.path), "resolved": health.resolved if health else "",
            "profileId": item.profile_id, "args": item.args, "label": item.label, "healthLevel": level,
            "linked": bool(getattr(item, "source_item_id", "")),
        }

    def project_row(self, p: M.Project, acts: list[M.Activity]) -> dict[str, Any]:
        statuses = self._project_health(p)
        return {
            "projectId": p.id, "name": p.name, "title": p.title, "spine": p.spine, "client": p.client,
            "dotColor": p.color, "icon": _icon(p.icon, "folder"), "itemCount": len(p.items),
            "activityCount": sum(1 for a in acts if p.id in a.project_ids or any(i.project_id == p.id for i in a.items)),
            "pinned": p.pinned, "healthWorst": T.worst_status(statuses), "healthText": T.health_summary(statuses),
            "lastOpenedText": T.relative_time(p.last_opened) if p.last_opened else "Never opened",
            "published": bool(p.origin.published_id), "subtitle": T.subtitle_line(p), "tags": list(p.tags),
            "favorite": p.favorite, "healthLine": T.health_line(len(p.items), len(p.enabled_items), p.last_opened),
            "jobNumber": p.job_number, "description": p.description,
        }

    # -------------------------------------------------------------- slots
    def start(self) -> None:
        """Fill the models, compute the Resume band (stale RunningMarkers), check paths."""
        for name, sig in (("capture", "stateChanged"), ("capture", "liveChanged"), ("tasks", "tasksChanged"),
                          ("watchers", "rootsChanged"), ("watchers", "alertsChanged"),
                          ("watchers", "watchersChanged")):
            try:
                getattr(getattr(self.app, name), sig).connect(self._refresh_timer.start)
            except Exception:  # noqa: BLE001
                pass
        try:
            # the band and a running activity are one object: once it runs again, the band goes
            self.app.capture.stateChanged.connect(self._compute_resume)
        except Exception:  # noqa: BLE001
            pass
        self.refresh()
        self._compute_resume()
        self.recheck()
        self._announce_migration()

    def _announce_migration(self) -> None:
        """Once, on the start that migrated the workspace (3.x launch sets -> activities, 1.x import)."""
        store = self._store()
        if not store.migrated_from:
            return
        rep = store.migration or {}
        body = T.join_facts(T.plural(len(store.projects), "project"),
                            T.plural(len(store.activities), "activity", "activities") + " from your launch sets"
                            if rep.get("activities_from_sets") or rep.get("activities_from_pinned") else "")
        if rep:
            body += ". The 3.x workspace is kept in Backups (pre-v4)."
        self.app.toast.emit(f"Brought across from {store.migrated_from}", body, "success")

    def _on_store_event(self, event: str, payload: Any) -> None:
        self._refresh_timer.start()

    @Slot()
    def refresh(self) -> None:
        """Rebuild the models from ``app.ctx.store`` (row-level sync: delegates keep their place)."""
        store = self._store()
        projects = {p.id: p for p in store.projects}
        stale = self._stale()
        acts = store.sorted_activities()
        running = self._cap("runningId", "")
        acts.sort(key=lambda a: 0 if a.id == running else (1 if a.id in stale else 2))
        self._activities.sync([self.activity_row(a, projects, stale) for a in acts])
        self.activitiesChanged.emit()
        self._refresh_projects(projects)
        self._profiles.sync([{"profileId": pr.id, "name": pr.name, "appName": pr.app, "description": pr.description}
                             for pr in store.profiles])
        self._all_items.sync([
            {"itemKey": f"{p.id}|{it.id}", "name": it.display_name, "path": it.path, "kind": it.kind,
             "group": it.group, "projectId": p.id, "projectTitle": p.title, "glyph": item_glyph(it.kind, it.path),
             "inCurrent": self._in_current(p.id, it.id)}
            for p in store.sorted_projects() for it in p.items])
        if self._current_id:
            self._fill_current()
        if self._project_id:
            self._fill_project()

    def _in_current(self, project_id: str, item_id: str) -> bool:
        act = self._store().activity(self._current_id) if self._current_id else None
        return bool(act and any(i.project_id == project_id and i.source_item_id == item_id for i in act.items))

    def _refresh_projects(self, projects: dict[str, M.Project] | None = None) -> None:
        store = self._store()
        q = self._project_query.strip().lower()
        tag = self._project_tag
        rows = []
        for p in store.sorted_projects():
            if q and q not in (p.title + " " + p.search_blob()).lower():
                continue
            if tag and tag not in p.tags:
                continue
            rows.append(self.project_row(p, store.activities))
        self._projects.sync(rows)
        self.projectsChanged.emit()

    def _fill_current(self) -> None:
        store = self._store()
        act = store.activity(self._current_id)
        if act is None:
            self._current_id, self._current = "", {}
            self._items.reset([])
            self.currentChanged.emit()
            return
        projects = {p.id: p for p in store.projects}
        self._current = self.activity_row(act, projects, self._stale())
        self._items.sync([self.item_row(it, n, act.id, projects, self._item_health(act.id, it))
                          for n, it in enumerate(act.items, start=1)])
        self.currentChanged.emit()

    def _fill_project(self) -> None:
        store = self._store()
        p = store.get(self._project_id)
        if p is None:
            self._project_id, self._project = "", {}
            self._project_items.reset([])
            self.projectChanged.emit()
            return
        projects = {x.id: x for x in store.projects}
        h = self.app.ctx.health_for(p.id)
        row = self.project_row(p, store.activities)
        acts = store.activities_for_project(p.id)
        row.update(notes=p.notes, activityNames=[a.name for a in acts], activityIds=[a.id for a in acts],
                   publishedRevision=p.origin.revision, metaLine=T.join_facts(
                       f"{len(p.enabled_items)} of {T.plural(len(p.items), 'item')}",
                       T.plural(len(acts), "activity", "activities"),
                       f"opened {p.open_count}×" if p.open_count else "never opened"))
        self._project = row
        rows = []
        for n, it in enumerate(p.items, start=1):
            r = self.item_row(it, n, p.id, projects, h.status_for(it.id) if h else None)
            r["projectId"], r["projectTitle"] = p.id, p.title
            rows.append(r)
        self._project_items.sync(rows)
        self.projectChanged.emit()

    @Slot()
    def recheck(self) -> None:
        """Check every activity item's path on the pool (one host cache per pass), then refresh."""
        resolver = self.app.ctx.resolver
        snapshot = [(a.id, [M.Item.from_dict(i.to_dict()) for i in a.items]) for a in self._store().activities]

        def work() -> dict[str, dict[str, H.ItemHealth]]:
            hosts: dict[str, bool] = {}
            return {aid: {it.id: H.check_item(it, resolver, hosts) for it in items} for aid, items in snapshot}

        def done(result: dict[str, dict[str, H.ItemHealth]]) -> None:
            self._health = result
            for per_item in result.values():
                for h in per_item.values():
                    self._path_health[h.resolved.rstrip(r"\/").lower()] = h
            self._health_rev += 1
            self.healthChanged.emit()
            self.refresh()

        self.app.run_async(work, done)
        try:
            self.app.ctx.refresh_all_health()
        except Exception:  # noqa: BLE001
            pass

    @Slot(str, result="QVariantList")
    def pathHealth(self, path: str) -> list[str]:
        """[level, word] for any path (a live capture row): the cached check, else ["", ""] while a check
        runs on the pool; ``healthRev`` changes when it lands, so QML bindings that read it re-ask."""
        key = (path or "").strip().rstrip(r"\/").lower()
        if not key or key.startswith(("http://", "https://")):
            return ["", ""]
        h = self._path_health.get(key)
        if h is not None:
            return list(T.STATUS_META.get(h.status, ("neutral", "")))
        if key not in self._path_pending:
            self._path_pending.add(key)
            resolver = self.app.ctx.resolver
            item = M.Item(path=path)

            def done(res: H.ItemHealth) -> None:
                self._path_pending.discard(key)
                self._path_health[key] = res
                self._health_rev += 1
                self.healthChanged.emit()

            self.app.run_async(lambda: H.check_item(item, resolver), done)
        return ["", ""]

    @Slot(str)
    def select(self, activity_id: str) -> None:
        """Make ``activity_id`` the centre of the stage (fills ``current`` and ``items``)."""
        self._current_id = activity_id
        self._fill_current()
        try:
            self.app.capture.selectActivity(activity_id)
        except Exception:  # noqa: BLE001
            pass

    @Slot(str)
    def selectProject(self, project_id: str) -> None:  # noqa: N802
        self._project_id = project_id
        self._fill_project()

    @Slot(str, str)
    def setProjectFilter(self, query: str, tag: str) -> None:  # noqa: N802
        self._project_query, self._project_tag = query, tag
        self._refresh_projects()

    # ----------------------------------------------------------- launch
    @Slot(str)
    def open(self, activity_id: str) -> None:
        """Open the activity: launch its items (dock rows settle), mark it running, start capture.
        More than ``Settings.confirm_launch_over`` items asks first (``confirmNeeded``)."""
        act = self._store().activity(activity_id)
        if act is None:
            return
        n = len([i for i in act.enabled_items if i.path.strip()])
        limit = int(self.app.ctx.settings.confirm_launch_over or 0)
        if limit and n > limit:
            rid = uuid.uuid4().hex[:8]
            self._pending[rid] = ("activity", activity_id)
            self.confirmNeeded.emit(rid, activity_id, n)
            return
        self._launch_activity(act)

    @Slot(str, bool)
    def answerConfirm(self, request_id: str, ok: bool) -> None:  # noqa: N802
        kind, key = self._pending.pop(request_id, ("", ""))
        if not ok or not kind:
            return
        if kind == "activity":
            act = self._store().activity(key)
            if act is not None:
                self._launch_activity(act)
        elif kind == "project":
            proj = self._store().get(key)
            if proj is not None:
                self._launch_project(proj)

    def _window_visible(self) -> bool:
        win = getattr(self.app.ui, "_window", None)
        try:
            return bool(win is not None and win.isVisible())
        except Exception:  # noqa: BLE001
            return False

    def _begin_dock(self, key: str, title: str, line: str, color: str, task: str, items: list[M.Item]) -> None:
        self._dock.reset([{"order": n, "name": it.display_name, "path": it.path, "group": it.group,
                           "status": "queued", "statusLabel": "", "message": "", "level": "neutral",
                           "glyph": item_glyph(it.kind, it.path)} for n, it in enumerate(items, start=1)])
        self._dock_open, self._dock_id, self._dock_title, self._dock_line = True, key, title, line
        self._dock_color, self._dock_task = color, task
        self._dock_started_at = time.strftime("%H:%M")
        self._launching, self._launch_progress, self._launch_summary = True, 0.0, ""
        self.launchChanged.emit()
        self.progressChanged.emit()

    def _attach_run(self, run: Any, key: str) -> None:
        self._run = run
        run.sheet_shown = self._window_visible()
        n = max(1, len(run.items))
        codes: list[str] = ["queued"] * len(run.items)

        def started(i: int) -> None:
            if self._run is not run:
                return
            codes[i] = "opening"
            self._dock.update(i, status="opening", statusLabel="Opening…", level="opening")

        def finished(i: int, result: Any) -> None:
            if self._run is not run:
                return
            code = result.code if result.code in T.LAUNCH_META else result.status
            codes[i] = code
            level, word = T.LAUNCH_META.get(code, ("bad", "Failed"))
            self._dock.update(i, status=code, statusLabel=word, level=level, message=result.message or "",
                              path=result.resolved or self._dock.rows[i]["path"])
            self._launch_progress = (i + 1) / n
            # only the progress bar: every dock binding on Home hangs off launchChanged, and re-running them
            # for each row cost up to 175 ms of GUI time per settled row (juror U2-1, the bench's heartbeat)
            self.progressChanged.emit()

        def done(report: Any) -> None:
            if self._run is not run:
                return
            self._launching = False
            self._launch_progress = 1.0
            self._launch_summary = T.launch_footer(codes, run.elapsed)
            self.launchChanged.emit()
            self.progressChanged.emit()
            self.launchFinished.emit(key, self._launch_summary)
            self.recheck()

        run.item_started.connect(started)
        run.item_finished.connect(finished)
        run.finished.connect(done)

    def _launch_activity(self, act: M.Activity, only: set[str] | None = None) -> None:
        store = self._store()
        projects = {p.id: p for p in store.projects}
        items = [i for i in act.enabled_items if i.path.strip() and (only is None or i.id in only)]
        row = self.activity_row(act, projects)
        primary = projects.get(act.primary_project_id)
        line = T.join_facts(T.plural(len(items), "item"), primary.client if primary else "",
                            primary.title if primary else "")
        self._begin_dock(act.id, row["title"], line, row["dotColor"], row["taskLine"], items)
        run = self.app.ctx.launch_activity(act, items)
        if run is None:
            self._launching = False
            self.launchChanged.emit()
            return
        self._attach_run(run, act.id)
        self.launchStarted.emit(act.id)
        self._start_capture(act.id)

    def _start_capture(self, activity_id: str) -> None:
        """Every open marks the activity running (the RunningMarker the Resume band depends on); capture
        shows itself as paused when the activity's or the global switch is off (V4-SEAMS, builder 2 ask 2)."""
        try:
            self.app.capture.startActivity(activity_id)
        except Exception:  # noqa: BLE001
            log.exception("capture start failed")

    @Slot(str)
    def openProject(self, project_id: str) -> None:  # noqa: N802
        """3.x behaviour: open a project's enabled items (no capture)."""
        proj = self._store().get(project_id)
        if proj is None:
            return
        n = len([i for i in proj.enabled_items if i.path.strip()])
        limit = int(self.app.ctx.settings.confirm_launch_over or 0)
        if limit and n > limit:
            rid = uuid.uuid4().hex[:8]
            self._pending[rid] = ("project", project_id)
            self.confirmNeeded.emit(rid, project_id, n)
            return
        self._launch_project(proj)

    def _launch_project(self, proj: M.Project) -> None:
        items = [i for i in proj.enabled_items if i.path.strip()]
        self._begin_dock(proj.id, proj.title, T.join_facts(T.plural(len(items), "item"), proj.client),
                         proj.color, self._task_line("project", proj.id), items)
        run = self.app.ctx.launch(proj, items=items)
        if run is None:
            self._launching = False
            self.launchChanged.emit()
            return
        self._attach_run(run, proj.id)
        self.launchStarted.emit(proj.id)

    @Slot(str, str)
    def openItem(self, activity_id: str, item_id: str) -> None:  # noqa: N802
        act = self._store().activity(activity_id)
        it = act.item_by_id(item_id) if act else None
        if it is None:
            return
        self._open_one(it)

    @Slot(str, str)
    def openProjectItem(self, project_id: str, item_id: str) -> None:  # noqa: N802
        proj = self._store().get(project_id)
        it = proj.item_by_id(item_id) if proj else None
        if proj is not None and it is not None:
            self._open_one(it)

    def _open_one(self, item: M.Item) -> None:
        launcher = self.app.ctx.launcher

        def done(res: Any) -> None:
            if res.status == "opened":
                self.app.toast.emit(f"Opened {item.display_name}", "", "success")
            else:
                word = T.LAUNCH_META.get(res.code, ("bad", "Failed"))[1]
                self.app.toast.emit(f"Could not open {item.display_name}", res.message or word, "error")

        self.app.run_async(lambda: launcher.open_item(item), done)

    @Slot()
    def closeDock(self) -> None:  # noqa: N802
        self._dock_open = False
        self.launchChanged.emit()

    @Slot()
    def openFailedAgain(self) -> None:  # noqa: N802
        """"Open the 2 again": relaunch the dock's rows that did not open."""
        act = self._store().activity(self._dock_id)
        if act is None or self._run is None:
            return
        bad = {r["order"] for r in self._dock.rows if r["status"] not in ("opened", "skipped", "queued", "opening")}
        items = [it for n, it in enumerate(self._run.items, start=1) if n in bad]
        if not items:
            return
        projects = {p.id: p for p in self._store().projects}
        row = self.activity_row(act, projects)
        self._begin_dock(act.id, row["title"], T.plural(len(items), "item"), row["dotColor"], row["taskLine"], items)
        run = self.app.ctx.launch_activity(act, items)
        if run is not None:
            self._attach_run(run, act.id)

    # ----------------------------------------------------- activity CRUD
    @Slot(str, str, result=str)
    def create(self, name: str, project_id: str) -> str:
        """New empty activity attached to ``project_id`` (may be ""); returns its id."""
        name = (name or "").strip() or "New activity"
        proj = self._store().get(project_id) if project_id else None
        act = M.Activity(name=name, project_ids=[proj.id] if proj else [], color="")
        self._store().add_activity(act)
        self.created.emit("activity", act.id)
        return act.id

    @Slot(str, "QVariantMap")
    def edit(self, activity_id: str, fields: dict[str, Any]) -> None:
        """Set name, shortName, icon, color, description, notes, projectIds, captureOn, resumeOnStart."""
        act = self._store().activity(activity_id)
        if act is None:
            return
        f = dict(fields or {})
        if "name" in f and str(f["name"]).strip():
            act.name = str(f["name"]).strip()
        for key, attr in (("shortName", "short_name"), ("description", "description"), ("notes", "notes"),
                          ("color", "color")):
            if key in f:
                setattr(act, attr, str(f[key] or "").strip())
        if "icon" in f:
            ic = str(f["icon"] or "").strip()
            act.icon = ic if not ic or "." in ic else f"ph.{ic}"
        if "projectIds" in f:
            act.project_ids = [str(p) for p in (f["projectIds"] or []) if self._store().get(str(p))]
        if "captureOn" in f:
            act.capture_enabled = _bool(f["captureOn"])
        if "resumeOnStart" in f:
            act.resume_on_start = _bool(f["resumeOnStart"])
        self._store().update_activity(act)

    @Slot(str)
    def remove(self, activity_id: str) -> None:
        act = self._store().remove_activity(activity_id)
        if act is not None:
            self.app.toast.emit(f"Deleted {act.name}", "", "info")
            if self._current_id == activity_id:
                self._current_id, self._current = "", {}
                self.currentChanged.emit()

    @Slot(str, result=str)
    def duplicate(self, activity_id: str) -> str:
        act = self._store().activity(activity_id)
        if act is None:
            return ""
        copy = act.clone()
        self._store().add_activity(copy)
        return copy.id

    @Slot(str)
    def togglePin(self, activity_id: str) -> None:  # noqa: N802
        act = self._store().activity(activity_id)
        if act is None:
            return
        act.pinned_at = None if act.pinned else M.now_iso()
        self._store().update_activity(act)

    @Slot(str, "QStringList")
    def addPaths(self, activity_id: str, paths: list[str]) -> None:  # noqa: N802
        """Add files/folders/links as items (Explorer verb, Send to, drop, the add-item sheet).
        A path that is already one of the activity's items is not added twice; a path that is a
        project item stays linked to it."""
        act = self._store().activity(activity_id)
        if act is None:
            return
        added = 0
        for raw in paths or []:
            path = str(raw).strip().strip('"')
            if not path or act.item_by_path(path):
                continue
            link = self._project_item_for(path)
            if link is not None:
                proj, src = link
                it = M.ActivityItem.from_item(src, proj.id, src.id)
                it.id = M.new_id()
            else:
                it = M.ActivityItem(path=path, kind=M.guess_kind(path))
            act.items.append(it)
            added += 1
        if added:
            self._store().update_activity(act)
            self.app.toast.emit(f"Added {T.plural(added, 'item')} to {act.name}", "", "success")
            self.recheck()
        elif paths:
            self.app.toast.emit("Nothing new to add", f"Every path is already in {act.name}.", "info")

    def _project_item_for(self, path: str) -> tuple[M.Project, M.Item] | None:
        low = path.rstrip("\\/").lower()
        for p in self._store().projects:
            for it in p.items:
                if it.path.rstrip("\\/").lower() == low:
                    return p, it
        return None

    @Slot(str, str, str)
    def addProjectItem(self, activity_id: str, project_id: str, item_id: str) -> None:  # noqa: N802
        act = self._store().activity(activity_id)
        proj = self._store().get(project_id)
        src = proj.item_by_id(item_id) if proj else None
        if act is None or src is None or proj is None:
            return
        if any(i.project_id == project_id and i.source_item_id == item_id for i in act.items):
            return
        it = M.ActivityItem.from_item(src, proj.id, src.id)
        it.id = M.new_id()
        it.enabled = True
        act.items.append(it)
        if not act.project_ids:
            act.project_ids = [proj.id]
        self._store().update_activity(act)
        self.recheck()

    @Slot(str, str)
    def removeItem(self, activity_id: str, item_id: str) -> None:  # noqa: N802
        act = self._store().activity(activity_id)
        if act is None:
            return
        before = len(act.items)
        act.items = [i for i in act.items if i.id != item_id]
        if len(act.items) != before:
            self._store().update_activity(act)

    @Slot(str, str, int)
    def moveItem(self, activity_id: str, item_id: str, to_index: int) -> None:  # noqa: N802
        """Launch order: Move up / Move down in the editor."""
        act = self._store().activity(activity_id)
        if act is None:
            return
        idx = next((n for n, i in enumerate(act.items) if i.id == item_id), -1)
        if idx < 0:
            return
        to = max(0, min(len(act.items) - 1, int(to_index)))
        if to == idx:
            return
        act.items.insert(to, act.items.pop(idx))
        self._store().update_activity(act)

    @Slot(str, str, "QVariantMap")
    def editItem(self, activity_id: str, item_id: str, fields: dict[str, Any]) -> None:  # noqa: N802
        """path, label, kind, args, group, profileId, itemEnabled."""
        act = self._store().activity(activity_id)
        it = act.item_by_id(item_id) if act else None
        if act is None or it is None:
            return
        _apply_item_fields(it, fields)
        if {"path", "kind", "label", "args", "profileId"} & set(fields or {}):
            it.source_item_id = "" if "path" in (fields or {}) and it.source_item_id else it.source_item_id
        self._store().update_activity(act)
        self.recheck()

    # ------------------------------------------------------ project CRUD
    @Slot("QVariantMap", result=str)
    def createProject(self, fields: dict[str, Any]) -> str:  # noqa: N802
        f = dict(fields or {})
        p = M.Project(name=str(f.get("name") or "").strip() or "New project")
        _apply_project_fields(p, f)
        self._store().add(p)
        self.created.emit("project", p.id)
        return p.id

    @Slot(str, "QVariantMap")
    def editProject(self, project_id: str, fields: dict[str, Any]) -> None:  # noqa: N802
        p = self._store().get(project_id)
        if p is None:
            return
        _apply_project_fields(p, dict(fields or {}))
        self._store().update(p)

    @Slot(str)
    def removeProject(self, project_id: str) -> None:  # noqa: N802
        p = self._store().remove(project_id)
        if p is not None:
            self.app.toast.emit(f"Deleted {p.title}", "", "info")

    @Slot(str)
    def toggleProjectPin(self, project_id: str) -> None:  # noqa: N802
        self._store().toggle_pin(project_id)

    @Slot(str, "QStringList")
    def addProjectPaths(self, project_id: str, paths: list[str]) -> None:  # noqa: N802
        p = self._store().get(project_id)
        if p is None:
            return
        have = {i.path.rstrip("\\/").lower() for i in p.items}
        added = 0
        for raw in paths or []:
            path = str(raw).strip().strip('"')
            if not path or path.rstrip("\\/").lower() in have:
                continue
            p.items.append(M.Item(path=path, kind=M.guess_kind(path)))
            have.add(path.rstrip("\\/").lower())
            added += 1
        if added:
            self._store().update(p)
            self.app.toast.emit(f"Added {T.plural(added, 'item')} to {p.title}", "", "success")

    @Slot(str, str, "QVariantMap")
    def editProjectItem(self, project_id: str, item_id: str, fields: dict[str, Any]) -> None:  # noqa: N802
        p = self._store().get(project_id)
        it = p.item_by_id(item_id) if p else None
        if p is None or it is None:
            return
        _apply_item_fields(it, fields)
        self._store().update(p)

    @Slot(str, str)
    def removeProjectItem(self, project_id: str, item_id: str) -> None:  # noqa: N802
        p = self._store().get(project_id)
        if p is None:
            return
        p.items = [i for i in p.items if i.id != item_id]
        self._store().update(p)

    @Slot(str, result=str)
    def portable(self, path: str) -> str:
        """The portable form of a path (drive letter -> UNC / variable), as items store it."""
        try:
            return self.app.ctx.resolver.portable(path)
        except Exception:  # noqa: BLE001
            return path

    @Slot(str, result=str)
    def newActivityFromProject(self, project_id: str) -> str:  # noqa: N802
        """An activity holding the project's enabled items, linked to it."""
        p = self._store().get(project_id)
        if p is None:
            return ""
        act = M.Activity(name=p.name, project_ids=[p.id],
                         items=[M.ActivityItem.from_item(i, p.id, i.id) for i in p.enabled_items])
        for it in act.items:
            it.id = M.new_id()
        self._store().add_activity(act)
        self.created.emit("activity", act.id)
        return act.id

    # ------------------------------------------------------------ resume
    def _compute_resume(self) -> None:
        store = self._store()
        best: tuple[str, M.Activity, M.Snapshot | None] | None = None
        for aid, marker in self._stale().items():
            act = store.activity(aid)
            if act is None or not act.resume_on_start or aid in self._resume_dismissed:
                continue
            if self._cap("runningId", "") == aid:
                continue                        # it runs again: the band and the activity are one object
            try:
                snap = self.app.snapshots.latest(aid)
            except Exception:  # noqa: BLE001
                snap = None
            when = (snap.taken_at if snap else "") or marker.last_seen
            if best is None or when > best[0]:
                best = (when, act, snap)
        if best is None:
            new: dict[str, Any] = {}
        else:
            when, act, snap = best
            proj = store.get(act.primary_project_id)
            count = snap.open_count if snap and snap.entries else len(act.enabled_items)
            title, text = T.resume_text(act.name, count, when, proj.spine if proj else "")
            new = {"activityId": act.id, "title": title, "count": count, "takenAt": T.clock(when), "text": text,
                   "name": act.name}
        if new != self._resume:
            self._resume = new
            self.resumeChanged.emit()

    @Slot()
    def resumeNow(self) -> None:  # noqa: N802
        """The Resume band's button: mark the activity running in this process (``startActivity`` replaces
        the stale marker), then restore its latest snapshot on the capture thread, so the live list follows
        the reopened windows (V4-SEAMS, builder 2 ask 2)."""
        aid = self._resume.get("activityId", "")
        if not aid:
            return
        try:
            snap = self.app.snapshots.latest(aid)
        except Exception:  # noqa: BLE001
            snap = None
        act = self._store().activity(aid)
        cap = self.app.capture
        sheet = bool(getattr(cap, "resume_prepared", None) and cap.resume_prepared(aid))
        if (snap is None or not snap.entries) and act is not None:
            # nothing captured yet: open its items in launch order (only those ticked in the sheet)
            ticked = {k[len("item:"):] for k in cap.resume_ticked() if k.startswith("item:")} if sheet else None
            self._launch_activity(act, only=ticked)
        else:
            self._resume_restore(aid, sheet)
        self._resume_dismissed.add(aid)
        self._resume = {}
        self.resumeChanged.emit()
        self.refresh()

    def _resume_restore(self, aid: str, ticked_only: bool = False) -> None:
        self._start_capture(aid)
        try:
            if ticked_only:
                self.app.capture.restoreTicked(aid)      # the Resume sheet: only what stayed ticked
            else:
                self.app.capture.restoreLatest(aid)
        except Exception:  # noqa: BLE001
            log.exception("restore failed")
            self.app.toast.emit("Could not resume", "See the log for details.", "error")

    @Slot()
    def dismissResume(self) -> None:  # noqa: N802
        """Dismiss keeps the snapshot (it stays restorable from the activity's checkpoints); the
        stale marker is cleared so the band does not come back at the next start."""
        aid = self._resume.get("activityId", "")
        if not aid:
            return
        self._resume_dismissed.add(aid)
        try:
            self.app.snapshots.clear_running(aid)
        except Exception:  # noqa: BLE001
            log.exception("could not clear the running marker")
        self._resume = {}
        self.resumeChanged.emit()
        self._compute_resume()
        self.refresh()

    # -------------------------------------------------------------- misc
    @Slot(str)
    def mailBundle(self, activity_id: str) -> None:  # noqa: N802
        """Outlook: the activity's items as links (``core.mail``)."""
        act = self._store().activity(activity_id)
        if act is None:
            return
        from project_opener.core import mail
        from project_opener.ipc import make_link
        # a mail goes to other PCs, where activity ids differ: the link names the activity (V4-SEAMS, builder 1
        # note 6; open_link looks names up too)
        resolver, client, link = self.app.ctx.resolver, self.app.ctx.settings.mail_client, make_link("activity", act.name)

        def work() -> bool:
            return mail.open_draft(mail.bundle_draft(act, resolver, link), client)

        def done(opened: bool) -> None:
            if not opened:
                self.app.toast.emit("Could not start the mail", "Neither Outlook nor a mail app answered.", "warning")

        def fail(exc: Exception) -> None:
            self.app.toast.emit("Could not start the mail", str(exc) or type(exc).__name__, "warning")

        self.app.run_async(work, done, fail)

    @Slot(str, result=str)
    def link(self, activity_id: str) -> str:
        """``projectopener://activity/<id>`` for copy-link."""
        from project_opener.ipc import make_link
        return make_link("activity", activity_id)

    @Slot(str)
    def copyLink(self, activity_id: str) -> None:  # noqa: N802
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(self.link(activity_id))
        self.app.toast.emit("Link copied", self.link(activity_id), "info")


PROJECT_ICONS = ("folder", "compass", "ruler", "factory", "anchor", "cube", "buildings", "wrench", "map-trifold",
                 "lightning", "tree-structure", "clipboard-text", "stack", "rocket-launch", "star", "flag")


def _icon(name: str, default: str = "stack") -> str:
    from project_opener.quick.ui_state import icon_name
    return icon_name(name, default)


def _apply_item_fields(it: M.Item, fields: dict[str, Any]) -> None:
    f = dict(fields or {})
    if "path" in f and str(f["path"]).strip():
        it.path = str(f["path"]).strip()
    for key, attr in (("label", "label"), ("args", "args"), ("group", "group"), ("profileId", "profile_id")):
        if key in f:
            setattr(it, attr, str(f[key] or "").strip())
    if "kind" in f and str(f["kind"]) in M.ITEM_KINDS:
        it.kind = str(f["kind"])
    if "itemEnabled" in f:
        it.enabled = _bool(f["itemEnabled"])


def _apply_project_fields(p: M.Project, f: dict[str, Any]) -> None:
    if "name" in f and str(f["name"]).strip():
        p.name = str(f["name"]).strip()
    for key, attr in (("client", "client"), ("jobNumber", "job_number"), ("description", "description"),
                      ("notes", "notes")):
        if key in f:
            setattr(p, attr, str(f[key] or "").strip())
    if "color" in f and str(f["color"]).startswith("#"):
        p.color = str(f["color"])
    if "icon" in f and str(f["icon"]).strip():
        ic = str(f["icon"]).strip()
        p.icon = ic if "." in ic else f"ph.{ic}"
    if "tags" in f:
        raw = f["tags"]
        tags = raw.split(",") if isinstance(raw, str) else list(raw or [])
        p.tags = [str(t).strip() for t in tags if str(t).strip()]
