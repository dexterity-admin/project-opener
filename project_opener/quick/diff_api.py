"""``app.diff``: the visual revision diff for QML (route ``diff``, ``qml/pages/DiffPage.qml``).

Two files in (dropped on the page, chosen with the file dialog, or "Compare with…" on an item), the
report of ``core.revdiff`` out.  The comparison runs on the pool; the page shows progress, then the
result.  Which file is the older revision is decided by one stated rule, the modified date (the older
on the left), and Swap turns it round; nothing else is inferred.

Registered on the facade by one class-body line (``from project_opener.quick.diff_api import diff``),
created on first use.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from project_opener.core import revdiff
from project_opener.quick.base import ApiBase, ro

log = logging.getLogger(__name__)

FILTERS = {
    "pdf": "PDF drawings (*.pdf)",
    "xlsx": "Excel workbooks (*.xlsx *.xlsm)",
    "docx": "Word documents (*.docx *.docm)",
}
ALL_FILTER = "Drawings and documents (*.pdf *.xlsx *.xlsm *.docx *.docm)"


def out_dir() -> Path:
    """Where overlays and cached results go: the temp folder (renders are scratch, never workspace data)."""
    return Path(tempfile.gettempdir()) / "ProjectOpener" / "revdiff"


def _local(path_or_url: str) -> str:
    s = str(path_or_url or "").strip()
    if s.startswith("file:"):
        s = QUrl(s).toLocalFile()
    return os.path.normpath(s) if s else ""


def _mtime(p: str) -> float:
    try:
        return os.path.getmtime(p)
    except OSError:
        return 0.0


class DiffApi(ApiBase):
    changed = Signal()
    progressChanged = Signal()

    def __init__(self, app: Any):
        super().__init__(app)
        self._a = ""
        self._b = ""
        self._state = "idle"               # idle | busy | done | error
        self._error = ""
        self._result: dict[str, Any] = {}
        self._progress = 0.0
        self._progress_text = ""
        self._run = 0                      # a newer comparison makes an older one's answer stale

    fileA = ro(str, "_a", changed)
    fileB = ro(str, "_b", changed)
    state = ro(str, "_state", changed)
    error = ro(str, "_error", changed)
    result = ro("QVariantMap", "_result", changed)
    progress = ro(float, "_progress", progressChanged)
    progressText = ro(str, "_progress_text", progressChanged)

    @Property(str, notify=changed)
    def nameA(self) -> str:  # noqa: N802
        return Path(self._a).name if self._a else ""

    @Property(str, notify=changed)
    def nameB(self) -> str:  # noqa: N802
        return Path(self._b).name if self._b else ""

    @Property(str, notify=changed)
    def folderA(self) -> str:  # noqa: N802
        return str(Path(self._a).parent) if self._a else ""

    @Property(str, notify=changed)
    def folderB(self) -> str:  # noqa: N802
        return str(Path(self._b).parent) if self._b else ""

    @Property("QVariantMap", constant=True)
    def colours(self) -> dict[str, str]:
        """The overlay's own colours, for the legend and the region marks (the drawing is always on paper)."""
        hexa = lambda c: "#{:02X}{:02X}{:02X}".format(*c)  # noqa: E731
        return {"added": hexa(revdiff.ADDED), "removed": hexa(revdiff.REMOVED), "unchanged": hexa(revdiff.UNCHANGED)}

    # ------------------------------------------------------------------------------------------ slots
    @Slot(str, result=bool)
    def supported(self, path: str) -> bool:
        return revdiff.supported(_local(path))

    @Slot(str, str)
    def compare(self, a: str, b: str) -> None:
        """Compare ``a`` (older) with ``b`` (newer), as given."""
        a, b = _local(a), _local(b)
        if (a, b) == (self._a, self._b) and self._state in ("busy", "done"):
            return
        self._a, self._b = a, b
        self._start()

    @Slot("QStringList")
    def dropped(self, urls: list[str]) -> None:
        """Files dropped on the page: two (or more: the first two) are compared, older modified date first;
        one fills the empty side, else replaces the newer."""
        paths = [p for p in (_local(u) for u in urls) if p]
        if not paths:
            return
        if len(paths) >= 2:
            a, b = sorted(paths[:2], key=lambda p: (_mtime(p), p.lower()))
            self.compare(a, b)
            return
        self.setFile("" if not self._a else "b", paths[0])

    @Slot(str, str)
    def setFile(self, side: str, path: str) -> None:  # noqa: N802
        """Put one file on a side ("a" older, "b" newer, "" = the empty one); compares once both are set."""
        path = _local(path)
        if side == "":
            side = "a" if not self._a else "b"
        if side == "a":
            self._a = path
        else:
            self._b = path
        if self._a and self._b:
            self._start()
        else:
            self._state, self._error, self._result = "idle", "", {}
            self.changed.emit()

    @Slot(str)
    def browse(self, side: str) -> None:
        """The file dialog for one side, filtered to the kind of the other side when it is set."""
        other = self._b if side == "a" else self._a
        kind = revdiff.kind_of(other) if other else ""
        start = str(Path(other).parent) if other else ""
        path = self._ask("Choose the older revision" if side == "a" else "Choose the newer revision",
                         start, FILTERS.get(kind, ALL_FILTER))
        if path:
            self.setFile(side, path)

    @Slot()
    def browsePair(self) -> None:  # noqa: N802
        from PySide6.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(None, "Choose two revisions", "", ALL_FILTER)
        if paths:
            self.dropped(list(paths))

    @Slot(str)
    def compareWith(self, path: str) -> None:  # noqa: N802
        """"Compare with…" on an item: ask for the other revision (same kind, starting in the item's folder),
        then show the diff, the older modified date first."""
        path = _local(path)
        if not revdiff.supported(path):
            self.app.toast.emit("Cannot compare this file", "PDF, .xlsx and .docx files only.", "warning")
            return
        other = self._ask("Compare with which revision?", str(Path(path).parent),
                          FILTERS[revdiff.kind_of(path)])
        if other:
            self.openPair(path, other)

    @Slot(str, str)
    def openPair(self, p: str, q: str) -> None:  # noqa: N802
        """Go to the diff page comparing two files, the older modified date first."""
        a, b = sorted([_local(p), _local(q)], key=lambda x: (_mtime(x), x.lower()))
        self.app.ui.go("diff", {"a": a, "b": b})

    @Slot()
    def swap(self) -> None:
        self._a, self._b = self._b, self._a
        if self._a and self._b:
            self._start()
        else:
            self.changed.emit()

    @Slot()
    def clear(self) -> None:
        self._run += 1
        self._a = self._b = self._error = ""
        self._state, self._result = "idle", {}
        self.changed.emit()

    @Slot(str)
    def openFile(self, path: str) -> None:  # noqa: N802
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    @Slot(str)
    def showInFolder(self, path: str) -> None:  # noqa: N802
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    # ------------------------------------------------------------------------------------------ work
    def _ask(self, title: str, start: str, filters: str) -> str:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(None, title, start, filters)
        return path or ""

    def _start(self) -> None:
        self._run += 1
        run = self._run
        a, b = self._a, self._b
        try:
            revdiff.check_pair(a, b)
        except revdiff.DiffError as exc:
            self._state, self._error, self._result = "error", str(exc), {}
            self.changed.emit()
            return
        self._state, self._error, self._result = "busy", "", {}
        self._set_progress(0.0, "Reading both revisions")
        self.changed.emit()

        def progress(i: int, n: int) -> None:
            text = f"Comparing page {min(i + 1, n)} of {n}" if i < n else "Listing the changes"
            self.app.run_on_gui(lambda: self._set_progress(i / n if n else 1.0, text) if run == self._run else None)

        def work() -> dict[str, Any]:
            return revdiff.compare(a, b, out_dir(), progress)

        def done(res: dict[str, Any]) -> None:
            if run != self._run:
                return
            for p in res.get("pages", []):
                p["overlayUrl"] = QUrl.fromLocalFile(p["overlay"]).toString() if p.get("overlay") else ""
                p["thumbUrl"] = QUrl.fromLocalFile(p["thumb"]).toString() if p.get("thumb") else ""
            self._state, self._result = "done", res
            self._set_progress(1.0, "")
            self.changed.emit()

        def fail(exc: BaseException) -> None:
            if run != self._run:
                return
            if not isinstance(exc, revdiff.DiffError):
                log.error("revision diff failed: %r", exc)
            self._state, self._result = "error", {}
            self._error = str(exc) if isinstance(exc, revdiff.DiffError) else f"The comparison stopped: {exc}"
            self.changed.emit()

        self.app.run_async(work, done, fail)

    def _set_progress(self, value: float, text: str) -> None:
        self._progress, self._progress_text = value, text
        self.progressChanged.emit()


def diff_property() -> Property:
    """``app.diff`` on the facade, created on first use (so registering it is one line in facade.py)."""
    def getter(self: Any) -> DiffApi:
        api = getattr(self, "_diff_api", None)
        if api is None:
            api = self._diff_api = DiffApi(self)
        return api
    return Property(QObject, getter, constant=True)


diff = diff_property()       # imported into AppFacade's class body: ``from project_opener.quick.diff_api import diff``
