"""Persistent workspace store.

Responsibilities:

* load ``workspace.json`` (schema 4), migrating from 1.x / 2.x on first run
  and from schema 3 (3.x) on the first 4.0 start (``core.migrate``; a
  ``pre-v4-workspace-*.json`` copy is kept and never rotated away);
* projects, activities, launch profiles and watchers (schema 4 lists);
* atomic saves with rotating timestamped backups;
* a launch history log (``history.jsonl``) used by the dashboard;
* simple observer hooks so the UI can refresh after any mutation.

The store knows nothing about Qt or the network.
"""
from __future__ import annotations

import logging
import shutil
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from project_opener import constants as C
from project_opener.core import migrate
from project_opener.core import models as M
from project_opener.core.jsonio import append_jsonl, read_json, read_jsonl, write_json_atomic

log = logging.getLogger(__name__)

Listener = Callable[[str, Any], None]


class WorkspaceStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else C.data_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / C.WORKSPACE_FILE
        self.history_path = self.root / C.HISTORY_FILE
        self.projects: list[M.Project] = []
        self.activities: list[M.Activity] = []
        self.profiles: list[M.LaunchProfile] = []
        self.watchers: list[M.Watcher] = []
        self.migration: dict[str, Any] = {}
        self.migrated_from: str | None = None
        self._listeners: list[Listener] = []
        self.load()

    # ---------------------------------------------------------------- events
    def subscribe(self, fn: Listener) -> None:
        self._listeners.append(fn)

    def _emit(self, event: str, payload: Any = None) -> None:
        for fn in list(self._listeners):
            try:
                fn(event, payload)
            except Exception:  # pragma: no cover - listeners must not break saves
                log.exception("store listener failed")

    # ------------------------------------------------------------------ load
    def load(self) -> None:
        data = read_json(self.path)
        if isinstance(data, dict) and isinstance(data.get("projects"), list):
            self._apply(data, from_file=True)
            return
        if self.path.exists():
            # Corrupt file: keep it for forensics, start from the newest backup.
            broken = self.path.with_suffix(".corrupt.json")
            try:
                shutil.copy2(self.path, broken)
            except OSError:
                pass
            restored = self._restore_latest_backup()
            if restored:
                log.warning("workspace.json was unreadable; restored backup %s", restored.name)
                return
        self.projects = []
        self._migrate_legacy()

    def _apply(self, data: dict[str, Any], from_file: bool = False) -> None:
        """Take a raw workspace dict of any schema; migrate 3 -> 4 when needed."""
        try:
            schema = int(data.get("schema", 3) or 3)
        except (TypeError, ValueError):
            schema = 3
        ws = migrate.migrate_workspace(data)
        self.projects, self.activities = ws.projects, ws.activities
        self.profiles, self.watchers, self.migration = ws.profiles, ws.watchers, ws.migration
        if schema < migrate.TARGET_SCHEMA and from_file:
            self._keep_pre_v4_copy()
            self.migrated_from = f"Project Opener 3.x (schema {schema})"
            self.save(backup=False)
            log.info("Migrated workspace schema %s -> 4: %s", schema, ws.migration)

    def _keep_pre_v4_copy(self) -> None:
        bdir = self.root / C.BACKUP_DIR
        bdir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            shutil.copy2(self.path, bdir / f"{C.PRE_V4_BACKUP_PREFIX}{stamp}.json")
        except OSError as exc:
            log.warning("pre-v4 copy failed: %s", exc)

    def _restore_latest_backup(self) -> Path | None:
        backups = sorted((self.root / C.BACKUP_DIR).glob("workspace-*.json"))
        for b in reversed(backups):
            data = read_json(b)
            if isinstance(data, dict) and isinstance(data.get("projects"), list):
                self._apply(data)
                return b
        return None

    def _migrate_legacy(self) -> None:
        """Import 1.x and 2.x data when no v3 workspace exists yet."""
        imported = 0
        v1 = C.legacy_v1_dir() / "projects.json"
        v1_data = read_json(v1)
        if isinstance(v1_data, dict) and v1_data:
            auto = read_json(C.legacy_v1_dir() / "auto_launch.json", {}) or {}
            for name, pdata in v1_data.items():
                if isinstance(pdata, dict):
                    proj = M.project_from_v1(str(name), pdata)
                    proj.auto_launch = bool(auto.get(name, False))
                    self.projects.append(proj)
                    imported += 1
            if imported:
                self.migrated_from = "Project Opener 1.x"
        if imported:
            self.save(backup=False)
            log.info("Migrated %d projects from %s", imported, self.migrated_from)

    def import_v2_file(self, path: Path, author: str = "") -> int:
        """Import a 2.x per-user hub file (``<user>.json``). Returns count."""
        data = read_json(path)
        if not isinstance(data, dict):
            return 0
        projs = data.get("projects", {})
        if not isinstance(projs, dict):
            return 0
        count = 0
        for name, pdata in projs.items():
            if isinstance(pdata, dict):
                proj = M.project_from_v2(str(name), pdata, author=author)
                proj.name = M.dedupe_name(proj.name, self.names())
                self.projects.append(proj)
                count += 1
        if count:
            self.save()
            self._emit("imported", count)
        return count

    # ------------------------------------------------------------------ save
    def to_dict(self) -> dict[str, Any]:
        ws = M.Workspace(projects=self.projects, activities=self.activities, profiles=self.profiles,
                         watchers=self.watchers, migration=self.migration, schema=C.SCHEMA_VERSION)
        return ws.to_dict(app_version=C.VERSION)

    def save(self, backup: bool = True) -> None:
        if backup and self.path.exists():
            self._rotate_backup()
        write_json_atomic(self.path, self.to_dict())
        self._emit("saved")

    def _rotate_backup(self) -> None:
        bdir = self.root / C.BACKUP_DIR
        bdir.mkdir(exist_ok=True)
        # Windows' clock advances in ~15.6 ms ticks, so two saves in one tick get the same microseconds: a
        # counter makes every name unique and keeps names sorting in save order ("...-123456-00" < "-01").
        # The rotation glob below never matches the pre-v4 backup (pre-v4-workspace-*), which is kept.
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = next((bdir / f"workspace-{stamp}-{n:02d}.json" for n in range(100)
                       if not (bdir / f"workspace-{stamp}-{n:02d}.json").exists()), None)
        if target is not None:
            try:
                shutil.copy2(self.path, target)
            except OSError as exc:
                log.warning("backup failed: %s", exc)
        backups = sorted(bdir.glob("workspace-*.json"))
        for old in backups[:-C.MAX_BACKUPS]:
            try:
                old.unlink()
            except OSError:
                pass

    def backups(self) -> list[Path]:
        return sorted((self.root / C.BACKUP_DIR).glob("workspace-*.json"), reverse=True)

    def restore_backup(self, backup: Path) -> bool:
        data = read_json(backup)
        if not (isinstance(data, dict) and isinstance(data.get("projects"), list)):
            return False
        self._apply(data)
        self.save()
        self._emit("changed")
        return True

    # ---------------------------------------------------------------- query
    def names(self) -> list[str]:
        return [p.name for p in self.projects]

    def get(self, project_id: str) -> M.Project | None:
        return next((p for p in self.projects if p.id == project_id), None)

    def by_name(self, name: str) -> M.Project | None:
        low = name.strip().lower()
        return next((p for p in self.projects if p.name.lower() == low), None)

    def all_tags(self) -> list[str]:
        tags: dict[str, int] = {}
        for p in self.projects:
            for t in p.tags:
                tags[t] = tags.get(t, 0) + 1
        return [t for t, _ in sorted(tags.items(), key=lambda kv: (-kv[1], kv[0].lower()))]

    def sorted_projects(self, key: str = "smart") -> list[M.Project]:
        """smart = pinned first (by pin time), then by recency, then name."""
        def recency(p: M.Project) -> float:
            dt = M.parse_iso(p.last_opened)
            return dt.timestamp() if dt else 0.0

        if key == "name":
            return sorted(self.projects, key=lambda p: (not p.pinned, p.name.lower()))
        if key == "recent":
            return sorted(self.projects, key=lambda p: (not p.pinned, -recency(p), p.name.lower()))
        if key == "most_used":
            return sorted(self.projects, key=lambda p: (not p.pinned, -p.open_count, p.name.lower()))
        if key == "created":
            return sorted(self.projects, key=lambda p: (not p.pinned, p.created_at), reverse=False)
        pinned = sorted([p for p in self.projects if p.pinned], key=lambda p: p.pinned_at or "")
        rest = sorted([p for p in self.projects if not p.pinned], key=lambda p: (-recency(p), p.name.lower()))
        return pinned + rest

    def recent(self, limit: int = 6) -> list[M.Project]:
        opened = [p for p in self.projects if p.last_opened]
        opened.sort(key=lambda p: p.last_opened or "", reverse=True)
        return opened[:limit]

    def auto_launch_projects(self) -> list[M.Project]:
        return [p for p in self.projects if p.auto_launch and p.enabled_items]

    # --------------------------------------------------------------- mutate
    def add(self, project: M.Project) -> M.Project:
        project.name = M.dedupe_name(project.name.strip() or "Untitled", self.names())
        self.projects.append(project)
        self.save()
        self._emit("added", project)
        return project

    def update(self, project: M.Project) -> None:
        project.touch()
        for i, p in enumerate(self.projects):
            if p.id == project.id:
                self.projects[i] = project
                break
        else:
            self.projects.append(project)
        changed = self._sync_activity_items(project)
        self.save()
        self._emit("updated", project)
        for act in changed:
            self._emit("activity_updated", act)

    def _sync_activity_items(self, project: M.Project) -> list[M.Activity]:
        """Keep activity items drawn from ``project`` in step with its items (path, kind, label, args, profile)."""
        by_id = {i.id: i for i in project.items}
        changed: list[M.Activity] = []
        for act in self.activities:
            touched = False
            for it in act.items:
                if it.project_id != project.id or not it.source_item_id:
                    continue
                src = by_id.get(it.source_item_id)
                if src is None:
                    continue
                for attr in ("path", "kind", "label", "args", "profile_id"):
                    if getattr(it, attr) != getattr(src, attr):
                        setattr(it, attr, getattr(src, attr))
                        touched = True
            if touched:
                act.touch()
                changed.append(act)
        return changed

    def remove(self, project_id: str) -> M.Project | None:
        proj = self.get(project_id)
        if proj:
            self.projects = [p for p in self.projects if p.id != project_id]
            self.save()
            self._emit("removed", proj)
        return proj

    def toggle_pin(self, project_id: str) -> bool:
        proj = self.get(project_id)
        if not proj:
            return False
        proj.pinned_at = None if proj.pinned else M.now_iso()
        self.update(proj)
        return proj.pinned

    def toggle_favorite(self, project_id: str) -> bool:
        proj = self.get(project_id)
        if not proj:
            return False
        proj.favorite = not proj.favorite
        self.update(proj)
        return proj.favorite

    def duplicate(self, project_id: str) -> M.Project | None:
        proj = self.get(project_id)
        if not proj:
            return None
        return self.add(proj.clone())

    def reorder(self, ordered_ids: Iterable[str]) -> None:
        index = {pid: i for i, pid in enumerate(ordered_ids)}
        self.projects.sort(key=lambda p: index.get(p.id, len(index)))
        self.save()
        self._emit("changed")

    # ------------------------------------------------------------ activities
    # Events: "activity_added", "activity_updated", "activity_removed" (payload: Activity).
    def activity(self, activity_id: str) -> M.Activity | None:
        return next((a for a in self.activities if a.id == activity_id), None)

    def activity_by_name(self, name: str) -> M.Activity | None:
        low = name.strip().lower()
        return next((a for a in self.activities if a.name.lower() == low), None)

    def activities_for_project(self, project_id: str) -> list[M.Activity]:
        return [a for a in self.activities if project_id in a.project_ids
                or any(i.project_id == project_id for i in a.items)]

    def sorted_activities(self) -> list[M.Activity]:
        """Pinned first (by pin time), then most recently opened, then name."""
        def recency(a: M.Activity) -> float:
            dt = M.parse_iso(a.last_opened)
            return dt.timestamp() if dt else 0.0

        pinned = sorted([a for a in self.activities if a.pinned], key=lambda a: a.pinned_at or "")
        rest = sorted([a for a in self.activities if not a.pinned], key=lambda a: (-recency(a), a.name.lower()))
        return pinned + rest

    def add_activity(self, activity: M.Activity) -> M.Activity:
        activity.name = activity.name.strip() or "Untitled"
        self.activities.append(activity)
        self.save()
        self._emit("activity_added", activity)
        return activity

    def update_activity(self, activity: M.Activity) -> None:
        activity.touch()
        for i, a in enumerate(self.activities):
            if a.id == activity.id:
                self.activities[i] = activity
                break
        else:
            self.activities.append(activity)
        self.save()
        self._emit("activity_updated", activity)

    def remove_activity(self, activity_id: str) -> M.Activity | None:
        act = self.activity(activity_id)
        if act:
            self.activities = [a for a in self.activities if a.id != activity_id]
            self.save()
            self._emit("activity_removed", act)
        return act

    def record_activity_launch(self, activity: M.Activity, items: list[M.Item], ok: int = 0, missing: int = 0) -> None:
        activity.mark_opened()
        self.update_activity(activity)
        append_jsonl(self.history_path, {
            "ts": M.now_iso(), "activity_id": activity.id, "activity": activity.name,
            "project_id": activity.primary_project_id, "project": "", "set": "",
            "count": len(items), "ok": ok, "missing": missing,
        })
        self._emit("launched", activity)

    # -------------------------------------------------------- profiles, watchers
    def profile(self, profile_id: str) -> M.LaunchProfile | None:
        return next((p for p in self.profiles if p.id == profile_id), None)

    def save_profile(self, profile: M.LaunchProfile) -> None:
        profile.updated_at = M.now_iso()
        self.profiles = [p for p in self.profiles if p.id != profile.id] + [profile]
        self.save()
        self._emit("profiles_changed", profile)

    def remove_profile(self, profile_id: str) -> None:
        self.profiles = [p for p in self.profiles if p.id != profile_id]
        self.save()
        self._emit("profiles_changed", None)

    def watcher(self, watcher_id: str) -> M.Watcher | None:
        return next((w for w in self.watchers if w.id == watcher_id), None)

    def save_watcher(self, watcher: M.Watcher) -> None:
        for i, w in enumerate(self.watchers):
            if w.id == watcher.id:
                self.watchers[i] = watcher
                break
        else:
            self.watchers.append(watcher)
        self.save()
        self._emit("watchers_changed", watcher)

    def remove_watcher(self, watcher_id: str) -> None:
        self.watchers = [w for w in self.watchers if w.id != watcher_id]
        self.save()
        self._emit("watchers_changed", None)

    # -------------------------------------------------------------- history
    def record_launch(self, project: M.Project, items: list[M.Item], launch_set: str = "",
                      ok: int = 0, missing: int = 0) -> None:
        project.mark_opened()
        self.update(project)
        append_jsonl(self.history_path, {
            "ts": M.now_iso(), "project_id": project.id, "project": project.name,
            "set": launch_set, "count": len(items), "ok": ok, "missing": missing,
        })
        self._emit("launched", project)

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = read_jsonl(self.history_path, limit=limit)
        rows.reverse()
        return rows

    def stats(self) -> dict[str, Any]:
        rows = read_jsonl(self.history_path)
        today = datetime.now().date()  # local date; timestamps are stored in UTC

        def is_today(ts: Any) -> bool:
            dt = M.parse_iso(ts)
            return dt is not None and dt.astimezone().date() == today

        return {
            "projects": len(self.projects),
            "items": sum(len(p.items) for p in self.projects),
            "launch_sets": sum(len(p.launch_sets) for p in self.projects),
            "launches_total": len(rows),
            "launches_today": sum(1 for r in rows[-500:] if is_today(r.get("ts"))),
            "pinned": sum(1 for p in self.projects if p.pinned),
        }

    # ------------------------------------------------------------- transfer
    def export_bundle(self, project_ids: Iterable[str] | None = None,
                      activity_ids: Iterable[str] | None = None) -> dict[str, Any]:
        """Projects plus activities (and the launch profiles their items use).

        Without ``activity_ids``: every activity when all projects are exported, else
        the activities that draw on an exported project."""
        ids = set(project_ids) if project_ids is not None else None
        projs = [p for p in self.projects if ids is None or p.id in ids]
        if activity_ids is not None:
            want = set(activity_ids)
            acts = [a for a in self.activities if a.id in want]
        elif ids is None:
            acts = list(self.activities)
        else:
            acts = [a for a in self.activities if set(a.project_ids) & ids or any(i.project_id in ids for i in a.items)]
        used = {i.profile_id for p in projs for i in p.items if i.profile_id}
        used |= {i.profile_id for a in acts for i in a.items if i.profile_id}
        return {"schema": C.SCHEMA_VERSION, "exported_at": M.now_iso(), "app_version": C.VERSION,
                "projects": [p.to_dict() for p in projs],
                "activities": [a.to_dict() for a in acts],
                "profiles": [p.to_dict() for p in self.profiles if p.id in used]}

    def import_bundle(self, data: dict[str, Any], mode: str = "merge") -> tuple[int, int]:
        """Import a v4 or v3 bundle or a v1 backup. Returns (added, updated) projects.

        A schema-3 bundle runs the same 3 -> 4 rules as the workspace (its launch sets
        become activities); a schema-4 bundle brings its activities and profiles.
        Activities are matched by id (merge replaces, otherwise a fresh id)."""
        added = updated = 0
        if not isinstance(data, dict):
            return 0, 0
        if mode == "replace":
            self.projects = []
            self.activities = []
        imported: list[M.Project] = []
        id_map: dict[str, str] = {}
        projects = data.get("projects")
        if isinstance(projects, list):
            for raw in projects:
                if not isinstance(raw, dict):
                    continue
                proj = M.Project.from_dict(raw)
                original = proj.id
                existing = self.get(proj.id) or self.by_name(proj.name)
                if existing and mode == "merge":
                    proj.id = existing.id
                    self.projects = [p for p in self.projects if p.id != existing.id]
                    updated += 1
                else:
                    if self.get(proj.id):
                        proj.id = M.new_id()
                    proj.name = M.dedupe_name(proj.name, self.names())
                    added += 1
                id_map[original] = proj.id
                self.projects.append(proj)
                imported.append(proj)
        elif isinstance(projects, dict):  # v1 backup export
            auto = data.get("auto_launch", {}) if isinstance(data.get("auto_launch"), dict) else {}
            for name, pdata in projects.items():
                if not isinstance(pdata, dict):
                    continue
                proj = M.project_from_v1(str(name), pdata)
                proj.auto_launch = bool(auto.get(name, False))
                existing = self.by_name(proj.name)
                if existing and mode == "merge":
                    proj.id = existing.id
                    self.projects = [p for p in self.projects if p.id != existing.id]
                    updated += 1
                else:
                    proj.name = M.dedupe_name(proj.name, self.names())
                    added += 1
                self.projects.append(proj)
                imported.append(proj)
        try:
            schema = int(data.get("schema", 3) or 3)
        except (TypeError, ValueError):
            schema = 3
        if schema >= migrate.TARGET_SCHEMA:
            acts = [M.Activity.from_dict(a) for a in data.get("activities", []) or [] if isinstance(a, dict)]
            for prof in data.get("profiles", []) or []:
                if isinstance(prof, dict):
                    lp = M.LaunchProfile.from_dict(prof)
                    if not self.profile(lp.id):
                        self.profiles.append(lp)
        else:
            acts, _report = migrate.migrate_projects(
                imported, existing_ids=set() if mode == "merge" else {a.id for a in self.activities})
        for act in acts:
            act.project_ids = [id_map.get(pid, pid) for pid in act.project_ids]
            for it in act.items:
                if it.project_id:
                    it.project_id = id_map.get(it.project_id, it.project_id)
            if self.activity(act.id):
                if mode == "merge":
                    self.activities = [a for a in self.activities if a.id != act.id]
                else:
                    act.id = M.new_id()
            self.activities.append(act)
        self.save()
        self._emit("changed")
        return added, updated
