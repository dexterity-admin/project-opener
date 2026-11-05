"""The watcher engine (brief section 3.4).  Owner: builder 1 (CORE+HUB).

Pure Python, no Qt: ``tick(now)`` is called on a pool thread every
``WATCH_TICK_S`` by ``quick.watchers_api``; it returns the new ``WatchEvent``s.

* folder: list the folder (``os.scandir``, optional glob, optional recursion) when its
  ``interval_s`` has passed; diff against ``watch-state/<id>.json`` (name -> size, mtime):
  new / changed / gone.  The first listing only records state (no flood of "new").
  Polling, never ReadDirectoryChangesW (unreliable over SMB).
* health: compare this PC's root health (``core.health.roots_health``) with the last tick:
  down / up.  The hub side (``watch/<user>.json``) is written by ``lan.healthboard``.
* hub: given the hub's latest events (``HubEvents``), match published / task_assigned /
  task_done / mention against the watcher's target.
* time: due dates of my tasks (the morning of, and when overdue), "activity not opened for
  ``stale_days``", reminders at ``at`` / every ``every_days``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from project_opener.core import models as M
from project_opener.core.pathvars import PathResolver


@dataclass
class HubEvents:
    """What changed on the hub since the last tick (filled by ``quick.hub_api``/``lan.hub``)."""
    published: list[dict] = field(default_factory=list)      # {published_id, type, title, author, revision}
    tasks_assigned: list[M.Task] = field(default_factory=list)
    tasks_done: list[M.Task] = field(default_factory=list)
    mentions: list[dict] = field(default_factory=list)       # {from, text, link}


@dataclass
class FolderState:
    files: dict[str, tuple[int, float]] = field(default_factory=dict)   # relative name -> (size, mtime)
    listed_at: str = ""


class WatcherEngine:
    def __init__(self, state_dir: Path, resolver: PathResolver):
        self.state_dir = Path(state_dir)
        self.resolver = resolver

    def tick(self, watchers: list[M.Watcher], now: datetime, hub: HubEvents | None = None,
             tasks: list[M.Task] | None = None, activities: list[M.Activity] | None = None,
             roots: dict[str, str] | None = None) -> list[M.WatchEvent]:
        """Run every due, enabled watcher once; never raises (a failing watcher logs and is skipped)."""
        raise NotImplementedError("WatcherEngine.tick")

    def poll_folder(self, watcher: M.Watcher, now: datetime) -> list[M.WatchEvent]:
        raise NotImplementedError("WatcherEngine.poll_folder")

    def load_state(self, watcher_id: str) -> FolderState:
        raise NotImplementedError("WatcherEngine.load_state")

    def save_state(self, watcher_id: str, state: FolderState) -> None:
        raise NotImplementedError("WatcherEngine.save_state")


def diff_listing(old: FolderState, new: FolderState) -> tuple[list[str], list[str], list[str]]:
    """(new, changed, gone) relative names.  Pure."""
    raise NotImplementedError("diff_listing")
