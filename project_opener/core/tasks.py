"""Tasks as one JSON file each (``<root>/<id>.json``).  Owner: builder 1 (CORE+HUB).

``root`` is the hub's ``tasks/`` folder, or ``data_dir()/tasks`` when no hub is
set (same format; nothing to migrate when a hub is added later except moving
files, which ``adopt_local`` does).  Anyone may write any task (everyone equal);
``updated_by``/``updated_at`` and the pulse record who.  Last writer wins.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path

from project_opener.core import models as M
from project_opener.core.jsonio import read_json, write_json_atomic

log = logging.getLogger(__name__)

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def parse_due(due: str) -> date | None:
    """``YYYY-MM-DD`` -> date; anything else -> None."""
    try:
        return date.fromisoformat((due or "").strip()[:10])
    except ValueError:
        return None


class TaskStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, task_id: str) -> Path | None:
        # Ids come from other PCs' files; never let one name a path outside the folder.
        return self.root / f"{task_id}.json" if SAFE_ID_RE.match(task_id or "") else None

    def all(self) -> list[M.Task]:
        """Every readable task; corrupt files skipped (logged)."""
        out: list[M.Task] = []
        try:
            files = sorted(self.root.glob("*.json"))
        except OSError as exc:
            log.debug("task listing failed: %s", exc)
            return out
        for f in files:
            d = read_json(f, None)
            if not isinstance(d, dict) or not d.get("title"):
                if d is not None:
                    log.warning("skipping unreadable task file %s", f)
                continue
            t = M.Task.from_dict(d)
            if not d.get("id"):
                t.id = f.stem
            out.append(t)
        return out

    def get(self, task_id: str) -> M.Task | None:
        p = self._path(task_id)
        if p is None:
            return None
        d = read_json(p, None)
        return M.Task.from_dict(d) if isinstance(d, dict) else None

    def save(self, task: M.Task) -> None:
        """Atomic write of ``<id>.json``."""
        p = self._path(task.id)
        if p is None:
            raise ValueError(f"bad task id {task.id!r}")
        write_json_atomic(p, task.to_dict())

    def remove(self, task_id: str) -> bool:
        p = self._path(task_id)
        if p is None:
            return False
        try:
            p.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as exc:
            log.warning("task remove failed: %s", exc)
            return False

    def for_owner(self, login: str, include_done: bool = False) -> list[M.Task]:
        """Due soonest first; no due date last; then created order."""
        low = (login or "").lower()
        tasks = [t for t in self.all() if t.owner.lower() == low and (include_done or not t.done)]
        return sort_by_due(tasks)

    def for_link(self, kind: str, local_id: str = "", published_id: str = "") -> list[M.Task]:
        out = []
        for t in self.all():
            if not t.link or t.link.kind != kind:
                continue
            if (local_id and t.link.local_id == local_id) or (published_id and t.link.published_id == published_id):
                out.append(t)
        return sort_by_due(out)

    def adopt_local(self, local_root: Path) -> int:
        """Move tasks from the local fallback folder into this (hub) store; returns the count."""
        local_root = Path(local_root)
        try:
            if local_root.resolve() == self.root.resolve():
                return 0
        except OSError:
            return 0
        count = 0
        try:
            files = list(local_root.glob("*.json"))
        except OSError:
            return 0
        for f in files:
            d = read_json(f, None)
            if not isinstance(d, dict) or not d.get("title"):
                continue
            task = M.Task.from_dict(d)
            target = self._path(task.id)
            if target is None:
                continue
            try:
                if not target.exists():
                    self.save(task)
                f.unlink()
                count += 1
            except OSError as exc:
                log.warning("could not move task %s to the hub: %s", f, exc)
        return count


def sort_by_due(tasks: list[M.Task]) -> list[M.Task]:
    def key(t: M.Task) -> tuple[int, str, str]:
        d = parse_due(t.due)
        return (0 if d else 1, d.isoformat() if d else "", t.created_at)
    return sorted(tasks, key=key)


def due_text(due: str, today: date | None = None) -> str:
    """"due today", "due Fri", "due 14 Nov", "2 days overdue"; "" when no due date."""
    d = parse_due(due)
    if d is None:
        return ""
    today = today or date.today()
    delta = (d - today).days
    if delta == 0:
        return "due today"
    if delta == 1:
        return "due tomorrow"
    if delta == -1:
        return "1 day overdue"
    if delta < 0:
        return f"{-delta} days overdue"
    if delta < 7:
        return f"due {d.strftime('%a')}"
    if d.year == today.year:
        return f"due {d.day} {d.strftime('%b')}"
    return f"due {d.day} {d.strftime('%b')} {d.year}"


def is_overdue(task: M.Task, today: date | None = None) -> bool:
    d = parse_due(task.due)
    return bool(d and not task.done and d < (today or date.today()))


def local_date(now: datetime | None = None) -> date:
    """Today's local date (``now`` may be naive local or aware)."""
    if now is None:
        return date.today()
    return now.astimezone().date() if now.tzinfo else now.date()


def when_text(iso: str, now: datetime | None = None) -> str:
    """Short local time for lists: "just now", "5 min ago", "14:32", "yesterday 09:10", "Mon", "14 Nov"."""
    dt = M.parse_iso(iso)
    if dt is None:
        return ""
    now = (now or datetime.now().astimezone()).astimezone()
    local = dt.astimezone()
    secs = (now - local).total_seconds()
    if 0 <= secs < 60:
        return "just now"
    if 0 <= secs < 3600:
        return f"{int(secs // 60)} min ago"
    days = (now.date() - local.date()).days
    if days == 0:
        return local.strftime("%H:%M")
    if days == 1:
        return "yesterday " + local.strftime("%H:%M")
    if 1 < days < 7:
        return local.strftime("%a")
    if local.year == now.year:
        return f"{local.day} {local.strftime('%b')}"
    return f"{local.day} {local.strftime('%b')} {local.year}"
