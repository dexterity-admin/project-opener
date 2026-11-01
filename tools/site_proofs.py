"""Cut the landing page's proof pictures from a smoke capture folder.

    python tools\\site_proofs.py <capture folder> [--out site/assets/screens] [--quality 84]

The capture folder is the output of ``tools\\smoke_ui.py --states --scale 2`` run once with
``--theme light`` and once with ``--theme dark`` (the same folder, or two folders merged), with
``PO_DEMO_ROOT`` and ``PO_DEMO_HUB`` set so the paths are office-shaped.  Every picture the page
shows is written from here and from nothing else, so the page can be refreshed after any app
round by re-running the two captures and then this script.

Each crop is a fixed pixel box in the 2× capture (2800×1720 for a 1400×860 window), saved as
WebP, and shown on the page at half its pixel width, so the app's 13 px text is 13 px on the
page.  The boxes are the app's own card edges; if a page layout moves, change the box here.
Deterministic: the same captures give byte-identical files.

Requires PySide6 (the app's own dependency); no Pillow.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath

ROOT = Path(__file__).resolve().parent.parent

# name -> (source capture, x, y, width, height[, rounded])  in 2× pixels.
# ``rounded`` = (full width, full height, radius): the box is a window onto a floating panel of that size
# (same origin) with rounded corners; the pixels outside the panel's rounded rectangle (the captured shadow)
# are filled with the page surface before the box is cut.
CROPS: dict[str, tuple] = {
    # Paths: the Items card of the P12513 project page (toggle, icon, name, path, status pill)
    "project-items-2x.webp": ("light-2x-project.png", 473, 417, 1336, 1104),
    # Hub: Online now, the tabs and the first row of published projects, sidebar excluded
    "hub-strip-2x.webp": ("light-2x-team.png", 473, 180, 2262, 726),
    # Search: the palette with "check" typed (five results)
    "palette-2x.webp": ("light-2x-palette.png", 721, 182, 1359, 920, (1359, 920, 32)),   # at the palette's own 1 px border
    # Search, phone: the same palette at 343 CSS px, the query and the first two results (nothing cut mid-word)
    "palette-phone-2x.webp": ("light-2x-palette.png", 721, 182, 686, 440, (1359, 920, 32)),
    # Updates: "This PC" and "Update sources" on the dark Updates page, up to date, both sources Reachable
    "updates-2x.webp": ("dark-2x-updates-uptodate.png", 473, 193, 2262, 692),
}


def cut(src_dir: Path, out_dir: Path, quality: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for name, spec in CROPS.items():
        source, x, y, w, h = spec[:5]
        rounded = spec[5] if len(spec) > 5 else None
        src = src_dir / source
        img = QImage(str(src))
        if img.isNull():
            print(f"missing or unreadable: {src}", file=sys.stderr)
            failures += 1
            continue
        box = QRect(x, y, w, h)
        if not img.rect().contains(box):
            print(f"{name}: box {box} is outside {source} ({img.width()}x{img.height()})", file=sys.stderr)
            failures += 1
            continue
        if rounded:
            fw, fh, radius = rounded
            panel = img.copy(QRect(x, y, fw, fh)).convertToFormat(QImage.Format.Format_ARGB32)
            filled = QImage(fw, fh, QImage.Format.Format_RGB32)
            filled.fill(QColor("#FFFFFF"))
            painter = QPainter(filled)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, fw, fh), radius, radius)
            painter.setClipPath(path)
            painter.drawImage(0, 0, panel)
            painter.end()
            crop = filled.copy(QRect(0, 0, w, h))
        else:
            crop = img.copy(box).convertToFormat(QImage.Format.Format_RGB32)
        dest = out_dir / name
        if not crop.save(str(dest), "WEBP", quality):
            print(f"{name}: could not write {dest}", file=sys.stderr)
            failures += 1
            continue
        print(f"{name}: {w}x{h} from {source} ({dest.stat().st_size} bytes); show at {w // 2}x{h // 2} CSS px")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("captures", help="folder with the 2x smoke captures (light and dark)")
    ap.add_argument("--out", default=str(ROOT / "site" / "assets" / "screens"))
    ap.add_argument("--quality", type=int, default=84)
    args = ap.parse_args()
    return 1 if cut(Path(args.captures), Path(args.out), args.quality) else 0


if __name__ == "__main__":
    sys.exit(main())
