"""Render resources/icon/app.svg into PNGs and a multi-size Windows ICO.

Usage:  python tools/build_icon.py

Uses Qt's SVG renderer (already a dependency) so no cairo/ImageMagick is
needed on CI.  The ICO embeds PNG-compressed images, which Windows has
supported since Vista.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "project_opener" / "resources" / "icon"
SVG = ICON_DIR / "app.svg"
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def render_pngs() -> dict[int, bytes]:
    from PySide6.QtCore import QBuffer, QIODevice, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    QGuiApplication.instance() or QGuiApplication(sys.argv)
    renderer = QSvgRenderer(str(SVG))
    if not renderer.isValid():
        raise SystemExit(f"invalid SVG: {SVG}")
    out: dict[int, bytes] = {}
    for size in SIZES + (512, 1024):
        img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        renderer.render(p)
        p.end()
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        out[size] = bytes(buf.data())
        (ICON_DIR / f"app-{size}.png").write_bytes(out[size])
    return out


def write_ico(pngs: dict[int, bytes], target: Path) -> None:
    entries = [(s, pngs[s]) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory = b""
    body = b""
    for size, data in entries:
        w = h = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        body += data
        offset += len(data)
    target.write_bytes(header + directory + body)


def main() -> None:
    pngs = render_pngs()
    write_ico(pngs, ICON_DIR / "app.ico")
    print(f"wrote {ICON_DIR / 'app.ico'} with sizes {SIZES} and PNGs up to 1024px")


if __name__ == "__main__":
    main()
