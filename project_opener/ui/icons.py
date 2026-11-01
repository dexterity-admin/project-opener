"""Icon helpers: one outline set (Phosphor regular, bundled with qtawesome).

Callers keep passing the Font Awesome 5 names the code and the saved
workspaces use; ``ALIASES`` maps each of them to the closest Phosphor glyph in
``icon()`` / ``pixmap()`` so the change lives in one place.  Unknown names fall
back to the original (qtawesome still ships FA5), so nothing goes blank.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from project_opener import constants as C
from project_opener.ui import theme

log = logging.getLogger(__name__)

try:
    import qtawesome as qta  # type: ignore
except Exception as exc:  # pragma: no cover - fallback path
    log.warning("qtawesome unavailable: %s", exc)
    qta = None

_app_icon: QIcon | None = None

# Font Awesome 5 name -> Phosphor regular name (the only set drawn in the app).
ALIASES: dict[str, str] = {
    # navigation and chrome
    "fa5s.home": "ph.house",
    "fa5s.th-large": "ph.squares-four",
    "fa5s.users": "ph.users",
    "fa5s.sync-alt": "ph.arrows-clockwise",
    "fa5s.sliders-h": "ph.sliders-horizontal",
    "fa5s.search": "ph.magnifying-glass",
    "fa5s.angle-double-left": "ph.caret-double-left",
    "fa5s.angle-double-right": "ph.caret-double-right",
    "fa5s.plus": "ph.plus",
    "fa5s.times": "ph.x",
    "fa5s.check": "ph.check",
    "fa5s.ellipsis-h": "ph.dots-three",
    "fa5s.ellipsis-v": "ph.dots-three-vertical",
    "fa5s.arrow-left": "ph.arrow-left",
    "fa5s.arrow-right": "ph.arrow-right",
    "fa5s.arrow-circle-up": "ph.arrow-circle-up",
    "fa5s.external-link-alt": "ph.arrow-square-out",
    "fa5s.window-maximize": "ph.frame-corners",
    "fa5s.adjust": "ph.circle-half",
    "fa5s.eye-dropper": "ph.eyedropper",
    "fa5s.list": "ph.list-bullets",
    "fa5s.stream": "ph.list-dashes",
    "fa5s.magic": "ph.magic-wand",
    "fa5s.key": "ph.key",
    "fa5s.question-circle": "ph.question",
    # status
    "fa5s.check-circle": "ph.check-circle",
    "fa5s.exclamation-circle": "ph.warning-circle",
    "fa5s.exclamation-triangle": "ph.warning",
    "fa5s.times-circle": "ph.x-circle",
    "fa5s.info-circle": "ph.info",
    "fa5s.circle-notch": "ph.circle-dashed",
    "fa5s.circle": "ph.circle",
    "fa5s.heartbeat": "ph.heartbeat",
    "fa5s.plug": "ph.lightning-slash",
    "fa5s.network-wired": "ph.tree-structure",
    "fa5s.power-off": "ph.power",
    # actions
    "fa5s.play": "ph.play",
    "fa5s.play-circle": "ph.play-circle",
    "fa5s.pen": "ph.pencil-simple",
    "fa5s.trash": "ph.trash",
    "fa5s.copy": "ph.copy",
    "fa5s.clone": "ph.copy",
    "fa5s.undo": "ph.arrow-counter-clockwise",
    "fa5s.redo": "ph.arrow-clockwise",
    "fa5s.history": "ph.clock-counter-clockwise",
    "fa5s.forward": "ph.arrow-right",
    "fa5s.download": "ph.download-simple",
    "fa5s.cloud-upload-alt": "ph.cloud-arrow-up",
    "fa5s.cloud-download-alt": "ph.cloud-arrow-down",
    "fa5s.share-alt": "ph.share-network",
    "fa5s.paper-plane": "ph.paper-plane-tilt",
    "fa5s.thumbtack": "ph.push-pin",
    "fa5s.star": "ph.star",
    "fa5r.star": "ph.star",
    "fa5s.layer-group": "ph.stack",
    "fa5s.bullhorn": "ph.megaphone",
    "fa5s.inbox": "ph.tray",
    "fa5s.terminal": "ph.terminal-window",
    # files and folders
    "fa5s.file": "ph.file",
    "fa5s.file-alt": "ph.file-text",
    "fa5s.file-export": "ph.file-arrow-up",
    "fa5s.file-import": "ph.file-arrow-down",
    "fa5s.file-signature": "ph.pen-nib",
    "fa5s.file-pdf": "ph.file-pdf",
    "fa5s.file-word": "ph.file-text",
    "fa5s.file-excel": "ph.file-text",
    "fa5s.file-code": "ph.code",
    "fa5s.file-image": "ph.image-square",
    "fa5s.file-archive": "ph.archive-box",
    "fa5s.folder": "ph.folder",
    "fa5s.folder-open": "ph.folder-open",
    "fa5s.folder-plus": "ph.folder-plus",
    "fa5s.link": "ph.link",
    "fa5s.archive": "ph.archive",
    "fa5s.book": "ph.book",
    "fa5s.clipboard-check": "ph.clipboard-text",
    # project subjects
    "fa5s.drafting-compass": "ph.compass",
    "fa5s.project-diagram": "ph.flow-arrow",
    "fa5s.industry": "ph.factory",
    "fa5s.oil-can": "ph.drop",
    "fa5s.bolt": "ph.lightning",
    "fa5s.water": "ph.drop-half",
    "fa5s.fire": "ph.fire",
    "fa5s.cogs": "ph.gear",
    "fa5s.cubes": "ph.cube",
    "fa5s.ruler-combined": "ph.ruler",
    "fa5s.ship": "ph.boat",
    "fa5s.hard-hat": "ph.hard-drives",
    "fa5s.flask": "ph.flask",
    "fa5s.tools": "ph.wrench",
    "fa5s.rocket": "ph.rocket",
    "fa5s.briefcase": "ph.briefcase",
    "fa5s.globe": "ph.globe",
    # brands
    "fa5b.microsoft": "ph.windows-logo",
    "fa5b.github": "ph.github-logo",
}


def resolve(name: str) -> str:
    """The Phosphor name drawn for ``name`` (fa5 names are aliased, others pass through)."""
    return ALIASES.get(name, name)


def app_icon() -> QIcon:
    global _app_icon
    if _app_icon is None:
        ico = C.resource_path("icon", "app.ico")
        _app_icon = QIcon(str(ico)) if ico.exists() else QIcon()
        for size in (16, 32, 48, 64, 128, 256):
            png = C.resource_path("icon", f"app-{size}.png")
            if png.exists():
                _app_icon.addFile(str(png), QSize(size, size))
    return _app_icon


def icon(name: str, color: str | None = None, color_active: str | None = None, scale: float = 1.0) -> QIcon:
    """Outline icon in the given colour (defaults to muted text)."""
    t = theme.current()
    color = color or t.text_muted
    if qta is None:
        return _fallback(color)
    for candidate in (resolve(name), name):
        try:
            return qta.icon(candidate, color=color, color_active=color_active or color, scale_factor=scale)
        except Exception:
            continue
    try:
        return qta.icon("ph.circle", color=color)
    except Exception:  # pragma: no cover
        return _fallback(color)


def pixmap(name: str, size: int = 20, color: str | None = None) -> QPixmap:
    return icon(name, color).pixmap(size, size)


def _fallback(color: str) -> QIcon:
    pm = QPixmap(16, 16)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(3, 3, 10, 10)
    p.end()
    return QIcon(pm)


PROJECT_ICONS: list[tuple[str, str]] = [
    ("ph.folder", "Folder"), ("ph.compass", "Drafting"), ("ph.flow-arrow", "Diagram"),
    ("ph.factory", "Plant"), ("ph.drop", "Oil & gas"), ("ph.lightning", "Power"), ("ph.drop-half", "Water"),
    ("ph.fire", "Fire"), ("ph.gear", "Mechanical"), ("ph.cube", "3D model"), ("ph.ruler", "Layout"),
    ("ph.clipboard-text", "QA / check"), ("ph.pen-nib", "Submission"), ("ph.boat", "Marine"),
    ("ph.hard-drives", "Site"), ("ph.flask", "Process"), ("ph.wrench", "Tools"), ("ph.book", "Reference"),
    ("ph.star", "Star"), ("ph.rocket", "Launch"), ("ph.briefcase", "Client"), ("ph.users", "Team"),
    ("ph.archive", "Archive"), ("ph.globe", "Web"),
]

KIND_ICONS = {
    "file": "ph.file", "folder": "ph.folder-open", "url": "ph.link", "app": "ph.rocket", "command": "ph.terminal-window",
}
