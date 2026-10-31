"""Persistent workspace store.

Responsibilities:

* load ``workspace.json`` (schema 3), migrating from 1.x / 2.x on first run;
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
            self.projects = [M.Project.from_dict(p) for p in data["projects"] if isinstance(p, dict)]
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

    def _restore_latest_backup(self) -> Path | None:
        backups = sorted((self.root / C.BACKUP_DIR).glob("workspace-*.json"))
        for b in reversed(backups):
            data = read_json(b)
            if isinstance(data, dict) and isinstance(data.get("projects"), list):
                self.projects = [M.Project.from_dict(p) for p in data["projects"] if isinstance(p, dict)]
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
        return {
            "schema": C.SCHEMA_VERSION,
            "app_version": C.VERSION,
            "saved_at": M.now_iso(),
            "projects": [p.to_dict() for p in self.projects],
        }

    def save(self, backup: bool = True) -> None:
        if backup and self.path.exists():
            self._rotate_backup()
        write_json_atomic(self.path, self.to_dict())
        self._emit("saved")

    def _rotate_backup(self) -> None:
        bdir = self.root / C.BACKUP_DIR
        bdir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = bdir / f"workspace-{stamp}.json"
        if not target.exists():
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
        self.projects = [M.Project.from_dict(p) for p in data["projects"] if isinstance(p, dict)]
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
        self.save()
        self._emit("updated", project)

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
        today = datetime.now().date().isoformat()
        week_rows = rows[-500:]
        return {
            "projects": len(self.projects),
            "items": sum(len(p.items) for p in self.projects),
            "launch_sets": sum(len(p.launch_sets) for p in self.projects),
            "launches_total": len(rows),
            "launches_today": sum(1 for r in week_rows if str(r.get("ts", "")).startswith(today)),
            "pinned": sum(1 for p in self.projects if p.pinned),
        }

    # ------------------------------------------------------------- transfer
    def export_bundle(self, project_ids: Iterable[str] | None = None) -> dict[str, Any]:
        ids = set(project_ids) if project_ids is not None else None
        projs = [p for p in self.projects if ids is None or p.id in ids]
        return {"schema": C.SCHEMA_VERSION, "exported_at": M.now_iso(), "app_version": C.VERSION,
                "projects": [p.to_dict() for p in projs]}

    def import_bundle(self, data: dict[str, Any], mode: str = "merge") -> tuple[int, int]:
        """Import a v3 bundle or a v1 backup. Returns (added, updated)."""
        added = updated = 0
        if not isinstance(data, dict):
            return 0, 0
        if mode == "replace":
            self.projects = []
        projects = data.get("projects")
        if isinstance(projects, list):
            for raw in projects:
                if not isinstance(raw, dict):
                    continue
                proj = M.Project.from_dict(raw)
                existing = self.get(proj.id) or self.by_name(proj.name)
                if existing and mode == "merge":
                    proj.id = existing.id
                    self.projects = [p for p in self.projects if p.id != existing.id]
                    updated += 1
                else:
                    proj.name = M.dedupe_name(proj.name, self.names())
                    added += 1
                self.projects.append(proj)
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
        self.save()
        self._emit("changed")
        return added, updated
