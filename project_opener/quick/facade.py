"""``AppFacade``: the "AppContext v4", the one object the QML shell and the pill talk to.  Owner: builder 4.

It composes the 3.2 ``AppContext`` (store, settings, resolver, launcher, hub,
presence, updater, thread pool, launch queue, health) unchanged, adds the v4
services, and exposes one sub-object per domain to QML as the context property
``app``::

    app.ui          UiState       tokens, motion, routing                  (builder 4)
    app.activities  ActivitiesApi activities, projects, dock, Resume band  (builder 4)
    app.settings    SettingsApi   settings by key, dialogs, secrets        (builder 4)
    app.capture     CaptureApi    running activity, snapshot, checkpoints  (builder 2)
    app.hub         HubApi        people, publish/for, inbox, groups, @    (builder 1)
    app.tasks       TasksApi      tasks                                    (builder 1)
    app.watchers    WatchersApi   watchers, alerts, drive map              (builder 1)
    app.desktop     DesktopApi    pill, hotkeys, picker, tray, quiet       (builder 3; set by app_v4)

Threads (docs/V4-ARCHITECTURE.md section 6): every property, model and signal
here lives on the GUI thread.  Work goes to the pool through ``run_async``;
the capture thread posts results through ``run_on_gui``.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from project_opener import constants as C
from project_opener.core.snapshots import SnapshotStore
from project_opener.quick.activities_api import ActivitiesApi
from project_opener.quick.capture_api import CaptureApi
from project_opener.quick.hub_api import HubApi
from project_opener.quick.settings_api import SettingsApi
from project_opener.quick.tasks_api import TasksApi
from project_opener.quick.ui_state import UiState
from project_opener.quick.watchers_api import WatchersApi
from project_opener.ui.context import AppContext

log = logging.getLogger(__name__)


class AppFacade(QObject):
    toast = Signal(str, str, str)                          # title, body, level (info|success|warning|error)
    toastAction = Signal(str, str, str, str, str, "QVariantMap")  # title, body, level, button, route, payload
    showWindowRequested = Signal()                         # raise the main window (ipc "show", tray, deep link)
    paletteRequested = Signal()                            # Ctrl+Alt+K
    chooserRequested = Signal("QStringList")               # paths to add when no activity runs (Explorer/Send to)
    desktopChanged = Signal()

    def __init__(self, data_dir: Path | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.ctx = AppContext(data_dir)
        self.snapshots = SnapshotStore(data_dir or C.data_dir())
        self._ui = UiState(self)
        self._activities = ActivitiesApi(self)
        self._settings = SettingsApi(self)
        self._capture = CaptureApi(self)
        self._hub = HubApi(self)
        self._tasks = TasksApi(self)
        self._watchers = WatchersApi(self)
        self._desktop: QObject | None = None
        self.ctx.toast.connect(lambda t, b, lvl: self.toast.emit(t, b, lvl))

    # ------------------------------------------------------- sub-objects
    @Property(QObject, constant=True)
    def ui(self) -> UiState:
        return self._ui

    @Property(QObject, constant=True)
    def activities(self) -> ActivitiesApi:
        return self._activities

    @Property(QObject, constant=True)
    def settings(self) -> SettingsApi:
        return self._settings

    @Property(QObject, constant=True)
    def capture(self) -> CaptureApi:
        return self._capture

    @Property(QObject, constant=True)
    def hub(self) -> HubApi:
        return self._hub

    @Property(QObject, constant=True)
    def tasks(self) -> TasksApi:
        return self._tasks

    @Property(QObject, constant=True)
    def watchers(self) -> WatchersApi:
        return self._watchers

    @Property(QObject, notify=desktopChanged)
    def desktop(self) -> QObject | None:
        return self._desktop

    def set_desktop(self, api: QObject) -> None:
        self._desktop = api
        self.desktopChanged.emit()

    @Property(str, constant=True)
    def version(self) -> str:
        return C.VERSION

    @Property(str, constant=True)
    def login(self) -> str:
        return self.ctx.user

    @Property(str, constant=True)
    def displayName(self) -> str:  # noqa: N802
        return self.ctx.display_name()

    # ---------------------------------------------------------- threads
    def run_async(self, fn: Callable, done: Callable | None = None, fail: Callable | None = None) -> None:
        self.ctx.run_async(fn, done, fail)

    def run_on_gui(self, fn: Callable) -> None:
        self.ctx.run_on_gui(fn)

    # -------------------------------------------------------- lifecycle
    def _apis(self) -> list[Any]:
        return [self._ui, self._activities, self._settings, self._capture, self._hub, self._tasks, self._watchers]

    @Slot()
    def start(self) -> None:
        """Called once the window is up: 3.2 services, then each sub-API (errors logged, never fatal)."""
        self.ctx.start()
        for api in self._apis():
            try:
                api.start()
            except NotImplementedError:
                pass
            except Exception:  # noqa: BLE001
                log.exception("start failed: %s", type(api).__name__)

    def shutdown(self) -> None:
        for api in reversed(self._apis()):
            try:
                api.shutdown()
            except Exception:  # noqa: BLE001
                log.exception("shutdown failed: %s", type(api).__name__)
        self.ctx.shutdown()

    # ------------------------------------------------- socket / CLI commands
    @Slot("QVariantMap")
    def handle_command(self, cmd: dict[str, Any]) -> None:
        """One ``ipc`` command (from a second instance or this process's own CLI arguments).

        show -> raise the window; open -> deep link; add/sendto -> add to the running activity, or the
        chooser when none runs; snapshot -> checkpoint; start-from-open -> the sheet.
        """
        from project_opener.ipc import parse_link
        name = cmd.get("cmd")
        try:
            if name == "show":
                self.showWindowRequested.emit()
            elif name == "open":
                kind, key = parse_link(str(cmd.get("link", "")))
                self.showWindowRequested.emit()
                self.open_link(kind, key)
            elif name in ("add", "sendto"):
                paths = [str(p) for p in cmd.get("paths") or []]
                running = self._capture.runningId
                if running:
                    self._activities.addPaths(running, paths)
                else:
                    self.showWindowRequested.emit()
                    self.chooserRequested.emit(paths)
            elif name == "snapshot":
                self._capture.snapshotNow()
            elif name == "start-from-open":
                self.showWindowRequested.emit()
                self._capture.prepareStartFromOpen()
                self._ui.go("home", {"sheet": "start-from-open"})
            else:
                log.warning("unknown command %r", cmd)
        except NotImplementedError as exc:
            log.warning("command %s not available yet (%s)", name, exc)

    def open_link(self, kind: str, key: str) -> None:
        """``projectopener://open/<project>`` | ``activity/<activity>`` | ``task/<id>``."""
        store = self.ctx.store
        if kind == "open":
            proj = store.get(key) or store.by_name(key)
            if proj:
                self._ui.go("project", {"projectId": proj.id})
        elif kind == "activity":
            act = store.activity(key) or store.activity_by_name(key)
            if act:
                self._ui.go("activity", {"activityId": act.id})
        elif kind == "task":
            self._ui.go("hub", {"tab": "tasks", "taskId": key})
