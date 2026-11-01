"""Project cards (grid), project rows (list) and stat tiles."""
from __future__ import annotations

from datetime import UTC

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QVBoxLayout,
)

from project_opener.core import models as M
from project_opener.core.health import ProjectHealth
from project_opener.ui import icons, theme
from project_opener.ui.widgets.common import Badge, Button, ElidedLabel, IconButton, IconCircle


def relative_time(iso: str | None) -> str:
    dt = M.parse_iso(iso)
    if not dt:
        return "Never opened"
    from datetime import datetime
    delta = datetime.now(UTC) - dt
    s = int(delta.total_seconds())
    if s < 60:
        return "Just now"
    if s < 3600:
        return f"{s // 60} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    if delta.days == 1:
        return "Yesterday"
    if delta.days < 7:
        return f"{delta.days} d ago"
    return dt.astimezone().strftime("%d %b %Y")


class HoverCard(QFrame):
    """A card with an animated hover lift and accent border."""

    clicked = Signal()

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self._hover = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim = QPropertyAnimation(self, b"hover", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(18)
        self._shadow.setOffset(0, 4)
        self._shadow.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(self._shadow)

    def get_hover(self) -> float:
        return self._hover

    def set_hover(self, v: float) -> None:
        self._hover = v
        self._shadow.setBlurRadius(18 + 16 * v)
        self._shadow.setOffset(0, 4 + 4 * v)
        self.update()

    hover = Property(float, get_hover, set_hover)

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def enterEvent(self, e) -> None:  # noqa: N802
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def paintEvent(self, e) -> None:  # noqa: N802
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, t.radius, t.radius)
        bg = QColor(t.surface)
        hover_bg = QColor(t.surface_2)
        mixed = QColor(
            int(bg.red() + (hover_bg.red() - bg.red()) * self._hover),
            int(bg.green() + (hover_bg.green() - bg.green()) * self._hover),
            int(bg.blue() + (hover_bg.blue() - bg.blue()) * self._hover))
        p.fillPath(path, mixed)
        # colour glow strip at the top
        accent = QColor(self._color)
        strip = QPainterPath()
        strip.addRoundedRect(QRectF(r.x(), r.y(), r.width(), 4), 2, 2)
        p.fillPath(strip, accent)
        glow = QColor(accent)
        glow.setAlpha(int(18 + 30 * self._hover))
        p.fillRect(QRectF(r.x(), r.y() + 4, r.width(), 46), glow)
        border = QColor(t.border)
        hb = QColor(self._color)
        border = QColor(
            int(border.red() + (hb.red() - border.red()) * self._hover * 0.7),
            int(border.green() + (hb.green() - border.green()) * self._hover * 0.7),
            int(border.blue() + (hb.blue() - border.blue()) * self._hover * 0.7))
        p.setPen(QPen(border, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


class ProjectCard(HoverCard):
    launch_requested = Signal(object)          # project
    launch_set_requested = Signal(object, object)
    open_requested = Signal(object)
    menu_requested = Signal(object, object)    # project, QPoint (global)
    pin_requested = Signal(object)
    favorite_requested = Signal(object)

    WIDTH = 332
    HEIGHT = 200

    def __init__(self, project: M.Project, parent=None):
        super().__init__(project.color, parent)
        self.project = project
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        t = theme.current()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 14)
        lay.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.icon = IconCircle(project.icon, project.color, 40)
        top.addWidget(self.icon)
        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        self.title = ElidedLabel(project.name, mode=Qt.TextElideMode.ElideRight)
        self.title.setStyleSheet(f"font-size: {t.font_size + 2}pt; font-weight: 700;")
        title_col.addWidget(self.title)
        sub = " · ".join(x for x in (project.client, project.job_number) if x) or project.description or " "
        self.subtitle = ElidedLabel(sub, mode=Qt.TextElideMode.ElideRight)
        self.subtitle.setObjectName("muted")
        title_col.addWidget(self.subtitle)
        top.addLayout(title_col, 1)
        self.pin_btn = IconButton("fa5s.thumbtack", "Pin", size=13,
                                  color=t.accent if project.pinned else t.text_faint)
        self.pin_btn.clicked.connect(lambda: self.pin_requested.emit(self.project))
        top.addWidget(self.pin_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.fav_btn = IconButton("fa5s.star" if project.favorite else "fa5r.star", "Favourite", size=13,
                                  color=t.warning if project.favorite else t.text_faint)
        self.fav_btn.clicked.connect(lambda: self.favorite_requested.emit(self.project))
        top.addWidget(self.fav_btn, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(top)

        # tags row
        tags = QHBoxLayout()
        tags.setSpacing(6)
        for tag in project.tags[:3]:
            tags.addWidget(Badge(tag, project.color))
        if len(project.tags) > 3:
            tags.addWidget(Badge(f"+{len(project.tags) - 3}", t.text_faint))
        tags.addStretch(1)
        lay.addLayout(tags)
        lay.addStretch(1)

        meta = QHBoxLayout()
        meta.setSpacing(6)
        self.health_dot = QLabel()
        self.health_dot.setFixedSize(14, 14)
        meta.addWidget(self.health_dot)
        self.meta = QLabel(f"{len(project.enabled_items)}/{len(project.items)} items  ·  {relative_time(project.last_opened)}")
        self.meta.setObjectName("faint")
        meta.addWidget(self.meta, 1)
        lay.addLayout(meta)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.launch_btn = Button("Open", "fa5s.play", "primary")
        self.launch_btn.setFixedHeight(32)
        self.launch_btn.clicked.connect(lambda: self.launch_requested.emit(self.project))
        actions.addWidget(self.launch_btn, 1)
        if project.launch_sets:
            self.sets_btn = Button("", "fa5s.layer-group")
            self.sets_btn.setFixedSize(34, 32)
            self.sets_btn.setToolTip("Launch sets")
            self.sets_btn.clicked.connect(self._show_sets)
            actions.addWidget(self.sets_btn)
        self.more_btn = Button("", "fa5s.ellipsis-h")
        self.more_btn.setFixedSize(34, 32)
        self.more_btn.clicked.connect(lambda: self.menu_requested.emit(self.project, self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft())))
        actions.addWidget(self.more_btn)
        lay.addLayout(actions)
        # Single click opens the detail page; launching is the Open button's job.
        self.clicked.connect(lambda: self.open_requested.emit(self.project))
        self.set_health(None)

    def _show_sets(self) -> None:
        menu = QMenu(self)
        for s in self.project.launch_sets:
            act = menu.addAction(icons.icon(s.icon), f"{s.name}  ({len(s.item_ids)})")
            act.triggered.connect(lambda _=False, ls=s: self.launch_set_requested.emit(self.project, ls))
        menu.exec(self.sets_btn.mapToGlobal(self.sets_btn.rect().bottomLeft()))

    def set_health(self, health: ProjectHealth | None) -> None:
        t = theme.current()
        if health is None:
            self.health_dot.setPixmap(icons.pixmap("fa5s.circle-notch", 11, t.text_faint))
            self.health_dot.setToolTip("Checking paths…")
            return
        problems = health.problems
        if not problems:
            self.health_dot.setPixmap(icons.pixmap("fa5s.check-circle", 12, t.success))
            self.health_dot.setToolTip("All paths reachable")
        else:
            offline = any(p.status == "offline" for p in problems)
            color = t.danger if offline else t.warning
            self.health_dot.setPixmap(icons.pixmap("fa5s.exclamation-circle", 12, color))
            self.health_dot.setToolTip(f"{len(problems)} item(s) need attention")


class ProjectRow(QFrame):
    """Compact list representation."""

    launch_requested = Signal(object)
    open_requested = Signal(object)
    menu_requested = Signal(object, object)

    def __init__(self, project: M.Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(58)
        t = theme.current()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 10, 8)
        lay.setSpacing(12)
        lay.addWidget(IconCircle(project.icon, project.color, 34))
        col = QVBoxLayout()
        col.setSpacing(0)
        name = QLabel(project.name)
        name.setStyleSheet("font-weight: 700;")
        col.addWidget(name)
        sub = " · ".join(x for x in (project.client, project.job_number, project.description) if x)
        sl = ElidedLabel(sub or f"{len(project.items)} items", mode=Qt.TextElideMode.ElideRight)
        sl.setObjectName("muted")
        col.addWidget(sl)
        lay.addLayout(col, 1)
        for tag in project.tags[:4]:
            lay.addWidget(Badge(tag, project.color))
        self.health_dot = QLabel()
        self.health_dot.setFixedSize(14, 14)
        lay.addWidget(self.health_dot)
        meta = QLabel(f"{len(project.enabled_items)}/{len(project.items)} · {relative_time(project.last_opened)}")
        meta.setObjectName("faint")
        lay.addWidget(meta)
        if project.pinned:
            pin = QLabel()
            pin.setPixmap(icons.pixmap("fa5s.thumbtack", 12, t.accent))
            lay.addWidget(pin)
        b = Button("Open", "fa5s.play", "primary")
        b.setFixedHeight(30)
        b.clicked.connect(lambda: self.launch_requested.emit(self.project))
        lay.addWidget(b)
        more = Button("", "fa5s.ellipsis-h")
        more.setFixedSize(32, 30)
        more.clicked.connect(lambda: self.menu_requested.emit(self.project, more.mapToGlobal(more.rect().bottomLeft())))
        lay.addWidget(more)
        self.set_health(None)

    def set_health(self, health: ProjectHealth | None) -> None:
        t = theme.current()
        if health is None:
            self.health_dot.setPixmap(icons.pixmap("fa5s.circle-notch", 11, t.text_faint))
        elif not health.problems:
            self.health_dot.setPixmap(icons.pixmap("fa5s.check-circle", 12, t.success))
        else:
            self.health_dot.setPixmap(icons.pixmap("fa5s.exclamation-circle", 12, t.warning))

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        # Single click opens the detail page; launching is the Open button's job.
        if e.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit(self.project)
        super().mouseReleaseEvent(e)


class StatTile(QFrame):
    def __init__(self, title: str, value: str, icon_name: str, color: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        t = theme.current()
        color = color or t.accent
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)
        lay.addWidget(IconCircle(icon_name, color, 40))
        col = QVBoxLayout()
        col.setSpacing(0)
        self.value = QLabel(value)
        self.value.setStyleSheet(f"font-size: {t.font_size + 8}pt; font-weight: 800; font-family: '{theme.display_font()}';")
        col.addWidget(self.value)
        self.title = QLabel(title)
        self.title.setObjectName("muted")
        col.addWidget(self.title)
        lay.addLayout(col, 1)
        self.setMinimumWidth(170)

    def set_value(self, v: str) -> None:
        self.value.setText(v)
