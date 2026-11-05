"""Pure snapshot arithmetic (no Win32, fully unit-testable).  Owner: builder 2.

* ``match_items``: set ``entry.item_id`` for entries whose path equals an activity item's
  resolved path (case-insensitive, trailing separators ignored, drive letter vs UNC through
  the resolver's ``portable`` form).
* ``changed``: whether a new pass differs from the last written snapshot in a way worth
  writing (identified set, statuses or a placement), so the live file is rewritten only on change.
* ``new_since``: entries identified now that were not in the checkpoint ("2 new since").
* ``order_for_restore``: restorable entries in the activity's launch order, unknown ones last.
"""
from __future__ import annotations

from collections.abc import Callable

from project_opener.core import models as M


def norm_path(path: str) -> str:
    return (path or "").strip().rstrip("\\/").lower()


def match_items(snapshot: M.Snapshot, items: list[M.Item],
                portable: Callable[[str], str] | None = None) -> M.Snapshot:
    raise NotImplementedError("diff.match_items")


def changed(old: M.Snapshot | None, new: M.Snapshot) -> bool:
    raise NotImplementedError("diff.changed")


def new_since(checkpoint: M.Snapshot | None, now: M.Snapshot) -> list[M.SnapshotEntry]:
    raise NotImplementedError("diff.new_since")


def order_for_restore(snapshot: M.Snapshot, items: list[M.Item]) -> list[M.SnapshotEntry]:
    raise NotImplementedError("diff.order_for_restore")
