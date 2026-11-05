"""Restorer: reopen a snapshot in order and put windows back.  Owner: builder 2.

Runs on the capture thread (COM).  Order: the activity's launch order
(``diff.order_for_restore``).  Opening: Office files through COM, folders through
``explorer.exe <path>``, URLs through the recorded browser with ``--new-window``,
everything else through ``core.launcher`` (variables, profiles).  Then, for up to
``RESTORE_SETTLE_S``, identify every *new* top-level window the way capture does,
match by identity (path/URL) first and process + title similarity (0.55) only for
title-identified apps, and place each as soon as it matches.

Never moves, closes or terminates a window it did not just open: only windows whose
hwnd did not exist when the restore began are candidates, and a document that is
already open is left where it is.  Unsaved and unidentified entries are reported,
not restored.
"""
from __future__ import annotations

import difflib
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from project_opener.capture import diff
from project_opener.capture.windows import entry_name
from project_opener.core import models as M

log = logging.getLogger(__name__)

TITLE_SIMILARITY = 0.55


@dataclass
class RestoreResult:
    key: str
    label: str
    opened: bool = False
    placed: bool = False
    matched_by: str = ""             # identity | title | ""
    message: str = ""
    how: str = ""                    # "Office (COM)", "explorer.exe", "chrome.exe --new-window", "association"
    open_s: float = 0.0              # how long the open call took
    placed_at_s: float = 0.0         # seconds from the start of the restore to the window being placed
    hwnd: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "opened": self.opened, "placed": self.placed,
                "matchedBy": self.matched_by, "message": self.message, "how": self.how,
                "openS": round(self.open_s, 1), "placedAtS": round(self.placed_at_s, 1)}


@dataclass
class RestoreReport:
    results: list[RestoreResult] = field(default_factory=list)
    unrestorable: list[M.SnapshotEntry] = field(default_factory=list)   # unsaved / unidentified, listed
    seconds: float = 0.0

    def to_dict(self) -> dict:
        return {"opened": sum(r.opened for r in self.results), "placed": sum(r.placed for r in self.results),
                "failed": [r.label for r in self.results if not r.opened],
                "unrestorable": [e.title for e in self.unrestorable], "seconds": round(self.seconds, 1),
                "results": [r.to_dict() for r in self.results]}


# ------------------------------------------------------------------ pure maths
def _w(r: list[int]) -> int:
    return r[2] - r[0]


def _h(r: list[int]) -> int:
    return r[3] - r[1]


def _shift(r: list[int], dx: int, dy: int) -> list[int]:
    return [r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy]


def _fit(r: list[int], area: list[int]) -> list[int]:
    """Shrink ``r`` to fit ``area`` and move it inside, keeping its size where possible."""
    w = min(_w(r), _w(area))
    h = min(_h(r), _h(area))
    left = min(max(r[0], area[0]), area[2] - w)
    top = min(max(r[1], area[1]), area[3] - h)
    return [left, top, left + w, top + h]


def plan_placement(saved: M.WindowPlacement | None, monitors: list[M.Monitor]) -> M.WindowPlacement | None:
    """Where to put a window now, given where it was and the monitors there are now.

    Same monitor (device and rectangle) -> exactly as saved.  Same device moved -> shifted with it.
    Monitor gone -> the same offset on the primary monitor, shrunk to fit its work area.  The
    show state (normal / maximised / minimised) is kept.  None when nothing was saved."""
    if saved is None:
        return None
    rect = list(saved.normal_rect)
    if _w(rect) <= 0 or _h(rect) <= 0:
        return None
    if not monitors:
        return M.WindowPlacement(saved.show_cmd, rect, list(saved.window_rect), saved.monitor, list(saved.monitor_rect))
    same = next((m for m in monitors if m.device == saved.monitor and list(m.rect) == list(saved.monitor_rect)), None)
    if same is None:
        same = next((m for m in monitors if list(m.rect) == list(saved.monitor_rect)), None)
    if same is not None:
        return M.WindowPlacement(saved.show_cmd, rect, list(saved.window_rect), same.device, list(same.rect))
    target = next((m for m in monitors if m.device == saved.monitor), None)
    if target is None:
        target = next((m for m in monitors if m.primary), monitors[0])
    old_origin = saved.monitor_rect[:2] if _w(saved.monitor_rect) > 0 else rect[:2]
    moved = _shift(rect, target.rect[0] - old_origin[0], target.rect[1] - old_origin[1])
    area = list(target.work) if _w(target.work) > 0 else list(target.rect)
    return M.WindowPlacement(saved.show_cmd, _fit(moved, area), [], target.device, list(target.rect))


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def match_window(found: M.SnapshotEntry | None, title: str, process: str, pending: list[M.SnapshotEntry],
                 portable: Callable[[str], str] | None = None) -> tuple[M.SnapshotEntry | None, str]:
    """Which pending entry a new window is: by identity (same path/URL), else, for entries that were
    themselves identified from a title, by the same process and a similar title (>= 0.55, or the
    document name inside the title).  Returns (entry, "identity" | "title") or (None, "")."""
    if found is not None and found.identified:
        for p in pending:
            if diff.same_target(found.path, p.path, portable):
                return p, "identity"
    best: M.SnapshotEntry | None = None
    best_s = 0.0
    for p in pending:
        if not p.identified_by.startswith("title") or p.process.lower() != process.lower():
            continue
        s = similarity(p.title, title)
        name = p.doc_name or os.path.basename(p.path.rstrip("\\/"))
        if name and name.lower() in title.lower():
            s = max(s, 0.9)
        if s > best_s:
            best, best_s = p, s
    if best is not None and best_s >= TITLE_SIMILARITY:
        return best, "title"
    return None, ""


# ------------------------------------------------------------------ platform
class Win32Platform:
    """The real desktop.  ``identifier`` is the capture thread's Identifier."""

    def __init__(self, identifier: Any, exclude_pids: set[int] | None = None):
        self.identifier = identifier
        self.exclude_pids = exclude_pids or set()

    def existing_hwnds(self) -> set[int]:
        from project_opener.capture import win32
        return win32.all_top_level_hwnds()

    def windows(self) -> list:
        from project_opener.capture import win32
        return win32.enumerate_windows(self.exclude_pids)

    def identify(self, windows: list, item_paths: list[str], full: bool) -> list[M.SnapshotEntry]:
        return self.identifier.identify(windows, item_paths, full=full, apply_ignore=False)

    def monitors(self) -> list[M.Monitor]:
        from project_opener.capture import win32
        return win32.monitors()

    def apply_placement(self, hwnd: int, placement: M.WindowPlacement) -> bool:
        from project_opener.capture import win32
        return win32.apply_placement(hwnd, placement)

    def open_office(self, path: str) -> bool:
        from project_opener.capture.sources import office
        return office.open_document(path)

    def open_folder(self, path: str) -> None:
        from project_opener.capture.sources import explorer
        explorer.open_folder(path)

    def open_url(self, url: str, exe: str) -> None:
        from project_opener.capture.sources import browser
        browser.open_url(url, exe)

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def sleep(self, s: float) -> None:
        time.sleep(s)

    def now(self) -> float:
        return time.monotonic()


# ------------------------------------------------------------------ the restorer
class Restorer:
    def __init__(self, open_item: Callable[[M.Item], object], settle_s: float = 25.0, *, platform: Any = None,
                 office_via_com: bool = True, portable: Callable[[str], str] | None = None,
                 resolve: Callable[[str], str] | None = None, gap_s: float = 0.3, poll_s: float = 0.5):
        """``open_item`` is the launcher's open for non-Office items (variables, profiles honoured)."""
        self.open_item = open_item
        self.settle_s = settle_s
        self.platform = platform
        self.office_via_com = office_via_com
        self.portable = portable
        self.resolve = resolve
        self.gap_s = gap_s
        self.poll_s = poll_s

    # -------------------------------------------------------------- opening
    def _open(self, e: M.SnapshotEntry, item: M.Item | None) -> tuple[bool, str, str]:
        """(opened, how, message)."""
        p = self.platform
        path = e.path
        try:
            if e.kind == "url":
                p.open_url(path, e.exe)
                exe = os.path.basename(e.exe) if e.exe else ""
                return True, (f"{exe} --new-window" if exe else "default browser"), ""
            if e.kind == "folder":
                if not p.exists(path):
                    return False, "", "folder not found"
                p.open_folder(path)
                return True, "explorer.exe", ""
            if e.kind == "file" and p.exists(path) and self.office_via_com:
                from project_opener.capture.sources.office import app_for_path
                if app_for_path(path) and p.open_office(path):
                    return True, "Office (COM)", ""
            res = self.open_item(item or e.to_item())
            status = getattr(res, "status", "opened" if res in (None, True) else "failed")
            if status == "opened":
                return True, "association", ""
            return False, "", str(getattr(res, "message", "") or status)
        except Exception as exc:  # noqa: BLE001 - one item never stops the restore
            log.info("restore: open failed for %s: %s", path, exc)
            return False, "", str(exc)

    # -------------------------------------------------------------- main
    def restore(self, snapshot: M.Snapshot, items: list[M.Item],
                progress: Callable[[int, int, str], None] | None = None) -> RestoreReport:
        if self.platform is None:
            raise RuntimeError("Restorer needs a platform (Win32Platform on the capture thread)")
        p = self.platform
        t0 = p.now()
        report = RestoreReport(unrestorable=diff.unrestorable(snapshot))
        order = diff.order_for_restore(snapshot, items)
        by_id = {it.id: it for it in items}
        total = len(order)

        def tell(done: int, label: str) -> None:
            if progress:
                try:
                    progress(done, total, label)
                except Exception:  # noqa: BLE001
                    pass

        before = p.existing_hwnds()
        current = p.windows()
        open_now = [e for e in p.identify(current, [e.path for e in order], False) if e.identified]

        pending: list[M.SnapshotEntry] = []
        results: dict[str, RestoreResult] = {}
        monitors = p.monitors()
        matched: set[int] = set()
        retry: list[tuple[int, M.SnapshotEntry, M.WindowPlacement]] = []

        def match_round() -> None:
            """Identify the windows that appeared since the restore began, match, place at once."""
            for hwnd, e, plan in list(retry):        # one more try for windows that resized themselves
                retry.remove((hwnd, e, plan))
                if p.apply_placement(hwnd, plan):
                    results[e.key].placed, results[e.key].message = True, ""
                    results[e.key].placed_at_s = p.now() - t0
            if not pending:
                return
            new = [w for w in p.windows() if w.hwnd not in before and w.hwnd not in matched]
            if not new:
                return
            found = p.identify(new, [e.path for e in pending], True)
            for w, f in zip(new, found, strict=False):
                m, how = match_window(f, w.title, w.process, pending, self.portable)
                if m is None:
                    continue
                matched.add(w.hwnd)
                pending.remove(m)
                r = results[m.key]
                r.matched_by, r.hwnd = how, w.hwnd
                plan = plan_placement(m.placement, monitors)
                if plan is None:
                    r.message = "no saved position"
                elif p.apply_placement(w.hwnd, plan):
                    r.placed = True
                    r.placed_at_s = p.now() - t0
                else:
                    r.message = "position did not hold"
                    retry.append((w.hwnd, m, plan))
                if not pending:
                    return

        for i, e in enumerate(order):
            label = entry_name(e)
            r = RestoreResult(key=e.key, label=label)
            results[e.key] = r
            report.results.append(r)
            if any(diff.same_target(o.path, e.path, self.portable) for o in open_now):
                r.opened, r.message = True, "already open; left where it is"
                tell(i + 1, label)
                continue
            t_open = p.now()
            r.opened, r.how, r.message = self._open(e, by_id.get(e.item_id))
            r.open_s = p.now() - t_open
            if r.opened:
                pending.append(e)
            tell(i + 1, label)
            if i < total - 1 and self.gap_s:
                p.sleep(self.gap_s)
            match_round()                            # place early windows while later items launch

        # the settle window starts when the last item has been launched (a cold Office start can take
        # longer than the whole window; counting from t0 would leave no time to match anything)
        deadline = p.now() + self.settle_s
        while (pending or retry) and p.now() < deadline:
            p.sleep(self.poll_s)
            match_round()
        for e in pending:
            results[e.key].message = f"opened; no window found within {self.settle_s:.0f} s, left where it opened"
        report.seconds = p.now() - t0
        tell(total, "done")
        return report
