"""Space map scanner: space used, duplicate files and stale files under the office's project folders.

Scope (docs/V4-PLUS-BRIEF.md section 4): every folder item on the Team Hub's project cards (published
projects and activities, created by anyone on the LAN) and nothing else.  ``roots_from_cards`` turns the
cards into scan roots; ``Scanner`` walks them on a background thread at low priority.

**Report only.**  Nothing here deletes, moves, renames or writes into a scanned folder; the only file written
is the cache (``cache_path``), which lives on the hub (or the data folder) and never inside a scanned tree.

What it reports, all of it measured, none of it judged:
- size and file count per folder (every level, for drill-down);
- duplicate groups: files of the same size (>= ``min_dup_bytes``) whose content hashes match, oldest copy
  first (the others are counted as "extra copies"; nothing says which one to keep).  Only files that share a
  size with another file are read: first a 64 KiB head hash, then a full hash for those whose heads match;
- stale files: not modified for ``stale_months`` months (a setting);
- what was skipped and why (unreachable share, access denied, path errors, links not followed).

Network safety: a root that cannot be listed is skipped with its reason; paths longer than 240 characters
are opened through the ``\\\\?\\`` prefix; links and junctions are not followed (no loops, no counting a
folder twice).  A re-scan re-lists the folders (a listing is cheap) and reuses every hash whose
(path, size, modified time) is unchanged, from the cache.
"""
from __future__ import annotations

import hashlib
import logging
import os
import stat
import sys
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from project_opener.core.jsonio import read_json, write_json_atomic

log = logging.getLogger(__name__)

CACHE_VERSION = 1
HEAD_BYTES = 64 * 1024
CHUNK = 1024 * 1024
MONTH_S = 30.44 * 86400
LONG_PATH = 240
MAX_DUP_GROUPS = 400            # kept in the result (largest wasted space first)
MAX_STALE = 400                 # stale files kept in the result (largest first)


# ----------------------------------------------------------------------------- roots
@dataclass
class ScanRoot:
    path: str                           # resolved, as this PC reaches it
    cards: list[str] = field(default_factory=list)      # titles of the cards that name this folder

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "cards": list(self.cards)}


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path)).rstrip("\\/")


def _inside(child: str, parent: str) -> bool:
    c, p = _norm(child), _norm(parent)
    return c == p or c.startswith(p + os.sep)


def roots_from_cards(cards: Iterable[tuple[str, Iterable[str]]]) -> tuple[list[ScanRoot], dict[str, list[str]]]:
    """Pure.  ``cards`` = (card title, folder paths already resolved).  Returns the unique scan roots (a
    folder inside another card's folder is scanned once, as part of the outer one) and, per card title,
    the folders it names (for the card bubbles)."""
    by_card: dict[str, list[str]] = {}
    seen: dict[str, ScanRoot] = {}
    for title, folders in cards:
        for f in folders:
            f = (f or "").strip()
            if not f:
                continue
            f = os.path.normpath(f)
            lst = by_card.setdefault(title, [])
            if _norm(f) not in {_norm(x) for x in lst}:
                lst.append(f)
            key = _norm(f)
            if key not in seen:
                seen[key] = ScanRoot(f, [])
            if title not in seen[key].cards:
                seen[key].cards.append(title)
    roots = sorted(seen.values(), key=lambda r: len(_norm(r.path)))
    out: list[ScanRoot] = []
    for r in roots:
        outer = next((o for o in out if _inside(r.path, o.path)), None)
        if outer is None:
            out.append(r)
        else:
            outer.cards.extend(c for c in r.cards if c not in outer.cards)
    order = list(seen.values())
    out.sort(key=order.index)                   # the cards' order, not the nesting pass's
    for t in by_card:                   # a card's folder nested in another of its own folders counts once
        lst = sorted(by_card[t], key=lambda p: len(_norm(p)))
        by_card[t] = [p for i, p in enumerate(lst) if not any(_inside(p, q) for q in lst[:i])]
    return out, by_card


# ----------------------------------------------------------------------------- result
@dataclass
class Folder:
    path: str
    size: int = 0                       # bytes under this folder (all levels)
    files: int = 0
    flagged: int = 0                    # bytes in extra duplicate copies or stale files (each file once)
    children: list[str] = field(default_factory=list)


@dataclass
class ScanResult:
    roots: list[ScanRoot] = field(default_factory=list)
    cards: dict[str, list[str]] = field(default_factory=dict)      # card title -> its folders (roots_from_cards)
    folders: dict[str, Folder] = field(default_factory=dict)       # normcase path -> folder
    duplicates: list[dict[str, Any]] = field(default_factory=list)  # {size, hash, paths, wasted}
    stale: list[dict[str, Any]] = field(default_factory=list)       # {path, size, mtime}
    stale_count: int = 0
    stale_bytes: int = 0
    skipped: list[dict[str, str]] = field(default_factory=list)     # {path, reason}
    files: int = 0
    size: int = 0
    scanned_at: str = ""
    stale_months: int = 12
    complete: bool = False
    seconds: float = 0.0

    def folder(self, path: str) -> Folder | None:
        return self.folders.get(_norm(path))

    @property
    def dup_wasted(self) -> int:
        return sum(int(g["wasted"]) for g in self.duplicates)

    def to_dict(self) -> dict[str, Any]:
        return {"roots": [r.to_dict() for r in self.roots], "cards": self.cards,
                "folders": [[f.path, f.size, f.files, f.flagged, [os.path.basename(c) for c in f.children]]
                            for f in self.folders.values()],
                "duplicates": self.duplicates, "stale": self.stale, "stale_count": self.stale_count,
                "stale_bytes": self.stale_bytes, "skipped": self.skipped, "files": self.files, "size": self.size,
                "scanned_at": self.scanned_at, "stale_months": self.stale_months, "complete": self.complete,
                "seconds": round(self.seconds, 1)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ScanResult:
        r = cls()
        r.roots = [ScanRoot(str(x.get("path", "")), [str(c) for c in x.get("cards", [])])
                   for x in d.get("roots", []) if isinstance(x, dict)]
        cards = d.get("cards", {})
        r.cards = {str(k): [str(p) for p in v] for k, v in cards.items() if isinstance(v, list)} \
            if isinstance(cards, dict) else {}
        for row in d.get("folders", []):
            try:
                path, size, files, flagged, kids = row
            except (TypeError, ValueError):
                continue
            f = Folder(str(path), int(size), int(files), int(flagged), [os.path.join(str(path), k) for k in kids])
            r.folders[_norm(f.path)] = f
        r.duplicates = [g for g in d.get("duplicates", []) if isinstance(g, dict)]
        r.stale = [s for s in d.get("stale", []) if isinstance(s, dict)]
        r.skipped = [s for s in d.get("skipped", []) if isinstance(s, dict)]
        for k in ("stale_count", "stale_bytes", "files", "size", "stale_months"):
            setattr(r, k, int(d.get(k, getattr(r, k)) or 0))
        r.scanned_at = str(d.get("scanned_at", ""))
        r.complete = bool(d.get("complete", False))
        r.seconds = float(d.get("seconds", 0.0) or 0.0)
        return r


@dataclass
class Progress:
    phase: str = "listing"              # listing | comparing | saving
    folders: int = 0
    files: int = 0
    size: int = 0
    current: str = ""
    candidates: int = 0                 # files being compared (phase comparing)
    compared: int = 0
    root_sizes: dict[str, int] = field(default_factory=dict)       # root path -> bytes so far


# ----------------------------------------------------------------------------- helpers
def long_path(path: str) -> str:
    """The ``\\\\?\\`` form of a long Windows path (UNC -> ``\\\\?\\UNC\\``); other paths unchanged."""
    if sys.platform != "win32" or len(path) < LONG_PATH or path.startswith("\\\\?\\"):
        return path
    p = os.path.abspath(path)
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p[2:]
    return "\\\\?\\" + p


def short_path(path: str) -> str:
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    if path.startswith("\\\\?\\"):
        return path[4:]
    return path


def lower_thread_priority() -> None:
    """Background mode for the calling thread on Windows (CPU and I/O priority); best effort elsewhere."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.GetCurrentThread()
        if not k32.SetThreadPriority(h, 0x00010000):      # THREAD_MODE_BACKGROUND_BEGIN
            k32.SetThreadPriority(h, -2)                  # THREAD_PRIORITY_LOWEST
    except Exception:  # noqa: BLE001
        log.debug("could not lower the scan thread's priority")


def _is_link(entry: os.DirEntry[str]) -> bool:
    try:
        if entry.is_symlink():
            return True
        junction = getattr(entry, "is_junction", None)
        if junction is not None and junction():
            return True
        st = entry.stat(follow_symlinks=False)
        return bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError:
        return False


def _reason(exc: BaseException) -> str:
    if isinstance(exc, PermissionError):
        return "access denied"
    if isinstance(exc, FileNotFoundError):
        return "not found"
    if isinstance(exc, TimeoutError):
        return "timed out"
    win = getattr(exc, "winerror", None)
    if win in (53, 67, 64, 1231, 1232, 121):
        return "server not reachable"
    if win == 206:
        return "path too long"
    return (getattr(exc, "strerror", None) or type(exc).__name__).lower()


class Cancelled(Exception):
    pass


# ----------------------------------------------------------------------------- scanner
class Scanner:
    """One scan of ``roots``.  ``run()`` does the work on the calling thread; ``start()`` runs it on a
    daemon thread at low priority.  ``on_progress(Progress)`` is called at most every ``tick_s`` from the
    scan thread; ``on_done(ScanResult)`` once at the end (also after a cancel, with ``complete`` False)."""

    def __init__(self, roots: list[ScanRoot], stale_months: int = 12, cache_path: Path | None = None,
                 cards: dict[str, list[str]] | None = None,
                 min_dup_bytes: int = 4096, on_progress: Callable[[Progress], None] | None = None,
                 on_done: Callable[[ScanResult], None] | None = None,
                 on_error: Callable[[BaseException], None] | None = None,
                 now: float | None = None, tick_s: float = 0.3):
        self.roots = roots
        self.cards = cards if cards is not None else {c: [r.path] for r in roots for c in r.cards}
        self.stale_months = max(1, int(stale_months))
        self.cache_path = cache_path
        self.min_dup_bytes = max(1, int(min_dup_bytes))
        self.on_progress = on_progress
        self.on_done = on_done
        self.on_error = on_error
        self.now = now
        self.tick_s = tick_s
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_tick = 0.0
        self.progress = Progress()

    # -- control
    def start(self) -> None:
        self._thread = threading.Thread(target=self._thread_main, name="spacemap-scan", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _thread_main(self) -> None:
        lower_thread_priority()
        try:
            res = self.run()
        except BaseException as exc:  # noqa: BLE001
            log.exception("space map scan failed")
            if self.on_error:
                self.on_error(exc)
            return
        if self.on_done:
            self.on_done(res)

    def _check(self) -> None:
        if self._cancel.is_set():
            raise Cancelled

    def _tick(self, force: bool = False) -> None:
        t = time.monotonic()
        if self.on_progress and (force or t - self._last_tick >= self.tick_s):
            self._last_tick = t
            p = self.progress
            self.on_progress(Progress(p.phase, p.folders, p.files, p.size, p.current, p.candidates, p.compared,
                                      dict(p.root_sizes)))

    # -- the scan
    def run(self) -> ScanResult:
        t0 = time.monotonic()
        now = self.now if self.now is not None else time.time()
        stale_before = now - self.stale_months * MONTH_S
        res = ScanResult(roots=list(self.roots), cards=dict(self.cards), stale_months=self.stale_months,
                         scanned_at=datetime.fromtimestamp(now).astimezone().isoformat(timespec="seconds"))
        old_hashes = self._load_hashes()
        by_size: dict[int, list[tuple[str, float]]] = {}
        stale_all: list[tuple[int, str, float]] = []
        file_flag: dict[str, int] = {}          # file path -> size, for files counted as flagged
        dir_files: dict[str, list[tuple[str, int]]] = {}    # normcase dir -> direct files (name, size), flagged only
        try:
            for root in self.roots:
                self._walk(root, res, by_size, stale_all, stale_before)
            self.progress.phase = "comparing"
            dup_groups, new_hashes = self._duplicates(by_size, old_hashes)
            res.complete = True
        except Cancelled:
            dup_groups, new_hashes = [], {}
            res.skipped.append({"path": "", "reason": "scan stopped before the end"})
        # flagged bytes per file (duplicate or stale, counted once)
        for size, path, _m in stale_all:
            file_flag[path] = size
        for g in dup_groups:             # the extra copies: every member but the oldest (as ``wasted`` counts)
            for p in g["paths"][1:]:
                file_flag[p] = g["size"]
        for p, size in file_flag.items():
            d = _norm(os.path.dirname(p))
            dir_files.setdefault(d, []).append((os.path.basename(p), size))
        self._roll_up(res, dir_files)
        stale_all.sort(key=lambda t: -t[0])
        res.stale_count = len(stale_all)
        res.stale_bytes = sum(t[0] for t in stale_all)
        res.stale = [{"path": p, "size": s, "mtime": m} for s, p, m in stale_all[:MAX_STALE]]
        dup_groups.sort(key=lambda g: -g["wasted"])
        res.duplicates = dup_groups[:MAX_DUP_GROUPS]
        res.seconds = time.monotonic() - t0
        self.progress.phase = "saving"
        self._tick(force=True)
        self._save(res, {**old_hashes, **new_hashes} if not res.complete else new_hashes)
        return res

    def _walk(self, root: ScanRoot, res: ScanResult, by_size: dict[int, list[tuple[str, float]]],
              stale_all: list[tuple[int, str, float]], stale_before: float) -> None:
        top = root.path
        self.progress.root_sizes.setdefault(top, 0)
        try:
            if not os.path.isdir(long_path(top)):
                res.skipped.append({"path": top, "reason": "not reachable from this PC"})
                return
        except OSError as exc:
            res.skipped.append({"path": top, "reason": _reason(exc)})
            return
        stack = [top]
        while stack:
            self._check()
            d = stack.pop()
            key = _norm(d)
            folder = res.folders.setdefault(key, Folder(d))
            self.progress.current = d
            try:
                with os.scandir(long_path(d)) as it:
                    entries = list(it)
            except OSError as exc:
                res.skipped.append({"path": d, "reason": _reason(exc)})
                continue
            self.progress.folders += 1
            for e in entries:
                path = os.path.join(d, e.name)
                try:
                    if _is_link(e):
                        res.skipped.append({"path": path, "reason": "link not followed"})
                        continue
                    if e.is_dir(follow_symlinks=False):
                        folder.children.append(path)
                        stack.append(path)
                        continue
                    st = e.stat(follow_symlinks=False)
                except OSError as exc:
                    res.skipped.append({"path": path, "reason": _reason(exc)})
                    continue
                size, mtime = int(st.st_size), float(st.st_mtime)
                folder.size += size
                folder.files += 1
                res.files += 1
                res.size += size
                self.progress.files += 1
                self.progress.size += size
                self.progress.root_sizes[top] += size
                if mtime < stale_before:
                    stale_all.append((size, path, mtime))
                if size >= self.min_dup_bytes:
                    by_size.setdefault(size, []).append((path, mtime))
            self._tick()

    def _duplicates(self, by_size: dict[int, list[tuple[str, float]]],
                    old: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, str]]:
        cands = {s: v for s, v in by_size.items() if len(v) > 1}
        self.progress.candidates = sum(len(v) for v in cands.values())
        self.progress.compared = 0
        new: dict[str, str] = {}
        groups: list[dict[str, Any]] = []

        def digest(path: str, size: int, mtime: float, head: bool) -> str | None:
            key = f"{'h' if head else 'f'}|{_norm(path)}|{size}|{int(mtime)}"
            if key in old:
                new[key] = old[key]
                return old[key]
            h = hashlib.blake2b(digest_size=20)
            try:
                with open(long_path(path), "rb") as fh:
                    left = HEAD_BYTES if head else size
                    while left > 0:
                        self._check()
                        buf = fh.read(min(CHUNK, left))
                        if not buf:
                            break
                        h.update(buf)
                        left -= len(buf)
            except OSError:
                return None
            new[key] = h.hexdigest()
            return new[key]

        for size in sorted(cands, reverse=True):
            files = cands[size]
            by_head: dict[str, list[tuple[str, float]]] = {}
            for path, mtime in files:
                self._check()
                hd = digest(path, size, mtime, True)
                if hd is not None:
                    by_head.setdefault(hd, []).append((path, mtime))
            for same_head in by_head.values():
                if len(same_head) < 2:
                    continue
                if size <= HEAD_BYTES:
                    buckets = {"": same_head}
                else:
                    buckets = {}
                    for path, mtime in same_head:
                        self.progress.current = path
                        self._tick()
                        fd = digest(path, size, mtime, False)
                        if fd is not None:
                            buckets.setdefault(fd, []).append((path, mtime))
                for full, members in buckets.items():
                    if len(members) > 1:
                        members.sort(key=lambda t: t[1])
                        groups.append({"size": size, "hash": full or "head", "paths": [p for p, _ in members],
                                       "mtimes": [m for _, m in members], "wasted": size * (len(members) - 1)})
            self.progress.compared += len(files)
            self._tick()
        return groups, new

    def _roll_up(self, res: ScanResult, dir_files: dict[str, list[tuple[str, int]]]) -> None:
        """Folder sizes are direct-only after the walk; add each folder into its ancestors (deepest first)."""
        for key, files in dir_files.items():
            f = res.folders.get(key)
            if f is not None:
                f.flagged += sum(s for _n, s in files)
        order = sorted(res.folders.values(), key=lambda f: -len(f.path))
        for f in order:
            for c in f.children:
                child = res.folders.get(_norm(c))
                if child is not None:
                    f.size += child.size
                    f.files += child.files
                    f.flagged += child.flagged
        for f in res.folders.values():   # children that could not be listed stay out of the drill-down
            f.children = [c for c in f.children if _norm(c) in res.folders]

    # -- cache
    def _load_hashes(self) -> dict[str, str]:
        if not self.cache_path:
            return {}
        d = read_json(self.cache_path, {}) or {}
        if not isinstance(d, dict) or d.get("version") != CACHE_VERSION:
            return {}
        h = d.get("hashes", {})
        return {str(k): str(v) for k, v in h.items()} if isinstance(h, dict) else {}

    def _save(self, res: ScanResult, hashes: dict[str, str]) -> None:
        if not self.cache_path:
            return
        try:
            write_json_atomic(self.cache_path, {"version": CACHE_VERSION, "result": res.to_dict(), "hashes": hashes},
                              indent=0)
        except OSError as exc:
            res.skipped.append({"path": str(self.cache_path), "reason": f"cache not saved ({_reason(exc)})"})


def load_cached(cache_path: Path | None) -> ScanResult | None:
    """The last saved scan, or None (no file, unreadable, another version)."""
    if not cache_path:
        return None
    d = read_json(cache_path, None)
    if not isinstance(d, dict) or d.get("version") != CACHE_VERSION or not isinstance(d.get("result"), dict):
        return None
    try:
        return ScanResult.from_dict(d["result"])
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------- the map's levels
MAX_BUBBLES = 36


def _bubble(key: str, label: str, size: int, flagged: int, drillable: bool, detail: str = "") -> dict[str, Any]:
    return {"bubbleKey": key, "label": label, "bytes": int(size), "sizeText": size_text(size),
            "share": (min(1.0, flagged / size) if size > 0 else 0.0), "drillable": drillable, "detail": detail}


def _card_folders(res: ScanResult, title: str) -> list[Folder]:
    return [f for f in (res.folder(p) for p in res.cards.get(title, [])) if f is not None]


def level(res: ScanResult, nav: list[str], live_sizes: dict[str, int] | None = None) -> dict[str, Any]:
    """Pure.  The bubbles, breadcrumbs and scope (folders the side lists keep to; None = everything) at
    ``nav`` (keys from the root: ``card:<title>``, then folder paths).  ``live_sizes`` (root path -> bytes)
    sizes the card bubbles while the first scan is still listing and there are no folders yet."""
    crumbs = [{"label": "All projects", "depth": 0}]
    for i, key in enumerate(nav, start=1):
        crumbs.append({"label": key[5:] if key.startswith("card:") else os.path.basename(key.rstrip("\\/")) or key,
                       "depth": i})
    bubbles: list[dict[str, Any]] = []
    scope: list[str] | None = None
    last = nav[-1] if nav else ""
    if not nav:
        for title, paths in res.cards.items():
            folders = _card_folders(res, title)
            if folders:
                size, flagged = sum(f.size for f in folders), sum(f.flagged for f in folders)
            elif live_sizes:
                size = sum(v for p, v in live_sizes.items() if any(_inside(q, p) or _inside(p, q) for q in paths))
                flagged = 0
            else:
                continue
            detail = paths[0] if len(paths) == 1 else f"{len(paths)} folders"
            bubbles.append(_bubble("card:" + title, title, size, flagged, bool(folders), detail))
    elif last.startswith("card:"):
        folders = _card_folders(res, last[5:])
        scope = [f.path for f in folders]
        if len(folders) == 1:
            bubbles = _folder_bubbles(res, folders[0])
        else:
            bubbles = [_bubble(f.path, os.path.basename(f.path.rstrip("\\/")) or f.path, f.size, f.flagged, True,
                               f.path) for f in folders]
    else:
        f = res.folder(last)
        scope = [last]
        if f is not None:
            bubbles = _folder_bubbles(res, f)
    bubbles = [b for b in bubbles if b["bytes"] > 0]
    bubbles.sort(key=lambda b: -b["bytes"])
    if len(bubbles) > MAX_BUBBLES:
        rest = bubbles[MAX_BUBBLES - 1:]
        bubbles = bubbles[:MAX_BUBBLES - 1]
        size = sum(b["bytes"] for b in rest)
        flagged = int(sum(b["bytes"] * b["share"] for b in rest))
        bubbles.append(_bubble("more:", f"{len(rest)} smaller", size, flagged, False, f"{len(rest)} folders"))
    return {"bubbles": bubbles, "crumbs": crumbs, "scope": scope}


def _folder_bubbles(res: ScanResult, f: Folder) -> list[dict[str, Any]]:
    out = []
    kids_size = kids_flag = 0
    for c in f.children:
        child = res.folder(c)
        if child is None:
            continue
        kids_size += child.size
        kids_flag += child.flagged
        out.append(_bubble(child.path, os.path.basename(child.path), child.size, child.flagged,
                           bool(child.children), child.path))
    direct = f.size - kids_size
    if direct > 0:
        out.append(_bubble("files:" + f.path, "Files here", direct, max(0, f.flagged - kids_flag), False, f.path))
    return out


def in_scope(path: str, scope: list[str] | None) -> bool:
    return scope is None or any(_inside(path, s) for s in scope)


# ----------------------------------------------------------------------------- text
def size_text(n: int) -> str:
    """"0 B", "812 KB", "4.2 GB" (1024-based, one decimal from GB up when under 100)."""
    n = int(n)
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n_f = n / 1024
        if n_f < 1024 or unit == "TB":
            return f"{n_f:.1f} {unit}" if unit in ("GB", "TB") and n_f < 100 else f"{round(n_f)} {unit}"
        n = n_f  # type: ignore[assignment]
    return f"{n} B"  # pragma: no cover


def age_text(mtime: float, now: float | None = None) -> str:
    """"14 months", "3 years" since ``mtime``."""
    months = int(((now if now is not None else time.time()) - mtime) // MONTH_S)
    if months >= 24:
        return f"{months // 12} years"
    return f"{months} month" + ("" if months == 1 else "s")
