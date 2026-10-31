"""Icon helpers: qtawesome (Font Awesome 5) with graceful fallbacks."""
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
    """Font Awesome icon in the given colour (defaults to muted text)."""
    t = theme.current()
    color = color or t.text_muted
    if qta is None:
        return _fallback(color)
    try:
        return qta.icon(name, color=color, color_active=color_active or color, scale_factor=scale)
    except Exception:
        try:
            return qta.icon("fa5s.circle", color=color)
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
    ("fa5s.folder", "Folder"), ("fa5s.drafting-compass", "Drafting"), ("fa5s.project-diagram", "Diagram"),
    ("fa5s.industry", "Plant"), ("fa5s.oil-can", "Oil & gas"), ("fa5s.bolt", "Power"), ("fa5s.water", "Water"),
    ("fa5s.fire", "Fire"), ("fa5s.cogs", "Mechanical"), ("fa5s.cubes", "3D model"), ("fa5s.ruler-combined", "Layout"),
    ("fa5s.clipboard-check", "QA / check"), ("fa5s.file-signature", "Submission"), ("fa5s.ship", "Marine"),
    ("fa5s.hard-hat", "Site"), ("fa5s.flask", "Process"), ("fa5s.tools", "Tools"), ("fa5s.book", "Reference"),
    ("fa5s.star", "Star"), ("fa5s.rocket", "Launch"), ("fa5s.briefcase", "Client"), ("fa5s.users", "Team"),
    ("fa5s.archive", "Archive"), ("fa5s.globe", "Web"),
]

KIND_ICONS = {
    "file": "fa5s.file", "folder": "fa5s.folder-open", "url": "fa5s.link", "app": "fa5s.rocket", "command": "fa5s.terminal",
}
