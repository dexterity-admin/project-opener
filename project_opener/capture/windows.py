"""Helpers for "add this window" and "start from what's open".  Owner: builder 2.

Pure decisions over ``SnapshotEntry`` lists (testable without Win32).
"""
from __future__ import annotations

import os

from project_opener.capture.diff import norm_path, norm_url
from project_opener.core import models as M

# Applications whose windows are not activity items by default (chat, mail): unticked in
# "start from what's open".  Decision data, not a guess about the user's intent.
NON_FILE_PROCESSES = frozenset({"outlook.exe", "ms-teams.exe", "teams.exe", "cliq.exe", "zoho cliq.exe",
                                "slack.exe", "whatsapp.exe", "claude.exe"})

# Row statuses shown in the live list and the candidates list (worst first).  ``unidentified`` is
# "needs a path" (a document app showing a file whose path is not known); ``window`` is "not a file".
STATUS_ORDER = ("ambiguous", "unidentified", "offline", "unsaved", "window", "identified")


def display_status(entry: M.SnapshotEntry, offline: bool = False) -> str:
    """The honest state of one entry for the lists:

    ``identified`` (a proven path/URL), ``offline`` (identified, but its server is down),
    ``ambiguous`` (several files with that name), ``unidentified`` (needs a path: a document app
    showing a file it could not find a path for), ``unsaved`` (no file yet), ``window`` (not a
    file: an application window with no document)."""
    if entry.status == "identified":
        return "offline" if offline else "identified"
    if entry.status == "ambiguous":
        return "ambiguous"
    if entry.status == "unsaved":
        return "unsaved"
    return "unidentified" if entry.doc_name else "window"


def needs_you(status: str) -> bool:
    return status in ("ambiguous", "unidentified")


def default_ticked(entry: M.SnapshotEntry) -> bool:
    """Identified files, folders and URLs are ticked; chat/mail apps and unidentified windows are not."""
    if entry.process.lower() in NON_FILE_PROCESSES:
        return False
    return entry.identified and entry.kind in ("file", "folder", "url")


def entry_name(entry: M.SnapshotEntry) -> str:
    """Short display name: the file or folder name, the tab title for a URL, else the window title."""
    if entry.identified:
        if entry.kind == "url":
            return entry.doc_name or norm_url(entry.path)
        tail = os.path.basename(entry.path.rstrip("\\/"))
        return tail or entry.path
    return entry.doc_name or entry.title


def label_lines(entry: M.SnapshotEntry) -> tuple[str, str]:
    """(what it is, what will happen): "Line list.xlsx · Excel" / the path; "AutoCAD · Drawing1.dwg" /
    "Unsaved: no file yet. ..."."""
    app = entry.app or entry.process
    if entry.identified:
        if entry.kind == "url":
            return f"{entry_name(entry)} · {app}", f"{entry.path} (active tab only)"
        return f"{entry_name(entry)} · {app}", entry.path
    name = entry.doc_name or entry.title
    if entry.status == "unsaved":
        return f"{app} · {name}", f"Unsaved: no file yet. You will be asked for its path, or can add {app} itself."
    if entry.status == "ambiguous":
        return f"{app} · {name}", f"{len(entry.candidates)} files have this name. You will be asked which one."
    if entry.doc_name:
        return f"{app} · {name}", "No file path found. You will be asked for it once."
    return f"{app} · {entry.title}", f"Not a file. You can add {app} itself as an application."


def add_label(entry: M.SnapshotEntry) -> str:
    """The picker's label: exactly what will be added, two lines split at the first newline (the
    picker shows the first bold, the second muted)."""
    first, second = label_lines(entry)
    return f"{first}\n{second}" if second else first


def add_message(entry: M.SnapshotEntry) -> str:
    """One line for ``addResult`` when the window cannot simply be added."""
    first, second = label_lines(entry)
    return f"{first}: {second}"


def items_from_entries(entries: list[M.SnapshotEntry], project_id: str = "") -> list[M.ActivityItem]:
    """Identified entries as activity items, in the given order, without duplicate paths."""
    seen: set[str] = set()
    out: list[M.ActivityItem] = []
    for e in entries:
        if not e.identified:
            continue
        k = norm_url(e.path) if e.kind == "url" else norm_path(e.path)
        if k in seen:
            continue
        seen.add(k)
        item = e.to_item(project_id)
        if e.kind == "url" and e.doc_name:
            item.label = e.doc_name
        out.append(item)
    return out


def app_item(entry: M.SnapshotEntry, project_id: str = "") -> M.ActivityItem | None:
    """The window's application itself as an item ("add AutoCAD"); None without a known exe."""
    if not entry.exe:
        return None
    return M.ActivityItem(path=entry.exe, kind="app", label=entry.app or entry.process, project_id=project_id)


def dedupe(entries: list[M.SnapshotEntry]) -> list[M.SnapshotEntry]:
    """One entry per key, first (front-most) kept."""
    seen: set[str] = set()
    out: list[M.SnapshotEntry] = []
    for e in entries:
        if e.key in seen:
            continue
        seen.add(e.key)
        out.append(e)
    return out


def worst_first(entries: list[M.SnapshotEntry], statuses: dict[str, str]) -> list[M.SnapshotEntry]:
    """Stable sort by ``STATUS_ORDER`` of each entry's display status (``statuses``: key -> status)."""
    rank = {s: i for i, s in enumerate(STATUS_ORDER)}
    return sorted(entries, key=lambda e: rank.get(statuses.get(e.key, "window"), len(rank)))


def ignore_rule(entry: M.SnapshotEntry) -> dict[str, str]:
    """A ``Settings.capture_ignore`` rule for exactly this process and title (glob characters escaped)."""
    title = "".join(f"[{c}]" if c in "*?[" else c for c in entry.title)
    return {"process": entry.process.lower(), "title": title}
