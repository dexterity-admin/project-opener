"""``app.watchers``: watcher rules, alerts, and the office-wide drive map (footlights).
Owner: builder 1 (CORE+HUB).

Runs ``core.watchers.WatcherEngine.tick`` on the pool every ``WATCH_TICK_S``;
hits go through ``lan.delivery.Dispatcher`` (toast via the facade, pulse,
inbox for mentions, Cliq) exactly once per event key.

Threading (docs/V4-ARCHITECTURE.md section 6): a GUI ``QTimer`` gathers the
inputs (copies) and starts one tick on the pool; a tick still running skips the
next timer shot.  Delivery runs on the pool too; toasts and model updates come
back on the GUI thread.  Other sub-APIs reach the dispatcher through
``app.watchers.dispatcher()`` and feed hub events through ``push_hub_events``.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from project_opener import constants as C
from project_opener.core import health as H
from project_opener.core import models as M
from project_opener.core.tasks import when_text
from project_opener.core.watchers import HubEvents, WatcherEngine
from project_opener.lan.delivery import Dispatcher, make_dispatcher
from project_opener.lan.healthboard import HealthBoard, OfficeRoot, observe
from project_opener.quick.base import ApiBase
from project_opener.quick.listmodel import DictListModel
from project_opener.ui import text as T

log = logging.getLogger(__name__)

WATCHER_ROLES = ("watcherId", "name", "kind", "target", "events", "watcherEnabled", "notifyText", "lastHitText",
                 "activityId", "projectId")
ALERT_ROLES = ("alertKey", "ts", "tsText", "title", "detail", "level", "link", "unread", "watcherId")
ROOT_ROLES = ("rootName", "status", "statusLabel", "mapping", "uses", "seenBy", "since", "sinceText", "jobsAffected")

STATUS_LABELS = {"ok": "Reachable", "offline": "Server not answering", "missing": "Not found on this PC",
                 "variable": "Variable not defined on this PC"}


SINCE_WORDS = {"offline": "down", "missing": "missing", "variable": "undefined"}


def new_files_fact(rows: list[dict[str, Any]], watchers: list[Any], activity_id: str,
                   is_item: Any = None) -> dict[str, Any]:
    """Pure: the files an activity's folder watchers found new and nobody has dealt with (unread "new" alerts),
    as the centre card's figure: {count, text, time (ISO), paths, keys}; {} when there are none.

    One alert per file has the file as ``path``; a collapsed alert ("12 new files in Revision C") has the
    folder as ``path`` and the names in ``detail``.  Files that are already items are not counted."""
    ids = {w.id: w for w in watchers if getattr(w, "activity_id", "") == activity_id and w.kind == "folder"}
    paths: list[str] = []
    keys: list[str] = []
    titles: list[str] = []
    latest = ""
    for r in rows:
        if r.get("read") or r.get("event") != "new" or str(r.get("watcher_id", "")) not in ids:
            continue
        path, detail = str(r.get("path", "")), str(r.get("detail", ""))
        names = [n.strip() for n in detail.split(" and ")[0].split(",") if n.strip()] if detail else []
        found = [os.path.join(path, n) for n in names] if names and not os.path.splitext(path)[1] else [path]
        found = [f for f in found if f and not (is_item and is_item(f))]
        if not found:
            continue
        keys.append(str(r.get("key", "")))
        titles.append(str(r.get("title", "")))
        for f in found:
            if f.lower() not in {x.lower() for x in paths}:
                paths.append(f)
        latest = max(latest, str(r.get("ts", "")))
    if not paths:
        return {}
    folder = os.path.basename(os.path.dirname(paths[0]).rstrip(r"\/")) or paths[0]
    text = titles[0] if len(titles) == 1 and titles[0][:1].isdigit() else f"{len(paths)} new in {folder}"
    return {"count": len(paths), "text": text, "time": latest, "paths": paths, "keys": keys}


def since_text(status: str, since_iso: str, seen_by: int) -> str:
    """"down since 14:45 · seen by 2 PCs" for a root that is not reachable; "" for one that is."""
    if status == "ok":
        return ""
    when = T.when_text(since_iso)
    first = f"{SINCE_WORDS.get(status, 'not reachable')} since {when}" if when else ""
    return T.join_facts(first, f"seen by {T.plural(seen_by, 'PC')}" if seen_by else "")


def notify_text(n: M.Notify) -> str:
    parts = ["Toast"] if n.toast else []
    parts += [f"@{m.lstrip('@')}" for m in n.mentions]
    if n.cliq_dm:
        parts.append("Cliq DM")
    if n.cliq_channel:
        parts.append(f"#{n.cliq_channel.lstrip('#')}")
    return " · ".join(parts) or "Alert list only"


def notify_from(d: dict[str, Any] | None) -> M.Notify:
    """QML's {toast, mentions, cliqDm, cliqChannel} (or the snake_case form) -> Notify."""
    d = d or {}
    return M.Notify.from_dict({"toast": d.get("toast", True), "mentions": d.get("mentions", []),
                               "cliq_dm": d.get("cliqDm", d.get("cliq_dm", False)),
                               "cliq_channel": d.get("cliqChannel", d.get("cliq_channel", ""))})


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
        self._engine: WatcherEngine | None = None
        self._dispatcher: Dispatcher | None = None
        self._dispatcher_key: tuple[Any, ...] | None = None
        self._pending = HubEvents()
        self._ticking = False
        self._roots_busy = False
        self._local_roots: dict[str, str] = {}             # this PC: root -> status (health watchers)
        self._root_since: dict[str, tuple[str, str]] = {}
        self._last_hit: dict[str, str] = {}
        self._alert_raw: list[dict[str, Any]] = []
        self._timer: QTimer | None = None
        self._retry_timer: QTimer | None = None
        self._roots_timer: QTimer | None = None

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
    def unreadCount(self) -> int:  # noqa: N802
        return sum(1 for r in self._alerts.rows if r.get("unread"))

    # ------------------------------------------------------------ helpers
    @property
    def ctx(self) -> Any:
        return self.app.ctx

    @property
    def data_dir(self) -> Path:
        return Path(self.ctx.store.root)

    def engine(self) -> WatcherEngine:
        if self._engine is None:
            self._engine = WatcherEngine(self.data_dir / C.WATCH_STATE_DIR, self.ctx.resolver)
        self._engine.resolver = self.ctx.resolver          # apply_settings rebuilds the resolver
        return self._engine

    def dispatcher(self) -> Dispatcher:
        """The delivery dispatcher for the current hub and Cliq settings (rebuilt when they change)."""
        st, hub = self.ctx.settings, self.ctx.hub
        key = (str(hub.root or ""), st.cliq_api_base, st.cliq_bot, st.cliq_token_enc, st.cliq_user_id,
               st.notify_cliq_default)
        if self._dispatcher is None or key != self._dispatcher_key:
            # PO_CLIQ_DRY_RUN=1 (testing): Cliq messages are logged, never sent
            self._dispatcher = make_dispatcher(hub, st, self.data_dir, self.ctx.user,
                                               dry_run_cliq=os.environ.get("PO_CLIQ_DRY_RUN") == "1")
            self._dispatcher_key = key
        return self._dispatcher

    def push_hub_events(self, published: list[dict] | None = None, tasks_assigned: list[M.Task] | None = None,
                        tasks_done: list[M.Task] | None = None, mentions: list[dict] | None = None) -> None:
        """Hub changes seen by ``app.hub``/``app.tasks``; consumed by the next tick's hub watchers."""
        self._pending.published += list(published or [])
        self._pending.tasks_assigned += list(tasks_assigned or [])
        self._pending.tasks_done += list(tasks_done or [])
        self._pending.mentions += list(mentions or [])

    def _toast(self, title: str, body: str, level: str) -> None:
        try:
            self.app.toast.emit(title, body, "error" if level == "critical" else level)
        except Exception:  # noqa: BLE001
            log.info("%s: %s", title, body)

    # ---------------------------------------------------------- lifecycle
    def start(self) -> None:
        # Interim seam (docs/V4-SEAMS.md, "Builder 1 asks"): until ui.context builds its Launcher with
        # ``profiles=store.profile``, launchers find profiles through the process-wide lookup.
        from project_opener.core import launcher as launcher_mod
        launcher_mod.set_profile_lookup(self.ctx.store.profile)
        self.ctx.store.subscribe(self._on_store)
        self._sync_watchers()
        self._load_alerts()
        self._timer = QTimer(self)
        self._timer.setInterval(C.WATCH_TICK_S * 1000)
        self._timer.timeout.connect(self.tick)
        self._timer.start()
        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(C.CLIQ_RETRY_S * 1000)
        self._retry_timer.timeout.connect(self._flush_cliq)
        self._retry_timer.start()
        self._roots_timer = QTimer(self)
        self._roots_timer.setSingleShot(True)
        self._roots_timer.setInterval(2000)
        self._roots_timer.timeout.connect(self._update_roots)
        self.ctx.health_updated.connect(lambda _pid: self._roots_timer.start())   # debounce a burst of results
        self.ctx.hub_changed.connect(lambda _s: self._roots_timer.start())
        self._roots_timer.start()

    def shutdown(self) -> None:
        for t in (self._timer, self._retry_timer, self._roots_timer):
            if t:
                t.stop()

    def _on_store(self, event: str, _payload: Any) -> None:
        if event in ("watchers_changed", "changed"):
            self._sync_watchers()

    # ------------------------------------------------------------- models
    def _sync_watchers(self) -> None:
        rows = []
        for w in self.ctx.store.watchers:
            rows.append({"watcherId": w.id, "name": w.name, "kind": w.kind, "target": w.target,
                         "events": list(w.events), "watcherEnabled": w.enabled, "notifyText": notify_text(w.notify),
                         "lastHitText": when_text(self._last_hit.get(w.id, "")), "activityId": w.activity_id,
                         "projectId": w.project_id})
        self._watchers.sync(rows)
        self.watchersChanged.emit()

    def _alert_row(self, r: dict[str, Any]) -> dict[str, Any]:
        return {"alertKey": str(r.get("key", "")), "ts": str(r.get("ts", "")), "tsText": when_text(str(r.get("ts", ""))),
                "title": str(r.get("title", "")), "detail": str(r.get("detail", "")),
                "level": str(r.get("level", "info")), "link": str(r.get("link", "")), "unread": not r.get("read"),
                "watcherId": str(r.get("watcher_id", ""))}

    def _load_alerts(self) -> None:
        disp = self.dispatcher()

        def done(rows: list[dict[str, Any]]) -> None:
            self._alert_raw = list(rows)
            for r in reversed(rows):
                wid, ts = str(r.get("watcher_id", "")), str(r.get("ts", ""))
                if ts > self._last_hit.get(wid, ""):
                    self._last_hit[wid] = ts
            self._alerts.sync([self._alert_row(r) for r in rows])
            self.alertsChanged.emit()
            self._sync_watchers()

        self.app.run_async(lambda: disp.alerts(200), done)

    # --------------------------------------------------------------- tick
    @Slot()
    def tick(self) -> None:
        """One engine pass on the pool (skipped while the previous one runs)."""
        if self._ticking:
            return
        watchers = [M.Watcher.from_dict(w.to_dict()) for w in self.ctx.store.watchers if w.enabled]
        if not watchers:
            self._pending = HubEvents()
            return
        self._ticking = True
        engine = self.engine()
        hub_events, self._pending = self._pending, HubEvents()
        me = self.ctx.user.lower()
        try:
            tasks = [t for t in self.app.tasks.latest() if t.owner.lower() == me]
        except Exception:  # noqa: BLE001
            tasks = []
        activities = [M.Activity.from_dict(a.to_dict()) for a in self.ctx.store.activities]
        roots = dict(self._local_roots) if self._local_roots else None
        by_id = {w.id: w for w in watchers}
        dispatcher = self.dispatcher()

        def work() -> list[tuple[M.WatchEvent, Any]]:
            events = engine.tick(watchers, datetime.now().astimezone(), hub_events, tasks, activities, roots)
            out = []
            for ev in events:
                w = by_id.get(ev.watcher_id)
                try:
                    out.append((ev, dispatcher.deliver(ev, w.notify if w else M.Notify())))
                except Exception:  # noqa: BLE001
                    log.exception("delivery failed for %s", ev.key)
            return out

        def done(results: list[tuple[M.WatchEvent, Any]]) -> None:
            self._ticking = False
            self._on_delivered(results, by_id)

        def fail(exc: Exception) -> None:
            self._ticking = False
            log.warning("watcher tick failed: %s", exc)

        self.app.run_async(work, done, fail)

    def _on_delivered(self, results: list[tuple[M.WatchEvent, Any]], by_id: dict[str, M.Watcher]) -> None:
        fresh = [(ev, d) for ev, d in results if d.new]
        if not fresh:
            return
        for ev, _d in fresh:
            self._insert_alert(ev)
            self._last_hit[ev.watcher_id] = ev.ts
            w = by_id.get(ev.watcher_id)
            if w is None or w.notify.toast:
                self.alert.emit(ev.title, ev.detail, ev.level, ev.link)
                self._toast(ev.title, ev.detail, ev.level)
        self.alertsChanged.emit()
        self._sync_watchers()

    def _insert_alert(self, ev: M.WatchEvent) -> None:
        rows = [self._alert_row({**ev.to_dict(), "read": False})]
        rows += [r for r in self._alerts.rows if r["alertKey"] != ev.key]
        self._alerts.sync(rows[:200])

    def _flush_cliq(self) -> None:
        disp = self.dispatcher()
        if disp.cliq is not None and disp.cliq.configured:
            self.app.run_async(disp.cliq.flush_outbox)

    # -------------------------------------------------------------- roots
    def _update_roots(self) -> None:
        """This PC's roots (from the 3.2 health results + activity items) -> watch/<me>.json -> merged rows."""
        if self._roots_busy:
            return
        self._roots_busy = True
        ctx = self.ctx
        projects = list(ctx.store.projects)
        health = dict(ctx.health)
        orphans = []
        for a in ctx.store.activities:
            loose = [i for i in a.items if not i.project_id]
            if loose:
                copy = M.Activity(a.name, id=a.id, items=loose)
                orphans.append(copy)
        resolver = ctx.resolver
        hub = ctx.hub
        user = ctx.user
        titles = {p.id: (p.job_number or p.title) for p in projects}
        titles.update({a.id: a.name for a in orphans})
        previous = dict(self._root_since)

        def work() -> tuple[list[H.RootHealth], list[OfficeRoot], dict[str, tuple[str, str]]]:
            for a in orphans:
                health[a.id] = H.check_activity(a, resolver)
            local = H.roots_health(projects + orphans, health, resolver.drive_map)
            current = {r.root: (r.status, H.jobs_for_root(r, titles), r.items) for r in local}
            observations, since = observe(previous, current)
            office: list[OfficeRoot] = []
            if hub.configured and hub.reachable():
                board = HealthBoard(hub.root, user)
                try:
                    board.write(M.HealthObservation(user=user, roots=observations))
                except OSError as exc:
                    log.info("watch/%s.json not written: %s", user, exc)
                office = board.merged()
            return local, office, since

        def done(res: tuple[list[H.RootHealth], list[OfficeRoot], dict[str, tuple[str, str]]]) -> None:
            self._roots_busy = False
            local, office, since = res
            self._root_since = since
            self._local_roots = {r.root: r.status for r in local}
            self._roots.sync(self._root_rows(local, office, since))
            self.rootsChanged.emit()

        def fail(exc: Exception) -> None:
            self._roots_busy = False
            log.warning("roots update failed: %s", exc)

        self.app.run_async(work, done, fail)

    def _uses_text(self, items: int, project_ids: list[str]) -> str:
        """"3 items · P12513, DM-GAD": what on this PC uses the root (V4-SEAMS, builder 4 ask 4)."""
        store = self.app.ctx.store
        jobs = []
        for pid in project_ids:
            p = store.get(pid)
            if p is not None:
                jobs.append(p.job_number or p.name)
        shown = ", ".join(jobs[:2]) + (f" +{len(jobs) - 2}" if len(jobs) > 2 else "")
        return T.join_facts(T.plural(items, "item") if items else "", shown)

    def _root_rows(self, local: list[H.RootHealth], office: list[OfficeRoot],
                   since: dict[str, tuple[str, str]]) -> list[dict[str, Any]]:
        by_root = {o.root.lower(): o for o in office}
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for r in local:
            o = by_root.get(r.root.lower())
            status, label = r.status, STATUS_LABELS.get(r.status, r.status)
            started = since.get(r.root, ("", ""))[1]
            seen_by, jobs = 1 if r.status != "ok" else 0, len(r.projects)
            if o is not None:
                seen_by, jobs = len(o.seen_by), max(jobs, len(o.jobs))
                if H.STATUS_RANK.get(o.status, 0) > H.STATUS_RANK.get(status, 0) or o.status != "ok":
                    status, started, label = o.status, o.since or started, o.text
            rows.append({"rootName": r.root, "status": status, "statusLabel": label, "mapping": r.mapping,
                         "uses": self._uses_text(r.items, r.projects), "seenBy": seen_by,
                         "since": started if status != "ok" else "",
                         "sinceText": since_text(status, started, seen_by) if status != "ok" else "",
                         "jobsAffected": jobs if status != "ok" else 0})
            seen.add(r.root.lower())
        for o in office:                       # roots others see that this PC does not use
            if o.root.lower() in seen or o.status == "ok":
                continue
            rows.append({"rootName": o.root, "status": o.status, "statusLabel": o.text, "mapping": "",
                         "uses": "", "seenBy": len(o.seen_by), "since": o.since,
                         "sinceText": since_text(o.status, o.since, len(o.seen_by)), "jobsAffected": len(o.jobs)})
        rows.sort(key=lambda x: (-H.STATUS_RANK.get(x["status"], 0), x["rootName"].lower()))
        return rows

    # -------------------------------------------------------------- slots
    @Slot(str, str, "QStringList", "QVariantMap", "QVariantMap", result=str)
    def create(self, kind: str, target: str, events: list[str], params: dict[str, Any],
               notify: dict[str, Any]) -> str:
        """notify: {toast, mentions, cliqDm, cliqChannel}; params may carry activityId/projectId."""
        p = dict(params or {})
        activity_id = str(p.pop("activityId", p.pop("activity_id", "")) or "")
        project_id = str(p.pop("projectId", p.pop("project_id", "")) or "")
        interval = p.pop("intervalS", p.pop("interval_s", 60))
        name = str(p.pop("name", "") or "") or self._default_name(kind, target)
        w = M.Watcher.from_dict({"name": name, "kind": kind, "target": target, "events": list(events or []),
                                 "interval_s": interval, "params": p, "notify": notify_from(notify).to_dict(),
                                 "activity_id": activity_id, "project_id": project_id, "enabled": True,
                                 "created_by": self.ctx.user})
        self.ctx.store.save_watcher(w)
        self._sync_watchers()
        return w.id

    @staticmethod
    def _default_name(kind: str, target: str) -> str:
        tail = target.rstrip("\\/").rsplit("\\", 1)[-1].rsplit("/", 1)[-1] if target else ""
        return {"folder": f"Watch {tail}" if tail else "Folder watcher", "health": f"{target or 'Drives'} health",
                "hub": "Hub events", "time": "Reminder"}.get(kind, "Watcher")

    @Slot(str, "QVariantMap")
    def edit(self, watcher_id: str, fields: dict[str, Any]) -> None:
        w = self.ctx.store.watcher(watcher_id)
        if w is None:
            return
        d = w.to_dict()
        f = dict(fields or {})
        reset = False
        for src, dst in (("name", "name"), ("target", "target"), ("events", "events"), ("params", "params"),
                         ("enabled", "enabled"), ("activityId", "activity_id"), ("projectId", "project_id"),
                         ("intervalS", "interval_s"), ("interval_s", "interval_s"), ("kind", "kind")):
            if src in f:
                if dst in ("target", "params", "kind") and f[src] != d.get(dst):
                    reset = True
                d[dst] = f[src]
        if "notify" in f:
            d["notify"] = notify_from(f["notify"]).to_dict()
        new = M.Watcher.from_dict(d)
        if reset:
            self.engine().forget(watcher_id)
        self.ctx.store.save_watcher(new)
        self._sync_watchers()

    @Slot(str)
    def remove(self, watcher_id: str) -> None:
        self.engine().forget(watcher_id)
        self.ctx.store.remove_watcher(watcher_id)
        self._sync_watchers()

    @Slot(str, bool)
    def setEnabled(self, watcher_id: str, on: bool) -> None:  # noqa: N802
        w = self.ctx.store.watcher(watcher_id)
        if w is None or w.enabled == bool(on):
            return
        w.enabled = bool(on)
        self.ctx.store.save_watcher(w)
        self._sync_watchers()

    @Slot(str)
    def markRead(self, alert_key: str) -> None:  # noqa: N802
        i = self._alerts.indexOf(alert_key)
        if i < 0 or not self._alerts.rows[i].get("unread"):
            return
        self._alerts.update(i, unread=False)
        self.alertsChanged.emit()
        disp = self.dispatcher()
        self.app.run_async(lambda: disp.mark_read(alert_key))

    def new_files(self, activity_id: str, is_item: Any = None) -> dict[str, Any]:
        """``new_files_fact`` over the loaded alerts (read flags as the model shows them)."""
        unread = {r["alertKey"] for r in self._alerts.rows if r.get("unread")}
        rows = [{**r, "read": str(r.get("key", "")) not in unread} for r in self._alert_raw]
        return new_files_fact(rows, list(self.ctx.store.watchers), activity_id, is_item)

    @Slot()
    def recheckRoots(self) -> None:  # noqa: N802
        self.ctx.resolver.refresh_drive_map()
        self.ctx.refresh_all_health()
        if self._roots_timer:
            self._roots_timer.start()
        else:
            self._update_roots()
