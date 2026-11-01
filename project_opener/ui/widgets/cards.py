"""Project cards (grid), project rows (list), the KPI strip and stat tiles."""
from __future__ import annotations

from datetime import UTC

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from project_opener.core import models as M
from project_opener.core.health import ProjectHealth
from project_opener.ui import icons, theme
from project_opener.ui.widgets.common import (
    Button,
    Chip,
    ColorDot,
    ElidedLabel,
    IconButton,
    IconCircle,
    kpi_value_label,
)


def plural(n: int, word: str) -> str:
    """"1 item", "2 items", "0 launch sets"."""
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


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


def _mix(a: str, b: str, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    return QColor(
        int(ca.red() + (cb.red() - ca.red()) * t),
        int(ca.green() + (cb.green() - ca.green()) * t),
        int(ca.blue() + (cb.blue() - ca.blue()) * t),
    )


def _tag_chip(text: str) -> Chip:
    c = Chip(text, checkable=False)
    c.setFixedHeight(22)
    c.setStyleSheet("QPushButton#chip { min-height: 20px; max-height: 20px; padding: 0 9px; }")
    c.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return c


class HoverCard(QFrame):
    """A card: surface fill, 1 px border, no shadow.  On hover the border strengthens."""

    clicked = Signal()

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self._hover = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim = QPropertyAnimation(self, b"hover", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def get_hover(self) -> float:
        return self._hover

    def set_hover(self, v: float) -> None:
        self._hover = v
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
        p.fillPath(path, QColor(t.surface))
        p.setPen(QPen(_mix(t.border, t.border_strong, self._hover), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


def _health_line(parent_layout, dot_size: int = 6) -> tuple[ColorDot, QLabel]:
    dot = ColorDot(theme.current().text_faint, dot_size)
    parent_layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
    meta = QLabel("")
    meta.setObjectName("muted")
    meta.setFont(theme.ui_font(9, 400, tabular=True))
    parent_layout.addWidget(meta, 1)
    return dot, meta


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
        self.setMinimumWidth(self.WIDTH)
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        t = theme.current()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 14, 14)
        lay.setSpacing(8)

        # row 1: icon in the project colour, name, pin / star
        top = QHBoxLayout()
        top.setSpacing(10)
        self.icon = IconCircle(project.icon, project.color, 20)
        top.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignVCenter)
        self.title = ElidedLabel(project.name, mode=Qt.TextElideMode.ElideRight)
        self.title.setFont(theme.ui_font(t.font_size + 1, 600))
        top.addWidget(self.title, 1)
        self.pin_btn = IconButton("fa5s.thumbtack", "Pin", size=14,
                                  color=t.text if project.pinned else t.text_faint)
        self.pin_btn.clicked.connect(lambda: self.pin_requested.emit(self.project))
        top.addWidget(self.pin_btn)
        self.fav_btn = IconButton("fa5s.star", "Favourite", size=14,
                                  color=t.warning if project.favorite else t.text_faint)
        self.fav_btn.clicked.connect(lambda: self.favorite_requested.emit(self.project))
        top.addWidget(self.fav_btn)
        lay.addLayout(top)

        # row 2: client · job number (or description)
        sub = " · ".join(x for x in (project.client, project.job_number) if x) or project.description or " "
        self.subtitle = ElidedLabel(sub, mode=Qt.TextElideMode.ElideRight)
        self.subtitle.setObjectName("muted")
        lay.addWidget(self.subtitle)

        # row 3: tags
        tags = QHBoxLayout()
        tags.setSpacing(6)
        for tag in project.tags[:3]:
            tags.addWidget(_tag_chip(tag))
        if len(project.tags) > 3:
            tags.addWidget(_tag_chip(f"+{len(project.tags) - 3}"))
        tags.addStretch(1)
        lay.addLayout(tags)
        lay.addStretch(1)

        # row 4: health
        meta = QHBoxLayout()
        meta.setSpacing(8)
        self.health_dot, self.meta = _health_line(meta)
        self.meta.setText(f"{len(project.enabled_items)}/{len(project.items)} items · {relative_time(project.last_opened)}")
        lay.addLayout(meta)

        # row 5: Open (secondary), launch sets, more
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.launch_btn = Button("Open", "fa5s.play")
        self.launch_btn.clicked.connect(lambda: self.launch_requested.emit(self.project))
        actions.addWidget(self.launch_btn, 1)
        if project.launch_sets:
            self.sets_btn = IconButton("fa5s.layer-group", "Launch sets", size=16)
            self.sets_btn.clicked.connect(self._show_sets)
            actions.addWidget(self.sets_btn)
        self.more_btn = IconButton("fa5s.ellipsis-h", "More", size=16)
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
            self.health_dot.set_color(t.text_faint)
            self.health_dot.setToolTip("Checking paths…")
            return
        problems = health.problems
        if not problems:
            self.health_dot.set_color(t.success)
            self.health_dot.setToolTip("All paths reachable")
        else:
            offline = any(p.status == "offline" for p in problems)
            self.health_dot.set_color(t.danger if offline else t.warning)
            self.health_dot.setToolTip(f"{len(problems)} item(s) need attention")


class ProjectRow(QFrame):
    """Compact list representation: a 52 px card row."""

    launch_requested = Signal(object)
    open_requested = Signal(object)
    menu_requested = Signal(object, object)

    def __init__(self, project: M.Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(52)
        t = theme.current()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 10, 0)
        lay.setSpacing(12)
        lay.addWidget(IconCircle(project.icon, project.color, 18), 0, Qt.AlignmentFlag.AlignVCenter)
        name = QLabel(project.name)
        name.setFont(theme.ui_font(t.font_size, 600))
        lay.addWidget(name)
        sub = " · ".join(x for x in (project.client, project.job_number) if x) or project.description
        sl = ElidedLabel(sub or plural(len(project.items), "item"), mode=Qt.TextElideMode.ElideRight)
        sl.setObjectName("muted")
        lay.addWidget(sl, 1)
        for tag in project.tags[:2]:
            lay.addWidget(_tag_chip(tag))
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        self.health_dot, meta = _health_line(meta_row)
        meta.setText(f"{len(project.enabled_items)}/{len(project.items)} · {relative_time(project.last_opened)}")
        meta.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(meta_row)
        if project.pinned:
            pin = QLabel()
            pin.setPixmap(icons.pixmap("fa5s.thumbtack", 14, t.text_muted))
            pin.setToolTip("Pinned")
            lay.addWidget(pin)
        b = Button("Open", "fa5s.play")
        b.clicked.connect(lambda: self.launch_requested.emit(self.project))
        lay.addWidget(b)
        more = IconButton("fa5s.ellipsis-h", "More", size=16)
        more.clicked.connect(lambda: self.menu_requested.emit(self.project, more.mapToGlobal(more.rect().bottomLeft())))
        lay.addWidget(more)
        self.set_health(None)

    def set_health(self, health: ProjectHealth | None) -> None:
        t = theme.current()
        if health is None:
            self.health_dot.set_color(t.text_faint)
        elif not health.problems:
            self.health_dot.set_color(t.success)
        else:
            offline = any(p.status == "offline" for p in health.problems)
            self.health_dot.set_color(t.danger if offline else t.warning)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        # Single click opens the detail page; launching is the Open button's job.
        if e.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit(self.project)
        super().mouseReleaseEvent(e)


class KpiStrip(QFrame):
    """One card divided by 1 px rules into equal columns: label over value.

    ``items`` are ``(label, value)`` or ``(label, value, window)`` tuples; the
    optional window ("today", "vs last week") is a faint third line.
    """

    def __init__(self, items: list[tuple], parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        t = theme.current()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.values: list[QLabel] = []
        for i, item in enumerate(items):
            lbl, val = item[0], item[1]
            window = item[2] if len(item) > 2 else ""
            if i:
                rule = QFrame()
                rule.setObjectName("vrule")
                rule.setFixedWidth(1)
                rule.setStyleSheet(f"QFrame#vrule {{ background-color: {t.border}; border: none; }}")
                lay.addWidget(rule)
            col = QWidget()
            cl = QVBoxLayout(col)
            cl.setContentsMargins(t.pad, t.pad - 4, t.pad, t.pad - 4)
            cl.setSpacing(2)
            lab = QLabel(lbl)
            lab.setObjectName("muted")
            lab.setFont(theme.ui_font(9, 400))
            cl.addWidget(lab)
            v = kpi_value_label(val)
            self.values.append(v)
            cl.addWidget(v)
            if window:
                w = QLabel(window)
                w.setObjectName("faint")
                cl.addWidget(w)
            cl.addStretch(1)
            lay.addWidget(col, 1)

    def set_values(self, values: list[str]) -> None:
        for lbl, v in zip(self.values, values, strict=False):
            lbl.setText(v)


class StatTile(QFrame):
    """Kept for compatibility: a single label-over-value card (no icon, no colour).

    New code should use ``KpiStrip``.  ``icon_name`` and ``color`` are accepted
    and ignored so existing callers keep working.
    """

    def __init__(self, title: str, value: str, icon_name: str = "", color: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        t = theme.current()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.pad, t.pad - 4, t.pad, t.pad - 4)
        lay.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("muted")
        self.title.setFont(theme.ui_font(9, 400))
        lay.addWidget(self.title)
        self.value = kpi_value_label(value)
        lay.addWidget(self.value)
        self.setMinimumWidth(150)

    def set_value(self, v: str) -> None:
        self.value.setText(v)
