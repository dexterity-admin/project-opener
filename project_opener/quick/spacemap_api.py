"""``app.spacemap``: the Space map (core/spacemap.py) for QML.  Report only: nothing is deleted or moved.

Registered on the facade by one class-body line (``from ...spacemap_api import spacemap``): ``spacemap`` is a
constant ``QObject`` property that builds this API on first read, as a child of the facade.  It needs no
``start``; it stops its scan when the application quits.

Flow: the page calls ``load()`` (the last scan from the cache, on the pool) and offers Scan.  ``scan()`` reads
the hub's project cards on the pool (published projects and activities; their folder items, resolved on
this PC), then runs one ``Scanner`` thread at low priority.  Progress comes back through ``run_on_gui`` at
most every 0.3 s: the card bubbles grow while the folders are listed.  The cache is
``<hub>/spacemap/scan.json`` (shared, so one PC's scan serves the office) or the data folder without a hub.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QCoreApplication, QObject, Signal, Slot

from project_opener import constants as C
from project_opener.core import spacemap as S
from project_opener.quick.base import ApiBase
from project_opener.quick.listmodel import DictListModel
from project_opener.ui import text as T

log = logging.getLogger(__name__)

BUBBLE_ROLES = ("bubbleKey", "label", "bytes", "sizeText", "share", "drillable", "detail")
DUP_ROLES = ("groupKey", "name", "countText", "sizeText", "wastedText", "paths", "folders")
STALE_ROLES = ("path", "name", "folder", "sizeText", "ageText")
SKIP_ROLES = ("skipKey", "path", "reason")
LIST_ROWS = 60
STALE_CHOICES = (6, 12, 24, 36)


def card_folders(hub: Any, resolve: Any) -> list[tuple[str, list[str]]]:
    """(card title, resolved folder paths) for every published project and activity on the hub.  Network
    reads: call on the pool."""
    cards: list[tuple[str, list[str]]] = []
    for pub in hub.published():
        proj = pub.project
        cards.append((proj.title, [resolve(i.path) for i in proj.items if i.kind == "folder" and i.path]))
    for pa in hub.published_activities():
        act = pa.activity
        spine = (pa.projects[0].get("job_number") or pa.projects[0].get("title")) if pa.projects else ""
        title = f"{spine} · {act.name}" if spine else act.name
        cards.append((title, [resolve(i.path) for i in act.items if i.kind == "folder" and i.path]))
    return cards


class SpaceMapApi(ApiBase):
    stateChanged = Signal()
    resultChanged = Signal()
    navChanged = Signal()
    progressChanged = Signal()

    def __init__(self, app: Any):
        super().__init__(app)
        self._bubbles = DictListModel(BUBBLE_ROLES, key="bubbleKey", parent=self)
        self._dups = DictListModel(DUP_ROLES, key="groupKey", parent=self)
        self._stale = DictListModel(STALE_ROLES, key="path", parent=self)
        self._skipped = DictListModel(SKIP_ROLES, key="skipKey", parent=self)
        self._state = "idle"              # idle | loading | scanning | stopping | done | error
        self._error = ""
        self._result: S.ScanResult | None = None
        self._live: dict[str, int] = {}
        self._live_cards: dict[str, list[str]] = {}
        self._nav: list[str] = []
        self._crumbs: list[dict[str, Any]] = [{"label": "All projects", "depth": 0}]
        self._progress = ""
        self._scanner: S.Scanner | None = None
        self._cache: Path | None = None
        self._loaded = False
        self._dup_count = 0
        self._stale_count = 0
        app_ = QCoreApplication.instance()
        if app_ is not None:
            app_.aboutToQuit.connect(self.shutdown)

    # ------------------------------------------------------------- models
    @Property(QObject, constant=True)
    def bubbles(self) -> DictListModel:
        return self._bubbles

    @Property(QObject, constant=True)
    def duplicates(self) -> DictListModel:
        return self._dups

    @Property(QObject, constant=True)
    def stale(self) -> DictListModel:
        return self._stale

    @Property(QObject, constant=True)
    def skipped(self) -> DictListModel:
        return self._skipped

    # --------------------------------------------------------- properties
    @Property(str, notify=stateChanged)
    def state(self) -> str:
        return self._state

    @Property(bool, notify=stateChanged)
    def scanning(self) -> bool:
        return self._state in ("scanning", "stopping")

    @Property(str, notify=stateChanged)
    def error(self) -> str:
        return self._error

    @Property(bool, notify=resultChanged)
    def hasResult(self) -> bool:  # noqa: N802
        return self._result is not None

    @Property(str, notify=progressChanged)
    def progressText(self) -> str:  # noqa: N802
        return self._progress

    @Property(str, notify=resultChanged)
    def summary(self) -> str:
        """The page's finding line: "412 GB in 14 folders on 9 cards · scanned 2 h ago"."""
        r = self._result
        if r is None:
            return "" if self._state == "loading" else "Not scanned yet."
        when = T.when_text(r.scanned_at)
        scanned = sum(1 for root in r.roots if r.folder(root.path) is not None)
        head = f"{S.size_text(r.size)} in {T.plural(scanned, 'folder')} on {T.plural(len(r.cards), 'card')}"
        if scanned < len(r.roots):
            head = T.join_facts(head, f"{len(r.roots) - scanned} not reachable")
        tail = f"scanned {when}" if when else ""
        if not r.complete:
            tail = T.join_facts(tail, "stopped before the end")
        return T.join_facts(head, tail)

    @Property("QVariantMap", notify=resultChanged)
    def stats(self) -> dict[str, Any]:
        r = self._result
        if r is None:
            return {"size": "", "files": "", "dupWasted": "", "dupGroups": "", "stale": "", "staleCount": "",
                    "skipped": 0}
        return {"size": S.size_text(r.size), "files": T.plural(r.files, "file"),
                "dupWasted": S.size_text(r.dup_wasted), "dupGroups": T.plural(len(r.duplicates), "group"),
                "stale": S.size_text(r.stale_bytes), "staleCount": T.plural(r.stale_count, "file"),
                "skipped": len(r.skipped)}

    @Property(int, notify=resultChanged)
    def duplicateCount(self) -> int:  # noqa: N802
        return self._dup_count

    @Property(int, notify=resultChanged)
    def staleCount(self) -> int:  # noqa: N802
        return self._stale_count

    @Property("QVariantList", notify=navChanged)
    def crumbs(self) -> list[dict[str, Any]]:
        return self._crumbs

    @Property(int, notify=navChanged)
    def depth(self) -> int:
        return len(self._nav)

    @Property(int, notify=resultChanged)
    def staleMonths(self) -> int:  # noqa: N802
        return int(getattr(self.app.ctx.settings, "spacemap_stale_months", 12) or 12)

    @Property(int, notify=resultChanged)
    def scannedMonths(self) -> int:  # noqa: N802
        """The stale threshold the shown scan used (the setting may have changed since)."""
        return self._result.stale_months if self._result is not None else self.staleMonths

    @Property("QVariantList", constant=True)
    def staleChoices(self) -> list[str]:  # noqa: N802
        return [str(m) for m in STALE_CHOICES]

    # -------------------------------------------------------------- slots
    @Slot()
    def load(self) -> None:
        """The last scan from the cache (once per run; the page calls it on arrival)."""
        if self._loaded or self.scanning:
            return
        self._loaded = True
        self._set_state("loading")
        hub = self.app.ctx.hub

        def work() -> tuple[Path, S.ScanResult | None]:
            path = self._cache_path(hub)
            return path, S.load_cached(path)

        def done(res: tuple[Path, S.ScanResult | None]) -> None:
            self._cache, cached = res
            if self._state == "loading":
                self._result = cached
                self._set_state("done" if cached is not None else "idle")
                self._refresh()

        self.app.run_async(work, done, lambda exc: self._fail(f"Could not read the last scan: {exc}"))

    @Slot()
    def scan(self) -> None:
        if self.scanning:
            return
        self._set_state("scanning")
        self._set_progress("Reading the project cards on the Team Hub…")
        ctx = self.app.ctx
        months = self.staleMonths

        def work() -> tuple[Path, list[S.ScanRoot], dict[str, list[str]]]:
            hub = ctx.hub
            if not hub.configured:
                raise RuntimeError("No Team Hub folder set. Choose a shared folder in Settings.")
            if not hub.reachable():
                raise RuntimeError(f"Hub folder not reachable: {hub.root}")

            def resolve(p: str) -> str:
                try:
                    return ctx.resolver.resolve(p).resolved or p
                except Exception:  # noqa: BLE001
                    return p
            roots, by_card = S.roots_from_cards(card_folders(hub, resolve))
            return self._cache_path(hub), roots, by_card

        def ready(res: tuple[Path, list[S.ScanRoot], dict[str, list[str]]]) -> None:
            self._cache, roots, by_card = res
            if self._state != "scanning":
                return                          # stopped while the cards were read
            if not roots:
                self._fail("No project card on the Team Hub names a folder yet.")
                return
            self._live, self._live_cards = {}, by_card
            sc = S.Scanner(roots, months, self._cache, cards=by_card,
                           on_progress=lambda p: self.app.run_on_gui(lambda: self._on_progress(sc, p)),
                           on_done=lambda r: self.app.run_on_gui(lambda: self._on_done(sc, r)),
                           on_error=lambda e: self.app.run_on_gui(lambda: self._on_error(sc, e)))
            self._scanner = sc
            sc.start()

        self.app.run_async(work, ready, lambda exc: self._fail(str(exc)))

    @Slot()
    def cancel(self) -> None:
        if self._scanner is not None and self._state == "scanning":
            self._scanner.cancel()
            self._set_state("stopping")
            self._set_progress("Stopping…")
        elif self._state == "scanning":                # still reading the cards
            self._set_state("done" if self._result is not None else "idle")
            self._set_progress("")

    @Slot(str)
    def drill(self, key: str) -> None:
        if not key or key.startswith(("files:", "more:")):
            return
        self._nav.append(key)
        self._refresh()

    @Slot(int)
    def goTo(self, depth: int) -> None:  # noqa: N802
        """Back to a breadcrumb (0 = all projects)."""
        self._nav = self._nav[:max(0, depth)]
        self._refresh()

    @Slot(str)
    def showInExplorer(self, path: str) -> None:  # noqa: N802
        """Explorer at the file (selected) or folder.  Off the GUI thread: the share may be slow."""
        if not path:
            return
        from project_opener.core.winutil import reveal_in_explorer
        self.app.run_async(lambda: reveal_in_explorer(path), None,
                           lambda exc: self.app.toast.emit("Could not open Explorer", str(exc), "error"))

    @Slot(str)
    def setStaleMonths(self, months: str) -> None:  # noqa: N802
        try:
            n = int(months)
        except (TypeError, ValueError):
            return
        s = self.app.ctx.settings
        if n == self.staleMonths or n < 1:
            return
        s.spacemap_stale_months = n
        try:
            s.save()
        except OSError:
            log.warning("could not save the stale setting")
        self.resultChanged.emit()

    # ------------------------------------------------------------- internals
    def _cache_path(self, hub: Any) -> Path:
        env = os.environ.get("PO_SPACEMAP_CACHE", "")
        if env:
            return Path(env)
        sub = hub.sub("spacemap") if hub is not None and hub.configured else None
        if sub is not None:
            try:
                if hub.reachable():
                    return sub / "scan.json"
            except OSError:
                pass
        return Path(C.data_dir()) / "spacemap.json"

    def _set_state(self, st: str) -> None:
        self.set_("_state", st, self.stateChanged)

    def _set_progress(self, text: str) -> None:
        self.set_("_progress", text, self.progressChanged)

    def _fail(self, msg: str) -> None:
        self._error = msg
        self._scanner = None
        self._set_progress("")
        self._state = "error"
        self.stateChanged.emit()

    def _on_progress(self, sc: S.Scanner, p: S.Progress) -> None:
        if sc is not self._scanner:
            return
        if p.phase == "listing":
            self._set_progress(f"Listing · {T.plural(p.folders, 'folder')} · {T.plural(p.files, 'file')} · "
                               f"{S.size_text(p.size)}")
        elif p.phase == "comparing":
            self._set_progress(f"Comparing files of the same size · {p.compared} of {p.candidates}")
        else:
            self._set_progress("Saving the scan…")
        self._live = p.root_sizes
        if self._result is None and not self._nav:     # first scan: the card bubbles grow as folders are listed
            live = S.ScanResult(cards=self._live_cards)
            self._bubbles.sync(S.level(live, [], self._live)["bubbles"])

    def _on_done(self, sc: S.Scanner, res: S.ScanResult) -> None:
        if sc is not self._scanner:
            return
        self._scanner = None
        self._result = res
        self._error = ""
        self._set_progress("")
        self._nav = [k for k in self._nav if k.startswith("card:") and k[5:] in res.cards or res.folder(k)]
        self._set_state("done")
        self._refresh()

    def _on_error(self, sc: S.Scanner, exc: BaseException) -> None:
        if sc is self._scanner:
            self._fail(f"The scan stopped: {exc}")

    def _refresh(self) -> None:
        r = self._result or S.ScanResult()
        lv = S.level(r, self._nav)
        self._bubbles.sync(lv["bubbles"])
        self._crumbs = lv["crumbs"]
        scope = lv["scope"]
        now = time.time()
        dups = [g for g in r.duplicates if any(S.in_scope(p, scope) for p in g.get("paths", []))]
        stale = [s for s in r.stale if S.in_scope(str(s.get("path", "")), scope)]
        self._dup_count, self._stale_count = len(dups), len(stale)
        self._dups.sync([{
            "groupKey": f"{g['size']}|{g['hash']}|{g['paths'][0]}",
            "name": os.path.basename(g["paths"][0]),
            "countText": T.plural(len(g["paths"]), "copy", "copies"),
            "sizeText": f"{S.size_text(g['size'])} each",
            "wastedText": f"{S.size_text(g['wasted'])} in extra copies",
            "paths": list(g["paths"]),
            "folders": [os.path.dirname(p) for p in g["paths"]],
        } for g in dups[:LIST_ROWS]])
        self._stale.sync([{
            "path": s["path"], "name": os.path.basename(s["path"]), "folder": os.path.dirname(s["path"]),
            "sizeText": S.size_text(int(s.get("size", 0))), "ageText": S.age_text(float(s.get("mtime", now)), now),
        } for s in stale[:LIST_ROWS]])
        self._skipped.reset([{"skipKey": str(i), "path": s.get("path", ""), "reason": s.get("reason", "")}
                             for i, s in enumerate(r.skipped[:LIST_ROWS])])
        self.navChanged.emit()
        self.resultChanged.emit()

    def shutdown(self) -> None:
        sc, self._scanner = self._scanner, None
        if sc is not None:
            sc.cancel()
            sc.join(2.0)


def _get(facade: Any) -> SpaceMapApi:
    api = getattr(facade, "_spacemap_api", None)
    if api is None:
        api = SpaceMapApi(facade)
        facade._spacemap_api = api
    return api


# The facade registers the API with one line in its class body:
#     from project_opener.quick.spacemap_api import spacemap  # app.spacemap
spacemap = Property(QObject, _get, constant=True)
