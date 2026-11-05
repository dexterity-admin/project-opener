"""Helpers for "add this window" and "start from what's open".  Owner: builder 2.

Pure decisions over ``SnapshotEntry`` lists (testable without Win32).
"""
from __future__ import annotations

from project_opener.core import models as M

# Applications whose windows are not activity items by default (chat, mail): unticked in
# "start from what's open".  Decision data, not a guess about the user's intent.
NON_FILE_PROCESSES = frozenset({"outlook.exe", "ms-teams.exe", "teams.exe", "cliq.exe", "zoho cliq.exe",
                                "slack.exe", "whatsapp.exe", "claude.exe"})


def default_ticked(entry: M.SnapshotEntry) -> bool:
    """Identified files, folders and URLs are ticked; chat/mail apps and unidentified windows are not."""
    raise NotImplementedError("windows.default_ticked")


def add_label(entry: M.SnapshotEntry) -> str:
    """The picker's label: exactly what will be added ("Line list.xlsx · Excel", "'Drawing1 - AutoCAD': no file")."""
    raise NotImplementedError("windows.add_label")


def items_from_entries(entries: list[M.SnapshotEntry], project_id: str = "") -> list[M.ActivityItem]:
    """Identified entries as activity items, in the given order, without duplicate paths."""
    raise NotImplementedError("windows.items_from_entries")
