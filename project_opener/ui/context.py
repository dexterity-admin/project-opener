"""AppContext - the one object every view talks to.

It owns the core services (store, settings, resolver, launcher, hub, presence,
updater), runs background work on a thread pool and turns results into Qt
signals.  Views never touch the filesystem or the network directly.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import QMessageBox, QWidget

from project_opener import constants as C
from project_opener.core import health as H
from project_opener.core import models as M
from project_opener.core.launcher import Launcher, LaunchReport
from project_opener.core.pathvars import PathResolver
from project_opener.core.settings import Settings
from project_opener.core.store import WorkspaceStore
from project_opener.lan.hub import HubStatus, Peer, TeamHub
from project_opener.lan.presence import PresenceBeacon
from project_opener.update.updater import CheckResult, UpdateInfo, Updater

log = logging.getLogger(__name__)


class _Job(QRunnable):
    def __init__(self, fn: Callable, done: Callable | None = None, fail: Callable | None = None):
        super().__init__()
        self.fn, self.done, self.fail = fn, done, fail
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001
            log.exception("background job failed")
            if self.fail:
                self.fail(exc)
            return
        if self.done:
            self.done(result)


class AppContext(QObject):
    projects_changed = Signal()
    project_updated = Signal(str)            # project id
    health_updated = Signal(str)             # project id
    hub_changed = Signal(object)             # HubStatus
    peers_changed = Signal(list)             # list[Peer]
    update_checked = Signal(object)          # CheckResult
    update_progress = Signal(int, int)
    update_ready = Signal(object)            # Path to installer
    update_failed = Signal(str)
    toast = Signal(str, str, str)            # title, body, level
    toast_action = Signal(str, str, str, str, object)  # title, body, level, button label, navigate (route, payload)
    navigate = Signal(str, object)           # route, payload
    _invoke = Signal(object)                 # run callable on the GUI thread

    def __init__(self, data_dir: Path | None = None):
        super().__init__()
        self.settings = Settings.load(data_dir)
        self.store = WorkspaceStore(data_dir)
        self.user = M.current_user()
        self.resolver = PathResolver(self.settings.variables)
        self.launcher = Launcher(self.resolver, delay_ms=self.settings.launch_delay_ms)
        self.hub = TeamHub(self.settings.hub_path or None, self.user, self.settings.display_name, self.settings.role)
        self.beacon: PresenceBeacon | None = None
        self.updater = Updater(token=self.settings.github_token, lan_dir=self.hub.updates_dir(),
                               channel=self.settings.update_channel)
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max(2, min(6, self.pool.maxThreadCount())))
        self.health: dict[str, H.ProjectHealth] = {}
        self._health_pending: set[str] = set()
        self.hub_status: HubStatus = HubStatus()
        self.peers: list[Peer] = []
        self.last_check: CheckResult | None = None   # survives page rebuilds (retheme)
        self.downloaded: Path | None = None          # verified installer from the last download
        self.current_project_name = ""
        self._seen_revisions: set[tuple[str, int]] = set()
        self.window: QWidget | None = None
        self._lock = threading.Lock()
        self._invoke.connect(self._run_on_gui)
        self.store.subscribe(self._on_store_event)

        self.hub_timer = QTimer(self)
        self.hub_timer.setInterval(C.HUB_HEARTBEAT_S * 1000)
        self.hub_timer.timeout.connect(self.refresh_hub)
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(C.UPDATE_CHECK_INTERVAL_H * 3600 * 1000)
        self.update_timer.timeout.connect(lambda: self.check_updates(silent=True))

    # ---------------------------------------------------------- lifecycle
    def start(self) -> None:
        self.refresh_hub()
        self.hub_timer.start()
        if self.settings.presence_udp:
            self.start_beacon()
        if self.settings.update_check:
            QTimer.singleShot(8000, lambda: self.check_updates(silent=True))
            self.update_timer.start()
        self.refresh_all_health()

    def shutdown(self) -> None:
        try:
            self.hub.sign_off()
        except Exception:  # noqa: BLE001
            pass
        if self.beacon:
            self.beacon.stop()
        self.settings.save()

    def start_beacon(self) -> None:
        if self.beacon:
            return
        self.beacon = PresenceBeacon(self.user, self.settings.display_name, on_peer=self._on_udp_peer)
        self.beacon.start()

    def stop_beacon(self) -> None:
        if self.beacon:
            self.beacon.stop()
            self.beacon = None

    # --------------------------------------------------------- gui thread
    def run_on_gui(self, fn: Callable) -> None:
        try:
            self._invoke.emit(fn)
        except RuntimeError:  # a pool job finished after the context was destroyed (shutdown)
            pass

    @Slot(object)
    def _run_on_gui(self, fn: Callable) -> None:
        try:
            fn()
        except RuntimeError as exc:  # a widget the job targeted was deleted meanwhile
            log.debug("gui callback skipped: %s", exc)

    @property
    def last_update(self) -> CheckResult | None:  # backwards-compatible alias
        return self.last_check

    @last_update.setter
    def last_update(self, value: CheckResult | None) -> None:
        self.last_check = value

    def run_async(self, fn: Callable, done: Callable | None = None, fail: Callable | None = None) -> None:
        self.pool.start(_Job(fn, (lambda r: self.run_on_gui(lambda: done(r))) if done else None,
                             (lambda e: self.run_on_gui(lambda: fail(e))) if fail else None))

    # ---------------------------------------------------------- settings
    def apply_settings(self) -> None:
        """Call after editing settings: rebuilds resolver/launcher/hub."""
        self.settings.save()
        self.resolver = PathResolver(self.settings.variables)
        self.launcher = Launcher(self.resolver, delay_ms=self.settings.launch_delay_ms)
        hub_path = self.settings.hub_path or None
        if str(self.hub.root or "") != str(hub_path or ""):
            self.hub = TeamHub(hub_path, self.user, self.settings.display_name, self.settings.role)
            self.health.clear()
        else:
            self.hub.display_name = self.settings.display_name
            self.hub.role = self.settings.role
        self.updater = Updater(token=self.settings.github_token, lan_dir=self.hub.updates_dir(),
                               channel=self.settings.update_channel)
        if self.settings.presence_udp:
            self.start_beacon()
            if self.beacon:
                self.beacon.display_name = self.settings.display_name
        else:
            self.stop_beacon()
        if self.beacon:
            self.beacon.current_project = self.current_project_name if self.settings.hub_share_pulse else ""
        if self.settings.update_check:
            if not self.update_timer.isActive():
                self.update_timer.start()
        else:
            self.update_timer.stop()
        self.refresh_hub()
        self.refresh_all_health()
        self.projects_changed.emit()

    # -------------------------------------------------------------- store
    def _on_store_event(self, event: str, payload) -> None:
        if event in ("added", "updated", "removed", "changed", "imported"):
            self.projects_changed.emit()
            if event in ("added", "updated") and isinstance(payload, M.Project):
                self.project_updated.emit(payload.id)
                self.schedule_health(payload)

    # -------------------------------------------------------------- launch
    def launch(self, project: M.Project, launch_set: M.LaunchSet | None = None, items: list[M.Item] | None = None,
               parent: QWidget | None = None) -> LaunchReport | None:
        if items is None:
            items = project.items_for_set(launch_set) if launch_set else project.enabled_items
        items = [i for i in items if i.path.strip()]
        if not items:
            self.toast.emit("Nothing to open", f"'{project.name}' has no enabled items.", "warning")
            return None
        limit = self.settings.confirm_launch_over
        if limit and len(items) > limit and parent is not None:
            ans = QMessageBox.question(parent, "Open many items?",
                                       f"This will open {len(items)} items at once. Continue?",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ans != QMessageBox.StandardButton.Yes:
                return None
        report = self.launcher.launch(items)
        set_name = launch_set.name if launch_set else ""
        self.store.record_launch(project, items, set_name, ok=len(report.opened), missing=len(report.missing))
        self.current_project_name = project.name
        if self.settings.hub_share_pulse:
            self.run_async(lambda: self.hub.pulse("launched", project.name + (f" › {set_name}" if set_name else "")))
            self.run_async(lambda: self.hub.heartbeat(current_project=project.name))
            if self.beacon:
                self.beacon.current_project = project.name
        if report.ok:
            self.toast.emit(f"Opened {project.name}", f"{len(report.opened)} item(s)" + (f" · {set_name}" if set_name else ""), "success")
        else:
            problems = report.missing + report.failed
            body = "\n".join(f"• {r.item.display_name}: {r.message}" for r in problems[:5])
            if len(problems) > 5:
                body += f"\n… and {len(problems) - 5} more"
            self.toast.emit(f"{project.name}: {report.summary()}", body, "warning")
        self.schedule_health(project)
        return report

    def open_single(self, project: M.Project, item: M.Item) -> None:
        res = self.launcher.open_item(item)
        if res.status == "opened":
            self.store.record_launch(project, [item], ok=1)
            self.toast.emit(f"Opened {item.display_name}", "", "success")
        else:
            self.toast.emit(f"Could not open {item.display_name}", res.message or res.status, "error")

    # -------------------------------------------------------------- health
    def schedule_health(self, project: M.Project) -> None:
        pid = project.id
        with self._lock:
            if pid in self._health_pending:
                return
            self._health_pending.add(pid)
        resolver = self.resolver
        snapshot = M.Project.from_dict(project.to_dict())

        def work() -> H.ProjectHealth:
            return H.check_project(snapshot, resolver)

        def done(result: H.ProjectHealth) -> None:
            with self._lock:
                self._health_pending.discard(pid)
            self.health[pid] = result
            self.health_updated.emit(pid)

        def fail(_exc) -> None:
            with self._lock:
                self._health_pending.discard(pid)

        self.run_async(work, done, fail)

    def refresh_all_health(self) -> None:
        for p in self.store.projects:
            self.schedule_health(p)

    def health_for(self, project_id: str) -> H.ProjectHealth | None:
        return self.health.get(project_id)

    # ----------------------------------------------------------------- hub
    def refresh_hub(self) -> None:
        hub = self.hub
        current = self.current_project_name if self.settings.hub_share_pulse else ""
        clones = [p for p in self.store.projects if p.origin.source == "team" and p.origin.published_id]

        def work():
            if hub.configured:
                hub.heartbeat(current_project=current)
            newer = []
            if hub.reachable():
                for p in clones:
                    pub = hub.newer_revision(p)
                    if pub:
                        newer.append((p, pub))
            return hub.status(), hub.peers(), newer

        def done(result) -> None:
            status, peers, newer = result
            self.hub_status = status
            self.peers = self._merge_peers(peers)
            self.hub_changed.emit(status)
            self.peers_changed.emit(self.peers)
            self._notify_revisions(newer)

        self.run_async(work, done)

    def _notify_revisions(self, newer: list) -> None:
        """Toast once per (published id, revision) when a cloned project has a newer revision on the hub."""
        for project, pub in newer:
            key = (pub.published_id, int(pub.revision))
            if key in self._seen_revisions:
                continue
            self._seen_revisions.add(key)
            self.toast_action.emit(f"New revision of {project.name}",
                                   f"{pub.author} published revision {pub.revision} to the Team Hub.",
                                   "info", "Open project", ("project", project))

    def _merge_peers(self, hub_peers: list[Peer]) -> list[Peer]:
        merged = {p.user: p for p in hub_peers}
        if self.beacon:
            for p in self.beacon.online():
                cur = merged.get(p.user)
                if cur is None or p.ts > cur.ts:
                    if cur:
                        p.display_name = p.display_name or cur.display_name
                        p.role = cur.role
                    merged[p.user] = p
        peers = list(merged.values())
        peers.sort(key=lambda p: (not p.online, p.label.lower()))
        return peers

    def _on_udp_peer(self, peer: Peer) -> None:
        # Called on the beacon thread; merge the hub's last-known peers with the live UDP set.
        def apply() -> None:
            hub_peers = [p for p in self.peers if p.source != "udp"]
            self.peers = self._merge_peers(hub_peers)
            self.peers_changed.emit(self.peers)

        self.run_on_gui(apply)

    # ------------------------------------------------------------- updates
    def check_updates(self, silent: bool = False) -> None:
        updater = self.updater

        def done(result: CheckResult) -> None:
            self.last_check = result
            self.settings.update_last_check = M.now_iso()
            self.settings.save()
            self.update_checked.emit(result)
            if result.available and result.update and result.update.version != self.settings.update_skip_version:
                self.toast_action.emit(f"Update {result.update.version} available",
                                       f"From {'LAN hub' if result.update.source == 'lan' else 'GitHub'}",
                                       "info", "Open Updates", ("updates", None))
            elif not silent and not result.available:
                msg = "You are on the latest version." if not result.errors else "; ".join(result.errors)
                self.toast.emit("No update found", msg, "info" if not result.errors else "warning")

        self.run_async(updater.check, done, lambda e: self.update_failed.emit(str(e)))

    def download_update(self, info: UpdateInfo) -> None:
        updater = self.updater

        def work() -> Path:
            return updater.download(info, progress=lambda d, t: self.update_progress.emit(d, t))

        def done(path: Path) -> None:
            self.downloaded = path
            self.update_ready.emit(path)

        self.run_async(work, done, lambda e: self.update_failed.emit(str(e)))

    def install_update(self, installer: Path) -> None:
        self.updater.install(installer)
        from PySide6.QtWidgets import QApplication
        QTimer.singleShot(400, QApplication.instance().quit)

    # ---------------------------------------------------------------- misc
    def display_name(self) -> str:
        return self.settings.display_name or self.user
