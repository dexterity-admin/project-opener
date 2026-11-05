"""Restorer: reopen a snapshot in order and put windows back.  Owner: builder 2.

Runs on the capture thread (COM).  Order: the activity's launch order
(``diff.order_for_restore``).  Opening: Office files through COM, folders through
``explorer.exe <path>``, URLs through the recorded browser with ``--new-window``,
everything else through ``core.launcher`` (variables, profiles).  Then, for up to
``RESTORE_SETTLE_S``, identify every *new* top-level window the way capture does,
match by identity (path/URL) first and process + title similarity (0.55) only for
title-identified apps, and place each as soon as it matches.

Never moves, closes or terminates a window it did not just open.  Unsaved and
unidentified entries are reported, not restored.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from project_opener.core import models as M


@dataclass
class RestoreResult:
    key: str
    label: str
    opened: bool = False
    placed: bool = False
    matched_by: str = ""             # identity | title | ""
    message: str = ""


@dataclass
class RestoreReport:
    results: list[RestoreResult] = field(default_factory=list)
    unrestorable: list[M.SnapshotEntry] = field(default_factory=list)   # unsaved / unidentified, listed
    seconds: float = 0.0

    def to_dict(self) -> dict:
        return {"opened": sum(r.opened for r in self.results), "placed": sum(r.placed for r in self.results),
                "failed": [r.label for r in self.results if not r.opened],
                "unrestorable": [e.title for e in self.unrestorable], "seconds": round(self.seconds, 1)}


class Restorer:
    def __init__(self, open_item: Callable[[M.Item], object], settle_s: float = 25.0):
        """``open_item`` is the launcher's open for non-Office items (variables, profiles honoured)."""
        self.open_item = open_item
        self.settle_s = settle_s

    def restore(self, snapshot: M.Snapshot, items: list[M.Item],
                progress: Callable[[int, int, str], None] | None = None) -> RestoreReport:
        raise NotImplementedError("Restorer.restore")
