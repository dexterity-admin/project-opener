"""The watcher engine (brief section 3.4).  Owner: builder 1 (CORE+HUB).

Pure Python, no Qt: ``tick(now)`` is called on a pool thread every
``WATCH_TICK_S`` by ``quick.watchers_api``; it returns the new ``WatchEvent``s.

* folder: list the folder (``os.scandir``, optional glob, optional recursion) when its
  ``interval_s`` has passed; diff against ``watch-state/<id>.json`` (name -> size, mtime):
  new / changed / gone.  The first listing only records state (no flood of "new").
  Polling, never ReadDirectoryChangesW (unreliable over SMB).  A folder that cannot
  be listed (share down, path gone) produces no events and keeps its last state:
  "server down" is the health watcher's job, never a flood of "gone".
* health: compare this PC's root health (``core.health.roots_health``) with the last tick:
  down / up.  The hub side (``watch/<user>.json``) is written by ``lan.healthboard``.
* hub: given the hub's latest events (``HubEvents``), match published / task_assigned /
  task_done / mention against the watcher's target.
* time: due dates of my tasks (the day it is due, and once when overdue), "activity not
  opened for ``stale_days``", reminders at ``at`` / every ``every_days``.

Every event carries a stable ``key`` (no timestamp of the tick in it), so the
delivery ledger can drop repeats across ticks, restarts and the user's other PCs.
"""
from __future__ import annotations

import fnmatch
import hashlib
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from project_opener import constants as C
from project_opener.core import models as M
from project_opener.core.jsonio import read_json, write_json_atomic
from project_opener.core.pathvars import PathResolver
from project_opener.core.tasks import local_date, parse_due

log = logging.getLogger(__name__)

COLLAPSE_OVER = 5          # more hits than this of one kind in one listing -> one summary event
MAX_FILES = 20000          # a listing stops here (a watcher on a whole share is a mistake, not a DoS)
DOWN = ("offline", "missing")


@dataclass
class HubEvents:
    """What changed on the hub since the last tick (filled by ``quick.hub_api``/``lan.hub``)."""
    published: list[dict] = field(default_factory=list)      # {published_id, type, title, author, revision}
    tasks_assigned: list[M.Task] = field(default_factory=list)
    tasks_done: list[M.Task] = field(default_factory=list)
    mentions: list[dict] = field(default_factory=list)       # {id, from, text, link}

    def __bool__(self) -> bool:
        return bool(self.published or self.tasks_assigned or self.tasks_done or self.mentions)


@dataclass
class FolderState:
    files: dict[str, tuple[int, float]] = field(default_factory=dict)   # relative name -> (size, mtime)
    listed_at: str = ""


def _aware(now: datetime) -> datetime:
    return now.astimezone() if now.tzinfo else now.astimezone()


def _short(names: list[str], n: int = 5) -> str:
    head = ", ".join(names[:n])
    return head + (f" and {len(names) - n} more" if len(names) > n else "")


def _digest(names: list[str]) -> str:
    return hashlib.sha1("\n".join(sorted(names)).encode("utf-8")).hexdigest()[:12]


def watcher_link(w: M.Watcher) -> str:
    if w.activity_id:
        return f"{C.URI_SCHEME}://activity/{w.activity_id}"
    if w.project_id:
        return f"{C.URI_SCHEME}://open/{w.project_id}"
    return ""


class WatcherEngine:
    def __init__(self, state_dir: Path, resolver: PathResolver):
        self.state_dir = Path(state_dir)
        self.resolver = resolver
        self._last_run: dict[str, datetime] = {}
        self._health_prev: dict[str, dict[str, str]] = {}    # watcher id -> root -> status
        self._lock = threading.Lock()                        # one tick at a time

    # --------------------------------------------------------------- tick
    def tick(self, watchers: list[M.Watcher], now: datetime, hub: HubEvents | None = None,
             tasks: list[M.Task] | None = None, activities: list[M.Activity] | None = None,
             roots: dict[str, str] | None = None) -> list[M.WatchEvent]:
        """Run every due, enabled watcher once; never raises (a failing watcher logs and is skipped)."""
        now = _aware(now)
        out: list[M.WatchEvent] = []
        with self._lock:
            for w in watchers:
                if not w.enabled:
                    continue
                try:
                    if w.kind == "folder":
                        last = self._last_run.get(w.id)
                        if last is not None and (now - last).total_seconds() < max(10, w.interval_s) - 1:
                            continue
                        self._last_run[w.id] = now
                        out += self.poll_folder(w, now)
                    elif w.kind == "health":
                        if roots is not None:
                            out += self.check_health(w, roots, now)
                    elif w.kind == "hub":
                        if hub:
                            out += self.match_hub(w, hub)
                    elif w.kind == "time":
                        out += self.check_time(w, now, tasks or [], activities or [])
                except Exception:  # noqa: BLE001 - one bad watcher never stops the others
                    log.exception("watcher %s (%s) failed", w.name, w.kind)
        return out

    # ------------------------------------------------------------- folder
    def list_folder(self, folder: str, pattern: str = "*", recursive: bool = False) -> FolderState | None:
        """The listing, or None when the folder cannot be read (absent, share down, no access)."""
        if not folder or not os.path.isdir(folder):
            return None
        files: dict[str, tuple[int, float]] = {}
        pats = [p.strip().lower() for p in (pattern or "*").split(";") if p.strip()] or ["*"]
        stack = [("", folder)]
        try:
            while stack and len(files) < MAX_FILES:
                rel_dir, abs_dir = stack.pop()
                with os.scandir(abs_dir) as it:
                    for e in it:
                        rel = f"{rel_dir}{os.sep}{e.name}" if rel_dir else e.name
                        try:
                            if e.is_dir(follow_symlinks=False):
                                if recursive:
                                    stack.append((rel, e.path))
                                continue
                            if not any(fnmatch.fnmatch(e.name.lower(), p) for p in pats):
                                continue
                            st = e.stat()
                            files[rel] = (int(st.st_size), round(float(st.st_mtime), 3))
                        except OSError:
                            continue
        except OSError as exc:
            log.info("cannot list %s: %s", folder, exc)
            return None
        return FolderState(files, M.now_iso())

    def poll_folder(self, watcher: M.Watcher, now: datetime) -> list[M.WatchEvent]:
        res = self.resolver.resolve(watcher.target)
        if res.unresolved:
            return []
        folder = res.resolved
        new_state = self.list_folder(folder, str(watcher.params.get("pattern") or "*"),
                                     bool(watcher.params.get("recursive", False)))
        if new_state is None:
            return []
        path = self._state_path(watcher.id)
        first = not path.exists()
        old = self.load_state(watcher.id)
        self.save_state(watcher.id, new_state)
        if first:
            return []
        new, changed, gone = diff_listing(old, new_state)
        name = os.path.basename(folder.rstrip("\\/")) or folder
        link = watcher_link(watcher)
        events: list[M.WatchEvent] = []
        for kind, names, verb in (("new", new, "New"), ("changed", changed, "Changed"), ("gone", gone, "Gone")):
            if kind not in watcher.events or not names:
                continue
            src = old.files if kind == "gone" else new_state.files
            if len(names) > COLLAPSE_OVER:
                events.append(M.WatchEvent(
                    watcher.id, kind, f"{len(names)} {verb.lower()} files in {name}", _short(names),
                    folder, link, "warning" if kind == "gone" else "info",
                    key=f"{watcher.id}:{kind}:*:{_digest([f'{n}|{src[n]}' for n in names])}"))
                continue
            for n in names:
                size, mtime = src.get(n, (0, 0.0))
                events.append(M.WatchEvent(
                    watcher.id, kind, f"{verb} in {name}: {os.path.basename(n)}", n, os.path.join(folder, n),
                    link, "warning" if kind == "gone" else "info",
                    key=f"{watcher.id}:{kind}:{n.lower()}:{size}:{mtime}"))
        return events

    def _state_path(self, watcher_id: str) -> Path:
        safe = "".join(ch for ch in watcher_id if ch.isalnum() or ch in "-_") or "watcher"
        return self.state_dir / f"{safe}.json"

    def load_state(self, watcher_id: str) -> FolderState:
        d = read_json(self._state_path(watcher_id), {}) or {}
        files: dict[str, tuple[int, float]] = {}
        raw = d.get("files", {}) if isinstance(d, dict) else {}
        if isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(v, (list, tuple)) and len(v) == 2:
                    try:
                        files[str(k)] = (int(v[0]), float(v[1]))
                    except (TypeError, ValueError):
                        continue
        return FolderState(files, str(d.get("listed_at", "")) if isinstance(d, dict) else "")

    def save_state(self, watcher_id: str, state: FolderState) -> None:
        write_json_atomic(self._state_path(watcher_id),
                          {"files": {k: [v[0], v[1]] for k, v in state.files.items()}, "listed_at": state.listed_at},
                          indent=0)

    def forget(self, watcher_id: str) -> None:
        """Drop a watcher's state (edited target or removed watcher)."""
        self._last_run.pop(watcher_id, None)
        self._health_prev.pop(watcher_id, None)
        try:
            self._state_path(watcher_id).unlink()
        except OSError:
            pass

    # ------------------------------------------------------------- health
    def check_health(self, watcher: M.Watcher, roots: dict[str, str], now: datetime) -> list[M.WatchEvent]:
        """``roots``: this PC's root -> status (ok | missing | offline | variable).  First call records only."""
        want = watcher.target.strip().lower()
        current = {r: s for r, s in roots.items() if not want or r.lower() == want}
        prev = self._health_prev.get(watcher.id)
        self._health_prev[watcher.id] = dict(current)
        if prev is None:
            return []
        stamp = now.isoformat(timespec="minutes")
        out = []
        for root, status in current.items():
            before = prev.get(root)
            if before is None:
                continue
            if status in DOWN and before not in DOWN and "down" in watcher.events:
                out.append(M.WatchEvent(watcher.id, "down", f"{root} is {status}",
                                        f"{root} stopped answering on this PC", root, watcher_link(watcher),
                                        "critical", key=f"{watcher.id}:down:{root.lower()}:{stamp}"))
            elif status == "ok" and before in DOWN and "up" in watcher.events:
                out.append(M.WatchEvent(watcher.id, "up", f"{root} is back", f"{root} answers again", root,
                                        watcher_link(watcher), "info", key=f"{watcher.id}:up:{root.lower()}:{stamp}"))
        return out

    # ---------------------------------------------------------------- hub
    def match_hub(self, watcher: M.Watcher, hub: HubEvents) -> list[M.WatchEvent]:
        t = watcher.target.strip().lower()
        out: list[M.WatchEvent] = []

        def hit(*values: str) -> bool:
            return not t or any(t == (v or "").lower() or (len(t) > 2 and t in (v or "").lower()) for v in values)

        if "published" in watcher.events:
            for p in hub.published:
                pid, title = str(p.get("published_id", "")), str(p.get("title", ""))
                if hit(pid, title, str(p.get("author", ""))):
                    rev = p.get("revision", 1)
                    out.append(M.WatchEvent(watcher.id, "published", f"{title} rev {rev} published",
                                            f"by {p.get('author_name') or p.get('author', '')}", "",
                                            str(p.get("link", "")), "info",
                                            key=f"{watcher.id}:published:{pid}:{rev}"))
        if "task_assigned" in watcher.events:
            for task in hub.tasks_assigned:
                if hit(task.id, task.owner, task.title, task.link.title if task.link else ""):
                    out.append(M.WatchEvent(watcher.id, "task_assigned", f"Task for {task.owner}: {task.title}",
                                            f"from {task.created_by}", "", f"{C.URI_SCHEME}://task/{task.id}", "info",
                                            key=f"{watcher.id}:task_assigned:{task.id}:{task.owner}"))
        if "task_done" in watcher.events:
            for task in hub.tasks_done:
                if hit(task.id, task.owner, task.title, task.done_by, task.link.title if task.link else ""):
                    out.append(M.WatchEvent(watcher.id, "task_done", f"{task.done_by or task.owner} finished {task.title}",
                                            "", "", f"{C.URI_SCHEME}://task/{task.id}", "info",
                                            key=f"{watcher.id}:task_done:{task.id}:{task.done_at}"))
        if "mention" in watcher.events:
            for m in hub.mentions:
                if hit(str(m.get("from", "")), str(m.get("text", ""))):
                    out.append(M.WatchEvent(watcher.id, "mention", f"{m.get('from_name') or m.get('from', '')} mentioned you",
                                            str(m.get("text", "")), "", str(m.get("link", "")), "info",
                                            key=f"{watcher.id}:mention:{m.get('id', '')}"))
        return out

    # --------------------------------------------------------------- time
    def check_time(self, watcher: M.Watcher, now: datetime, tasks: list[M.Task],
                   activities: list[M.Activity]) -> list[M.WatchEvent]:
        out: list[M.WatchEvent] = []
        today = local_date(now)
        p = watcher.params
        if "due" in watcher.events:
            only = str(p.get("task_id") or "")
            for task in tasks:
                if task.done or (only and task.id != only):
                    continue
                d = parse_due(task.due)
                if d is None or d > today:
                    continue
                link = f"{C.URI_SCHEME}://task/{task.id}"
                if d == today:
                    out.append(M.WatchEvent(watcher.id, "due", f"Due today: {task.title}", task.owner, "", link,
                                            "warning", key=f"{watcher.id}:due:{task.id}:{task.due}"))
                else:
                    out.append(M.WatchEvent(watcher.id, "due", f"Overdue: {task.title}",
                                            f"was due {task.due}", "", link, "warning",
                                            key=f"{watcher.id}:overdue:{task.id}:{task.due}"))
        if "stale" in watcher.events:
            try:
                days = int(p.get("stale_days") or 30)
            except (TypeError, ValueError):
                days = 30
            for act in activities:
                if watcher.activity_id and act.id != watcher.activity_id:
                    continue
                seen = M.parse_iso(act.last_opened) or M.parse_iso(act.created_at)
                if seen is None or (now - seen) < timedelta(days=days):
                    continue
                out.append(M.WatchEvent(watcher.id, "stale", f"{act.name} not opened for {(now - seen).days} days",
                                        "", "", f"{C.URI_SCHEME}://activity/{act.id}", "info",
                                        key=f"{watcher.id}:stale:{act.id}:{act.last_opened or act.created_at}"))
        if "reminder" in watcher.events:
            try:
                at: datetime | None = datetime.fromisoformat(str(p.get("at") or "").replace("Z", "+00:00"))
            except ValueError:
                at = None
            if at is not None and at.tzinfo is None:
                at = at.astimezone()            # a naive "at" is local time
            if at is not None and now >= at:
                try:
                    every = float(p.get("every_days") or 0)
                except (TypeError, ValueError):
                    every = 0
                occurrence = at
                if every > 0:
                    n = int((now - at) / timedelta(days=every))
                    occurrence = at + n * timedelta(days=every)
                out.append(M.WatchEvent(watcher.id, "reminder", watcher.name, str(p.get("text", "")), "",
                                        watcher_link(watcher), "info",
                                        key=f"{watcher.id}:reminder:{occurrence.isoformat(timespec='minutes')}"))
        return out


def diff_listing(old: FolderState, new: FolderState) -> tuple[list[str], list[str], list[str]]:
    """(new, changed, gone) relative names.  Pure."""
    added = sorted(n for n in new.files if n not in old.files)
    gone = sorted(n for n in old.files if n not in new.files)
    changed = sorted(n for n in new.files if n in old.files and tuple(new.files[n]) != tuple(old.files[n]))
    return added, changed, gone
