"""Visual revision diff (4.0 signature feature; docs/V4-PLUS-BRIEF.md "Visual revision diff").

Two revisions of one document in, a report of what changed out.  v1 covers:

* **PDF drawings**: both revisions rendered page by page (QtPdf), the newer one aligned onto the older
  by a whole-pixel shift (a re-plot moves the sheet a little), then a red/green overlay (removed red,
  added green, unchanged ink grey) and per page the changed regions with the words that changed
  inside each.
* **Excel .xlsx/.xlsm**: cell-level changes per sheet (added, removed, changed, old -> new).
* **Word .docx**: paragraph changes in the body, tables, headers and footers, with the words inside.

Deterministic plumbing only: it reports what differs between the two files and never decides whether a
change is right, intended or compliant.  Office files are read with the stdlib (``zipfile`` +
``xml.etree``).  PDFs are rendered and their words placed with QtPdf, which ships with PySide6 (already a
dependency, LGPL like the rest of Qt), so no new package: PyMuPDF would add ~100 MB and is AGPL, which
does not sit with this proprietary app.  Pixel work uses big-integer bit operations over 0/1 byte masks
and QImage, so numpy is not needed.  The QtPdf calls run in a worker thread with no window involved.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import zipfile
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

ENGINE_VERSION = "1"                       # bump when the output of a comparison changes (cache key)

PDF_EXT = {".pdf"}
XLSX_EXT = {".xlsx", ".xlsm"}
DOCX_EXT = {".docx", ".docm"}
OLD_OFFICE = {".xls": "Excel 97-2003 (.xls)", ".doc": "Word 97-2003 (.doc)"}

# PDF rendering
MAX_SIDE = 3000                            # longest side of a page render, px (an A1 sheet at ~90 dpi)
MAX_SCALE = 150 / 72                       # never above 150 dpi (an A4 page)
ALIGN_SIDE = 800                           # longest side of the alignment render, px
ALIGN_RANGE = 0.015                        # largest shift tried, as a fraction of the longest side
INK = 200                                  # a grey value below this is ink (0 black .. 255 paper)
CELL_SHIFT = 3                             # region grid: cells of 2**3 = 8 px
MIN_REGION_PX = 4                          # a region with fewer changed pixels is reported as a speck
MAX_REGIONS = 200                          # per page; the count beyond is reported
THUMB_W = 240                              # page-strip thumbnail width, px

# overlay colours (RGB): paper, added, removed, unchanged ink.  Added and removed are the light theme's
# success and danger (ui/theme.py), so the legend, the pills and the drawing say one colour each.
PAPER = (255, 255, 255)
ADDED = (31, 122, 77)
REMOVED = (180, 35, 24)
UNCHANGED = (150, 160, 163)

MAX_ROWS = 5000                            # change rows per sheet / document sent to the UI

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class DiffError(Exception):
    """A comparison that cannot be made; the message names the problem and the way out."""


Progress = Callable[[int, int], None]


# ------------------------------------------------------------------------------------------------ dispatch
def kind_of(path: str | Path) -> str:
    """"pdf" | "xlsx" | "docx" | "" for a path, by its extension."""
    ext = Path(path).suffix.lower()
    if ext in PDF_EXT:
        return "pdf"
    if ext in XLSX_EXT:
        return "xlsx"
    if ext in DOCX_EXT:
        return "docx"
    return ""


def supported(path: str | Path) -> bool:
    return kind_of(path) != ""


def check_pair(a: str | Path, b: str | Path) -> str:
    """The kind both files share; DiffError when they cannot be compared."""
    for p in (a, b):
        ext = Path(p).suffix.lower()
        if ext in OLD_OFFICE:
            raise DiffError(f"{Path(p).name} is {OLD_OFFICE[ext]}. Save it as "
                            f"{'.xlsx' if ext == '.xls' else '.docx'} and compare again.")
        if not kind_of(p):
            raise DiffError(f"{Path(p).name} cannot be compared: PDF, .xlsx and .docx files only.")
        if not Path(p).is_file():
            raise DiffError(f"{p} was not found.")
    ka, kb = kind_of(a), kind_of(b)
    if ka != kb:
        raise DiffError(f"{Path(a).name} and {Path(b).name} are different kinds of file.")
    return ka


def cache_key(a: str | Path, b: str | Path) -> str:
    """A folder name for one comparison: both paths, sizes and modified times, and the engine version."""
    parts = [ENGINE_VERSION]
    for p in (a, b):
        st = Path(p).stat()
        parts += [str(Path(p).resolve()).lower(), str(st.st_size), str(st.st_mtime_ns)]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def compare(a: str | Path, b: str | Path, out_dir: str | Path, progress: Progress | None = None) -> dict[str, Any]:
    """Compare revision ``a`` (older) with ``b`` (newer).  PDF overlays are written under ``out_dir``.

    The result is plain JSON-able data (the UI's model); it is cached as ``result.json`` beside the overlays
    and reused while neither file changes.
    """
    kind = check_pair(a, b)
    folder = Path(out_dir) / cache_key(a, b)
    cached = folder / "result.json"
    if cached.is_file():
        try:
            with open(cached, encoding="utf-8") as f:
                res = json.load(f)
            if all(Path(p["overlay"]).is_file() for p in res.get("pages", []) if p.get("overlay")):
                return res
        except (OSError, ValueError, KeyError, TypeError):
            pass
    folder.mkdir(parents=True, exist_ok=True)
    if kind == "pdf":
        res = compare_pdf(a, b, folder, progress)
    elif kind == "xlsx":
        res = compare_xlsx(a, b)
    else:
        res = compare_docx(a, b)
    res.update({"kind": kind, "a": str(a), "b": str(b), "nameA": Path(a).name, "nameB": Path(b).name})
    try:
        with open(cached, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False)
    except OSError:
        pass
    return res


def plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word if n == 1 else (many or word + 's')}"


# ------------------------------------------------------------------------------------------------ PDF
_BIN = bytes(1 if i < INK else 0 for i in range(256))


class _Mask:
    """A W x H image of 0/1 bytes, also held as one big integer for whole-image bit operations."""

    __slots__ = ("w", "h", "data")

    def __init__(self, w: int, h: int, data: bytes):
        self.w, self.h, self.data = w, h, data

    def as_int(self) -> int:
        return int.from_bytes(self.data, "big")

    def padded(self, w: int, h: int) -> _Mask:
        if (w, h) == (self.w, self.h):
            return self
        pad_row = bytes(w - self.w)
        rows = [self.data[r * self.w:(r + 1) * self.w] + pad_row for r in range(self.h)]
        rows += [bytes(w)] * (h - self.h)
        return _Mask(w, h, b"".join(rows))

    def shifted(self, dx: int, dy: int) -> _Mask:
        """The image moved by (dx, dy) px, paper filling what is uncovered (nothing wraps round)."""
        if dx == 0 and dy == 0:
            return self
        w, h, d = self.w, self.h, self.data
        if dx:
            if abs(dx) >= w:
                return _Mask(w, h, bytes(w * h))
            z = bytes(abs(dx))
            if dx > 0:
                d = b"".join(z + d[r * w:(r + 1) * w - dx] for r in range(h))
            else:
                d = b"".join(d[r * w - dx:(r + 1) * w] + z for r in range(h))
        if dy:
            if abs(dy) >= h:
                return _Mask(w, h, bytes(w * h))
            if dy > 0:
                d = bytes(w * dy) + d[:w * (h - dy)]
            else:
                d = d[w * -dy:] + bytes(w * -dy)
        return _Mask(w, h, d)


class _Pdf:
    """One PDF opened with QtPdf (part of PySide6, LGPL like the rest of Qt): page sizes in points, page
    renders on white paper, and the words of a page with their boxes."""

    def __init__(self, path: str | Path):
        from PySide6.QtPdf import QPdfDocument
        self.name = Path(path).name
        self.doc = QPdfDocument(None)
        err = self.doc.load(str(path))
        if err == QPdfDocument.Error.IncorrectPassword:
            raise DiffError(f"{self.name} is password-protected.")
        if err != QPdfDocument.Error.None_ or self.doc.status() != QPdfDocument.Status.Ready:
            raise DiffError(f"{self.name} could not be read as a PDF ({err.name.rstrip('_')}).")

    @property
    def pages(self) -> int:
        return self.doc.pageCount()

    def size(self, i: int) -> tuple[float, float]:
        s = self.doc.pagePointSize(i)
        return s.width(), s.height()

    def render(self, i: int, scale: float) -> _Mask:
        """The page at ``scale`` px per point, annotations included (what a viewer shows), as an ink mask."""
        from PySide6.QtCore import QSize, Qt
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtPdf import QPdfDocumentRenderOptions
        w, h = self.size(i)
        size = QSize(max(1, round(w * scale)), max(1, round(h * scale)))
        opts = QPdfDocumentRenderOptions()
        opts.setRenderFlags(QPdfDocumentRenderOptions.RenderFlag.Annotations)
        img = self.doc.render(i, size, opts)
        paper = QImage(size, QImage.Format.Format_RGB32)
        paper.fill(Qt.GlobalColor.white)              # the render is transparent where nothing is drawn
        p = QPainter(paper)
        p.drawImage(0, 0, img)
        p.end()
        gray = paper.convertToFormat(QImage.Format.Format_Grayscale8)
        gw, gh, bpl = gray.width(), gray.height(), gray.bytesPerLine()
        raw = bytes(gray.constBits())
        data = raw[:gw * gh] if bpl == gw else b"".join(raw[r * bpl:r * bpl + gw] for r in range(gh))
        return _Mask(gw, gh, data.translate(_BIN))

    def words(self, i: int, dx_pt: float = 0.0, dy_pt: float = 0.0) -> list[tuple[float, float, str]]:
        """(centre x, centre y, word) in points, moved by the alignment shift."""
        text = self.doc.getAllText(i).text()
        out = []
        for m in re.finditer(r"\S+", text):
            r = self.doc.getSelectionAtIndex(i, m.start(), m.end() - m.start()).boundingRectangle()
            if r.width() > 0 or r.height() > 0:
                out.append((r.center().x() + dx_pt, r.center().y() + dy_pt, m.group()))
        return out

    def close(self) -> None:
        self.doc.close()


def _dilate(x: int, w: int) -> int:
    """Grow 0/1 byte-pixels by one pixel left, right, up and down (row ends may bleed one pixel)."""
    return x | (x << 8) | (x >> 8) | (x << (8 * w)) | (x >> (8 * w))


def _ones(n: int) -> int:
    return int.from_bytes(b"\x01" * n, "big")


def _profile_shift(pa: list[int], pb: list[int], rng: int) -> int:
    """The move of profile b (ink per column, or per row) that best matches profile a."""
    n = len(pa)
    best = (-1, 0)
    for d in sorted(range(-rng, rng + 1), key=lambda v: (abs(v), v)):   # ties go to the smaller move
        score = sum(pa[i] * pb[i - d] for i in range(max(0, d), min(n, n + d)))
        if score > best[0]:
            best = (score, d)
    return best[1]


def _profiles(m: _Mask) -> tuple[list[int], list[int]]:
    d, w = m.data, m.w
    return [sum(d[c::w]) for c in range(w)], [sum(d[r * w:(r + 1) * w]) for r in range(m.h)]


def _overlap(ai_dilated: int, b: _Mask, dx: int, dy: int) -> int:
    return (ai_dilated & b.shifted(dx, dy).as_int()).bit_count()


def _best_around(a: _Mask, b: _Mask, dx: int, dy: int, rng: int) -> tuple[int, int, int]:
    """The (dx, dy) within ``rng`` of a guess that lays most of b's ink on a's; and that ink."""
    ai = _dilate(a.as_int(), a.w)
    best = (-1, dx, dy)
    for ddy in range(-rng, rng + 1):
        for ddx in range(-rng, rng + 1):
            x, y = dx + ddx, dy + ddy
            score = _overlap(ai, b, x, y)
            # ties go to the smaller move: one answer for one input
            if score > best[0] or (score == best[0] and abs(x) + abs(y) < abs(best[1]) + abs(best[2])):
                best = (score, x, y)
    return best[1], best[2], best[0]


def _align(da: _Pdf, db: _Pdf, i: int, scale: float, a: _Mask, b: _Mask) -> tuple[int, int]:
    """Whole-pixel shift (at ``scale``) that lays page b over page a: the ink profiles (per column, per row)
    of a low render give the move, a small 2-D search confirms it, and the full render refines it by a
    pixel.  A shift is kept only when it lays clearly more ink on ink than none (5 %), so a page that
    really changed is not slid about."""
    longest = max(*da.size(i), *db.size(i))
    low = min(scale, ALIGN_SIDE / longest)
    la, lb = da.render(i, low), db.render(i, low)
    w, h = max(la.w, lb.w), max(la.h, lb.h)
    la, lb = la.padded(w, h), lb.padded(w, h)
    rng = max(2, round(ALIGN_RANGE * max(w, h)))
    (ca, ra), (cb, rb) = _profiles(la), _profiles(lb)
    gx, gy = _profile_shift(ca, cb, rng), _profile_shift(ra, rb, rng)
    dx, dy, score = _best_around(la, lb, gx, gy, 1)
    base = _overlap(_dilate(la.as_int(), w), lb, 0, 0)
    if (dx, dy) == (0, 0) or score == 0 or score < base * 1.05:
        return 0, 0
    fx, fy = round(dx * scale / low), round(dy * scale / low)
    fx, fy, _ = _best_around(a, b, fx, fy, 1)
    return fx, fy


def _word_diff(wa: list[str], wb: list[str]) -> tuple[list[str], list[str]]:
    """Words in b and not a (added) and in a and not b (removed), counted, in reading order."""
    ca, cb = Counter(wa), Counter(wb)
    first_a = {s: i for i, s in reversed(list(enumerate(wa)))}
    first_b = {s: i for i, s in reversed(list(enumerate(wb)))}
    removed = sorted((ca - cb).elements(), key=lambda s: (first_a[s], s))
    added = sorted((cb - ca).elements(), key=lambda s: (first_b[s], s))
    return added, removed


_CELL = 1 << CELL_SHIFT


def _cells(mask: int, w: int, h: int) -> list[int]:
    """Changed pixels per 8 x 8 cell (row-major, w and h multiples of 8): rows, then columns, summed as
    big integers (each byte counts at most 64, so nothing carries into the next)."""
    n = w * h
    full = (1 << (8 * n)) - 1
    v = mask
    for k in range(1, _CELL):
        v += (mask << (8 * w * k)) & full            # row r collects rows r .. r+7
    s = v
    for k in range(1, _CELL):
        s += (v << (8 * k)) & full                   # column c collects columns c .. c+7
    data = s.to_bytes(n, "big")
    out: list[int] = []
    for r in range(0, h, _CELL):
        out.extend(data[r * w:(r + 1) * w:_CELL])
    return out


def _regions(added: int, removed: int, w: int, h: int) -> tuple[list[dict[str, Any]], int]:
    """Changed regions: 8 px cells that hold a change, joined when they lie within a gap of each other."""
    cw, ch = w // _CELL, h // _CELL
    ca, cr = _cells(added, w, h), _cells(removed, w, h)
    hot = [i for i in range(cw * ch) if ca[i] or cr[i]]
    if not hot:
        return [], 0
    gap = max(2, round(min(cw, ch) / 60))
    hotset = set(hot)
    seen: set[int] = set()
    found = []
    for start in hot:
        if start in seen:
            continue
        seen.add(start)
        stack, comp = [start], []
        while stack:
            i = stack.pop()
            comp.append(i)
            x0, y0 = i % cw, i // cw
            for yy in range(max(0, y0 - gap), min(ch, y0 + gap + 1)):
                for xx in range(max(0, x0 - gap), min(cw, x0 + gap + 1)):
                    j = yy * cw + xx
                    if j in hotset and j not in seen:
                        seen.add(j)
                        stack.append(j)
        xs = [i % cw for i in comp]
        ys = [i // cw for i in comp]
        found.append((min(ys), min(xs), max(xs), max(ys), sum(ca[i] for i in comp), sum(cr[i] for i in comp)))
    found.sort()
    out, specks = [], 0
    for y0, x0, x1, y1, add_px, rem_px in found:
        if add_px + rem_px < MIN_REGION_PX:
            specks += 1
            continue
        out.append({
            "x": x0 / cw, "y": y0 / ch, "w": (x1 - x0 + 1) / cw, "h": (y1 - y0 + 1) / ch,
            "addedPx": add_px, "removedPx": rem_px,
            "kind": "both" if add_px and rem_px else "added" if add_px else "removed",
        })
    return out, specks


def _overlay(path: Path, w: int, h: int, added: int, removed: int, ink: int) -> None:
    """removed red, added green, unchanged ink grey, paper white; one PNG."""
    from PySide6.QtGui import QImage
    n = w * h
    code = (removed << 1) | added | ink | (ink << 1)          # 0 paper, 1 added, 2 removed, 3 ink
    codes = code.to_bytes(n, "big")
    colours = (PAPER, ADDED, REMOVED, UNCHANGED)
    rgb = bytearray(3 * n)
    for ch in range(3):
        table = bytes(colours[i][ch] if i < 4 else 0 for i in range(256))
        rgb[ch::3] = codes.translate(table)
    from PySide6.QtCore import Qt
    img = QImage(bytes(rgb), w, h, 3 * w, QImage.Format.Format_RGB888).copy()
    thumb = img.scaledToWidth(THUMB_W, Qt.TransformationMode.SmoothTransformation)
    if not img.save(str(path), "PNG") or not thumb.save(str(_thumb_path(path)), "PNG"):
        raise DiffError(f"The overlay could not be written to {path.parent}.")


def _thumb_path(overlay: Path) -> Path:
    return overlay.with_name(overlay.stem + "-thumb.png")


def _mm(pt: float) -> str:
    return f"{pt * 25.4 / 72:.0f}"


def compare_pdf(a: str | Path, b: str | Path, folder: Path, progress: Progress | None = None) -> dict[str, Any]:
    da = _Pdf(a)
    try:
        db = _Pdf(b)
    except DiffError:
        da.close()
        raise
    try:
        n = max(da.pages, db.pages)
        pages = []
        for i in range(n):
            if progress:
                progress(i, n)
            pages.append(_compare_page(i, da if i < da.pages else None, db if i < db.pages else None, folder))
        if progress:
            progress(n, n)
    finally:
        da.close()
        db.close()
    changed = [p for p in pages if p["status"] != "same"]
    regions = sum(len(p["regions"]) for p in pages)
    facts = [f"{len(changed)} of {plural(n, 'page')} changed"]
    if regions:
        facts.append(plural(regions, "region"))
    added_pages = sum(p["status"] == "added" for p in pages)
    removed_pages = sum(p["status"] == "removed" for p in pages)
    if added_pages:
        facts.append(f"{plural(added_pages, 'page')} added")
    if removed_pages:
        facts.append(f"{plural(removed_pages, 'page')} removed")
    return {"summary": " · ".join(facts), "pages": pages, "pageCount": n, "changedPages": len(changed),
            "regionCount": regions}


def _compare_page(i: int, da: _Pdf | None, db: _Pdf | None, folder: Path) -> dict[str, Any]:
    ref = da if da is not None else db
    assert ref is not None
    sa = da.size(i) if da is not None else None
    sb = db.size(i) if db is not None else None
    longest = max(*(sa or ()), *(sb or ()))
    scale = min(MAX_SCALE, MAX_SIDE / longest)
    overlay = folder / f"page-{i + 1:03d}.png"
    notes: list[str] = []
    dx = dy = 0

    def fit(m: _Mask, w: int, h: int) -> _Mask:
        return m.padded(w, h)

    if da is not None and db is not None:
        ma, mb = da.render(i, scale), db.render(i, scale)
        if abs(sa[0] - sb[0]) > 1 or abs(sa[1] - sb[1]) > 1:
            notes.append(f"Sheet size changed: {_mm(sa[0])} × {_mm(sa[1])} mm → {_mm(sb[0])} × {_mm(sb[1])} mm")
        w, h = -(-max(ma.w, mb.w) // _CELL) * _CELL, -(-max(ma.h, mb.h) // _CELL) * _CELL
        ma, mb = fit(ma, w, h), fit(mb, w, h)
        dx, dy = _align(da, db, i, scale, ma, mb)
        if (dx, dy) != (0, 0):
            mb = mb.shifted(dx, dy)
        ai, bi = ma.as_int(), mb.as_int()
    else:
        m = ref.render(i, scale)
        w, h = -(-m.w // _CELL) * _CELL, -(-m.h // _CELL) * _CELL
        m = fit(m, w, h)
        ai = m.as_int() if da is not None else 0
        bi = m.as_int() if db is not None else 0
    ones = _ones(w * h)
    removed = ai & (ones ^ _dilate(bi, w))
    added = bi & (ones ^ _dilate(ai, w))
    ink = (ai | bi) & (ones ^ (removed | added))
    _overlay(overlay, w, h, added, removed, ink)
    regions, specks = _regions(added, removed, w, h)
    dx_pt, dy_pt = dx / scale, dy / scale
    words_a = da.words(i) if da is not None else []
    words_b = db.words(i, dx_pt, dy_pt) if db is not None else []
    pw, ph = w / scale, h / scale
    for n_, r in enumerate(regions, 1):
        x0, y0 = r["x"] * pw, r["y"] * ph
        x1, y1 = x0 + r["w"] * pw, y0 + r["h"] * ph
        inside_a = [t for x, y, t in words_a if x0 <= x <= x1 and y0 <= y <= y1]
        inside_b = [t for x, y, t in words_b if x0 <= x <= x1 and y0 <= y <= y1]
        r["n"] = n_
        r["wordsAdded"], r["wordsRemoved"] = _word_diff(inside_a, inside_b)
        r["mm"] = [round(v * 25.4 / 72, 1) for v in (x0, y0, x1 - x0, y1 - y0)]
    more = max(0, len(regions) - MAX_REGIONS)
    if more:
        notes.append(f"{more} more regions not listed")
        regions = regions[:MAX_REGIONS]
    if specks:
        notes.append(f"{plural(specks, 'speck')} under {MIN_REGION_PX} px not listed")
    if (dx, dy) != (0, 0):
        notes.append(f"Newer revision aligned by {dx_pt * 25.4 / 72:+.1f}, {dy_pt * 25.4 / 72:+.1f} mm")
    words_added, words_removed = _word_diff([t for *_, t in words_a], [t for *_, t in words_b])
    union = (ai | bi).bit_count()
    changed_px = (added | removed).bit_count()
    if da is None:
        status = "added"
    elif db is None:
        status = "removed"
    else:
        status = "changed" if regions or words_added or words_removed else "same"
    pts = sa or sb
    return {
        "index": i, "status": status, "overlay": str(overlay), "thumb": str(_thumb_path(overlay)),
        "width": w, "height": h,
        "size": f"{_mm(pts[0])} × {_mm(pts[1])} mm", "regions": regions, "notes": notes,
        "wordsAdded": words_added[:200], "wordsRemoved": words_removed[:200],
        "addedPx": added.bit_count(), "removedPx": removed.bit_count(),
        "changedPct": round(100 * changed_px / union, 2) if union else 0.0,
    }


# ------------------------------------------------------------------------------------------------ zip helpers
def _open_zip(path: str | Path, label: str) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise DiffError(f"{Path(path).name} could not be read as {label}: {exc}") from exc


def _rels(z: zipfile.ZipFile, rels_path: str, base: str) -> dict[str, str]:
    """Relationship id -> part name inside the package."""
    try:
        root = ET.fromstring(z.read(rels_path))
    except KeyError:
        return {}
    out = {}
    for rel in root.iter(f"{{{NS_PKG}}}Relationship"):
        target = rel.get("Target", "")
        if rel.get("TargetMode") == "External":
            continue
        part = target.lstrip("/") if target.startswith("/") else _join(base, target)
        out[rel.get("Id", "")] = part
    return out


def _join(base: str, target: str) -> str:
    parts = [p for p in base.split("/") if p] + []
    for seg in target.split("/"):
        if seg == "..":
            if parts:
                parts.pop()
        elif seg and seg != ".":
            parts.append(seg)
    return "/".join(parts)


# ------------------------------------------------------------------------------------------------ Excel
_CELL_RE = re.compile(r"([A-Z]+)(\d+)")
_DATE_BUILTIN = set(range(14, 23)) | set(range(45, 48))


def col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def col_letters(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _is_date_format(code: str) -> bool:
    code = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", code).lower()
    return bool(re.search(r"[dy]", code)) or bool(re.search(r"(^|[^a-z])m+([^a-z]|$)", code) and "h" in code)


def _xlsx_styles(z: zipfile.ZipFile) -> list[bool]:
    """Per cell style index: does its number format show a date?"""
    try:
        root = ET.fromstring(z.read("xl/styles.xml"))
    except KeyError:
        return []
    custom = {}
    fmts = root.find(f"{{{NS_MAIN}}}numFmts")
    if fmts is not None:
        for f in fmts:
            custom[int(f.get("numFmtId", "0"))] = f.get("formatCode", "")
    out = []
    xfs = root.find(f"{{{NS_MAIN}}}cellXfs")
    if xfs is not None:
        for xf in xfs:
            fid = int(xf.get("numFmtId", "0"))
            out.append(fid in _DATE_BUILTIN or (fid in custom and _is_date_format(custom[fid])))
    return out


def _serial_to_text(v: str, date1904: bool) -> str:
    try:
        f = float(v)
    except ValueError:
        return v
    base = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 30)
    try:
        d = base + timedelta(days=f)
    except OverflowError:
        return v
    if abs(f - round(f)) < 1e-9:
        return d.strftime("%Y-%m-%d")
    return d.strftime("%Y-%m-%d %H:%M:%S" if d.second else "%Y-%m-%d %H:%M")


def _number_text(v: str) -> str:
    """The stored number as Excel keeps it, with float noise trimmed ("0.30000000000000004" -> "0.3")."""
    try:
        f = float(v)
    except ValueError:
        return v
    if f.is_integer() and abs(f) < 1e15:
        return str(int(f))
    return repr(round(f, 12)).rstrip("0").rstrip(".") if "e" not in v.lower() else v


def _text_of(el: ET.Element) -> str:
    return "".join(t.text or "" for t in el.iter(f"{{{NS_MAIN}}}t"))


def read_xlsx(path: str | Path) -> dict[str, dict[str, tuple[str, str]]]:
    """Sheet name -> {cell ref: (shown value, formula)} for every cell that holds a value or a formula."""
    with _open_zip(path, "an Excel workbook") as z:
        try:
            wb = ET.fromstring(z.read("xl/workbook.xml"))
        except KeyError as exc:
            raise DiffError(f"{Path(path).name} has no workbook part; is it an Excel file?") from exc
        rels = _rels(z, "xl/_rels/workbook.xml.rels", "xl")
        shared: list[str] = []
        try:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{{{NS_MAIN}}}si"):
                # plain text in si/t, rich runs in si/r/t; phonetic runs (si/rPh) are not shown
                parts = []
                for child in si:
                    if child.tag == f"{{{NS_MAIN}}}t":
                        parts.append(child.text or "")
                    elif child.tag == f"{{{NS_MAIN}}}r":
                        parts.append(_text_of(child))
                shared.append("".join(parts))
        except KeyError:
            pass
        styles = _xlsx_styles(z)
        pr = wb.find(f"{{{NS_MAIN}}}workbookPr")
        date1904 = pr is not None and pr.get("date1904", "0") in ("1", "true")
        sheets: dict[str, dict[str, tuple[str, str]]] = {}
        node = wb.find(f"{{{NS_MAIN}}}sheets")
        for sh in (node if node is not None else []):
            name = sh.get("name", "")
            part = rels.get(sh.get(f"{{{NS_REL}}}id", ""), "")
            if not part or part not in z.namelist():
                continue                       # a chart sheet or a missing part: no cells to compare
            cells: dict[str, tuple[str, str]] = {}
            with z.open(part) as f:
                for _, el in ET.iterparse(f):
                    if el.tag != f"{{{NS_MAIN}}}c":
                        continue
                    ref = el.get("r", "")
                    t = el.get("t", "n")
                    v_el = el.find(f"{{{NS_MAIN}}}v")
                    f_el = el.find(f"{{{NS_MAIN}}}f")
                    raw = v_el.text if v_el is not None and v_el.text is not None else None
                    if t == "s" and raw is not None:
                        try:
                            val = shared[int(raw)]
                        except (ValueError, IndexError):
                            val = raw
                    elif t == "inlineStr":
                        is_el = el.find(f"{{{NS_MAIN}}}is")
                        val = _text_of(is_el) if is_el is not None else ""
                    elif t == "b" and raw is not None:
                        val = "TRUE" if raw in ("1", "true") else "FALSE"
                    elif raw is None:
                        val = ""
                    elif t in ("str", "e"):
                        val = raw
                    else:
                        s = int(el.get("s", "0") or 0)
                        val = _serial_to_text(raw, date1904) if s < len(styles) and styles[s] else _number_text(raw)
                    formula = (f_el.text or "") if f_el is not None else ""
                    if ref and (val != "" or formula):
                        cells[ref] = (val, "=" + formula if formula else "")
                    el.clear()
            sheets[name] = cells
        return sheets


def _cell_key(ref: str) -> tuple[int, int]:
    m = _CELL_RE.fullmatch(ref)
    return (int(m.group(2)), col_index(m.group(1))) if m else (0, 0)


def _by_row(cells: dict[str, tuple[str, str]]) -> dict[int, dict[int, tuple[str, str]]]:
    rows: dict[int, dict[int, tuple[str, str]]] = {}
    for ref, v in cells.items():
        r, c = _cell_key(ref)
        rows.setdefault(r, {})[c] = v
    return rows


def _cell_row(ref_old: str, ref_new: str, old: tuple[str, str] | None,
              new: tuple[str, str] | None) -> dict[str, Any] | None:
    if old == new:
        return None
    if old is None:
        kind = "added"
    elif new is None:
        kind = "removed"
    elif old[0] == new[0]:
        kind = "formula"                   # same shown value, different formula
    else:
        kind = "changed"
    return {"cell": ref_new or ref_old, "oldCell": ref_old, "kind": kind,
            "old": old[0] if old else "", "new": new[0] if new else "",
            "oldFormula": old[1] if old else "", "newFormula": new[1] if new else ""}


def _sheet_changes(ca: dict[str, tuple[str, str]], cb: dict[str, tuple[str, str]]) -> tuple[list[dict], int, int]:
    """Cell changes with rows aligned first: a row inserted or deleted in the newer revision is reported
    as that row's cells added or removed, not as every row under it changed.  Rows are matched by their
    shown values (formulas are compared after matching, as their references move with the rows)."""
    ra, rb = _by_row(ca), _by_row(cb)
    na, nb = sorted(ra), sorted(rb)
    sig_a = [tuple(sorted((c, v[0]) for c, v in ra[r].items())) for r in na]
    sig_b = [tuple(sorted((c, v[0]) for c, v in rb[r].items())) for r in nb]
    out: list[dict[str, Any]] = []
    inserted = deleted = 0

    def pair(r_old: int | None, r_new: int | None) -> None:
        cells_a = ra.get(r_old, {}) if r_old is not None else {}
        cells_b = rb.get(r_new, {}) if r_new is not None else {}
        for c in sorted(set(cells_a) | set(cells_b)):
            row = _cell_row(f"{col_letters(c)}{r_old}" if r_old is not None and c in cells_a else "",
                            f"{col_letters(c)}{r_new}" if r_new is not None and c in cells_b else "",
                            cells_a.get(c), cells_b.get(c))
            if row is not None:
                if not row["cell"]:
                    row["cell"] = f"{col_letters(c)}{r_new if r_new is not None else r_old}"
                out.append(row)

    def alike(i: int, j: int) -> bool:
        a, b = dict(sig_a[i]), dict(sig_b[j])
        shared = sum(1 for c in a if c in b and a[c] == b[c])
        return shared * 2 >= max(len(a), len(b))

    sm = difflib.SequenceMatcher(None, sig_a, sig_b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2), strict=True):
                pair(na[i], nb[j])         # same values: only formulas can differ
            continue
        olds, news = list(range(i1, i2)), list(range(j1, j2))
        while olds and news:
            i, j = olds[0], news[0]
            if alike(i, j) or (len(olds) == len(news) and na[i] == nb[j]):
                pair(na[i], nb[j])
                olds.pop(0)
                news.pop(0)
            elif len(olds) > len(news):
                pair(na[i], None)
                deleted += 1
                olds.pop(0)
            else:
                pair(None, nb[j])
                inserted += 1
                news.pop(0)
        for i in olds:
            pair(na[i], None)
            deleted += 1
        for j in news:
            pair(None, nb[j])
            inserted += 1
    out.sort(key=lambda r: _cell_key(r["cell"]))
    return out, inserted, deleted


def compare_xlsx(a: str | Path, b: str | Path) -> dict[str, Any]:
    sa, sb = read_xlsx(a), read_xlsx(b)
    names = list(sa) + [n for n in sb if n not in sa]
    sheets = []
    total = Counter()
    for name in names:
        ca, cb = sa.get(name), sb.get(name)
        status = "added" if ca is None else "removed" if cb is None else ""
        rows, inserted, deleted = _sheet_changes(ca or {}, cb or {})
        counts = Counter(r["kind"] for r in rows)
        total.update(counts)
        if not status:
            status = "changed" if rows else "same"
        sheets.append({"name": name, "status": status, "rows": rows[:MAX_ROWS],
                       "more": max(0, len(rows) - MAX_ROWS), "count": len(rows),
                       "rowsInserted": inserted, "rowsDeleted": deleted,
                       "added": counts["added"], "removed": counts["removed"],
                       "changed": counts["changed"] + counts["formula"]})
    changed_sheets = [s for s in sheets if s["status"] != "same"]
    n_cells = sum(total.values())
    facts = [f"{plural(n_cells, 'cell')} differ in {len(changed_sheets)} of {plural(len(sheets), 'sheet')}"]
    for key, word in (("changed", "changed"), ("added", "added"), ("removed", "removed")):
        v = total[key] + (total["formula"] if key == "changed" else 0)
        if v:
            facts.append(f"{v} {word}")
    return {"summary": " · ".join(facts), "sheets": sheets, "cellCount": n_cells}


# ------------------------------------------------------------------------------------------------ Word
_TOKEN_RE = re.compile(r"\s+|\w+|[^\w\s]", re.UNICODE)


def _w(tag: str) -> str:
    return f"{{{NS_W}}}{tag}"


def _para_text(p: ET.Element) -> str:
    out = []
    for el in p.iter():
        tag = el.tag
        if tag == _w("t"):
            out.append(el.text or "")
        elif tag == _w("tab"):
            out.append("\t")
        elif tag in (_w("br"), _w("cr")):
            out.append("\n")
        elif tag == _w("noBreakHyphen"):
            out.append("-")
    return "".join(out)


def _walk(el: ET.Element, where: str, out: list[tuple[str, str]], counters: dict[str, int]) -> None:
    """Paragraphs in reading order with where they stand ("Table 2, row 3, cell 1").  Deleted text of a
    tracked change (w:delText) is not shown, inserted text is: the document as if changes were accepted."""
    for child in el:
        if child.tag == _w("p"):
            out.append((where, _para_text(child)))
        elif child.tag == _w("tbl"):
            counters["table"] += 1
            t = counters["table"]
            for r, tr in enumerate(child.findall(_w("tr")), 1):
                for c, tc in enumerate(tr.findall(_w("tc")), 1):
                    inner = f"Table {t}, row {r}, cell {c}"
                    _walk(tc, f"{where} · {inner}" if where else inner, out, counters)
        elif child.tag in (_w("sdt"), _w("sdtContent"), _w("customXml"), _w("ins"), _w("smartTag")):
            _walk(child, where, out, counters)


def read_docx(path: str | Path) -> list[tuple[str, str]]:
    """(part, location, text) flattened to (location, text) for the body, then headers and footers."""
    with _open_zip(path, "a Word document") as z:
        try:
            doc = ET.fromstring(z.read("word/document.xml"))
        except KeyError as exc:
            raise DiffError(f"{Path(path).name} has no document part; is it a Word file?") from exc
        out: list[tuple[str, str]] = []
        body = doc.find(_w("body"))
        if body is not None:
            _walk(body, "", out, {"table": 0})
        for kind in ("header", "footer"):
            parts = sorted(n for n in z.namelist() if re.fullmatch(rf"word/{kind}\d*\.xml", n))
            for k, part in enumerate(parts, 1):
                label = f"{kind.capitalize()} {k}"
                _walk(ET.fromstring(z.read(part)), label, out, {"table": 0})
        return out


def _segments(old: str, new: str) -> list[dict[str, str]]:
    """Word-level edit of one paragraph: runs of equal, deleted and inserted text, in order."""
    ta, tb = _TOKEN_RE.findall(old), _TOKEN_RE.findall(new)
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    segs: list[dict[str, str]] = []

    def push(op: str, text: str) -> None:
        if not text:
            return
        if segs and segs[-1]["op"] == op:
            segs[-1]["text"] += text
        else:
            segs.append({"op": op, "text": text})

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            push("eq", "".join(ta[i1:i2]))
        else:
            push("del", "".join(ta[i1:i2]))
            push("ins", "".join(tb[j1:j2]))
    return segs


def _label(where: str, idx: int) -> str:
    return where or f"Paragraph {idx}"


def compare_docx(a: str | Path, b: str | Path) -> dict[str, Any]:
    pa = [(w, t) for w, t in read_docx(a)]
    pb = [(w, t) for w, t in read_docx(b)]
    # number body paragraphs (empty ones too, so the number is the one Word's navigator counts) and
    # compare only the ones that hold text
    def index(ps: list[tuple[str, str]]) -> list[tuple[str, str]]:
        out, n = [], 0
        for where, text in ps:
            if not where:
                n += 1                     # body paragraphs only; table cells and headers carry their place
            if text.strip():
                out.append((_label(where, n), text))
        return out

    ia, ib = index(pa), index(pb)
    ta, tb = [t for _, t in ia], [t for _, t in ib]
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    rows: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        olds, news = list(range(i1, i2)), list(range(j1, j2))
        # inside a replaced block, pair paragraphs in order while they stay alike (ratio >= 0.4), stand in
        # the same place (a table cell), or are the only one on each side
        single = len(olds) == 1 and len(news) == 1
        while olds and news:
            i, j = olds[0], news[0]
            same_cell = ia[i][0] == ib[j][0] and not ia[i][0].startswith("Paragraph ")
            if single or same_cell or \
                    difflib.SequenceMatcher(None, ta[i], tb[j], autojunk=False).ratio() >= 0.4:
                rows.append({"kind": "changed", "where": ib[j][0], "whereOld": ia[i][0], "old": ta[i], "new": tb[j],
                             "segments": _segments(ta[i], tb[j])})
                olds.pop(0)
                news.pop(0)
            elif len(olds) >= len(news):
                rows.append({"kind": "removed", "where": ia[i][0], "whereOld": ia[i][0], "old": ta[i], "new": "",
                             "segments": [{"op": "del", "text": ta[i]}]})
                olds.pop(0)
            else:
                rows.append({"kind": "added", "where": ib[j][0], "whereOld": "", "old": "", "new": tb[j],
                             "segments": [{"op": "ins", "text": tb[j]}]})
                news.pop(0)
        for i in olds:
            rows.append({"kind": "removed", "where": ia[i][0], "whereOld": ia[i][0], "old": ta[i], "new": "",
                         "segments": [{"op": "del", "text": ta[i]}]})
        for j in news:
            rows.append({"kind": "added", "where": ib[j][0], "whereOld": "", "old": "", "new": tb[j],
                         "segments": [{"op": "ins", "text": tb[j]}]})
    counts = Counter(r["kind"] for r in rows)
    facts = []
    for key in ("changed", "added", "removed"):
        if counts[key]:
            facts.append(f"{plural(counts[key], 'paragraph')} {key}")
    if not facts:
        facts = ["No text differs"]
    return {"summary": " · ".join(facts), "paragraphs": rows[:MAX_ROWS], "more": max(0, len(rows) - MAX_ROWS),
            "paragraphCount": len(ib), "changeCount": len(rows)}
