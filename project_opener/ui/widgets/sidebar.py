"""Collapsible navigation rail."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from project_opener import constants as C
from project_opener.ui import icons, theme
from project_opener.ui.widgets.common import Avatar, IconButton

NAV = [
    ("home", "Home", "fa5s.home"),
    ("projects", "Projects", "fa5s.th-large"),
    ("team", "Team Hub", "fa5s.users"),
    ("updates", "Updates", "fa5s.sync-alt"),
    ("settings", "Settings", "fa5s.sliders-h"),
]

EXPANDED = 228
COLLAPSED = 68


class Sidebar(QFrame):
    route_changed = Signal(str)
    new_project = Signal()
    palette_requested = Signal()
    profile_clicked = Signal()

    def __init__(self, user_label: str, collapsed: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._collapsed = collapsed
        self._buttons: dict[str, QPushButton] = {}
        self._labels: dict[str, str] = {}
        t = theme.current()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 14, 12, 14)
        lay.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(34, 34))
        logo.setFixedSize(34, 34)
        brand.addWidget(logo)
        self.brand_text = QWidget()
        bt = QVBoxLayout(self.brand_text)
        bt.setContentsMargins(0, 0, 0, 0)
        bt.setSpacing(0)
        name = QLabel(C.APP_NAME)
        name.setStyleSheet(f"font-weight: 800; font-size: {t.font_size + 2}pt; font-family: '{theme.display_font()}';")
        bt.addWidget(name)
        ver = QLabel(f"v{C.VERSION} · Dexterity")
        ver.setObjectName("faint")
        bt.addWidget(ver)
        brand.addWidget(self.brand_text, 1)
        self.collapse_btn = IconButton("fa5s.angle-double-left", "Collapse sidebar", size=13)
        self.collapse_btn.clicked.connect(self.toggle)
        brand.addWidget(self.collapse_btn)
        lay.addLayout(brand)
        lay.addSpacing(10)

        self.new_btn = QPushButton("  New project")
        self.new_btn.setObjectName("primary")
        self.new_btn.setIcon(icons.icon("fa5s.plus", t.accent_fg))
        self.new_btn.setIconSize(QSize(13, 13))
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.setFixedHeight(36)
        self.new_btn.clicked.connect(self.new_project.emit)
        lay.addWidget(self.new_btn)

        self.search_btn = QPushButton("  Search  ·  Ctrl+K")
        self.search_btn.setObjectName("nav")
        self.search_btn.setIcon(icons.icon("fa5s.search"))
        self.search_btn.setIconSize(QSize(14, 14))
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.clicked.connect(self.palette_requested.emit)
        lay.addWidget(self.search_btn)
        lay.addSpacing(8)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._inbox = 0
        for route, title, ic in NAV:
            b = QPushButton("  " + title)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setIcon(icons.icon(ic))
            b.setIconSize(QSize(15, 15))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(38)
            b.clicked.connect(lambda _=False, r=route: self.route_changed.emit(r))
            self.group.addButton(b)
            self._buttons[route] = b
            self._labels[route] = title
            lay.addWidget(b)
            if route == "team":
                # Count badge overlaid on the button so it survives collapse/expand.
                self.inbox_badge = QLabel(b)
                self.inbox_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.inbox_badge.setFixedHeight(18)
                self.inbox_badge.setMinimumWidth(18)
                self.inbox_badge.setStyleSheet(
                    f"background-color: {t.accent}; color: {t.accent_fg}; border-radius: 9px;"
                    f" font-size: {max(7, t.font_size - 2)}pt; font-weight: 700; padding: 0 5px;")
                self.inbox_badge.hide()
                b.installEventFilter(self)   # re-place the badge whenever the button resizes
        lay.addStretch(1)

        self.hub_dot = QLabel()
        self.hub_dot.setObjectName("faint")
        self.hub_dot.setWordWrap(True)
        lay.addWidget(self.hub_dot)

        prof = QFrame()
        prof.setObjectName("panel2")
        pl = QHBoxLayout(prof)
        pl.setContentsMargins(8, 8, 8, 8)
        pl.setSpacing(8)
        self.avatar = Avatar(user_label, 30, online=True)
        pl.addWidget(self.avatar)
        self.user_lbl = QLabel(user_label)
        self.user_lbl.setStyleSheet("font-weight: 600;")
        pl.addWidget(self.user_lbl, 1)
        prof.setCursor(Qt.CursorShape.PointingHandCursor)
        prof.mouseReleaseEvent = lambda e: self.profile_clicked.emit()  # type: ignore[assignment]
        self.profile = prof
        lay.addWidget(prof)

        self._anim = QPropertyAnimation(self, b"maximumWidth", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setMinimumWidth(COLLAPSED)
        self.setMaximumWidth(COLLAPSED if collapsed else EXPANDED)
        self._apply_collapsed(animate=False)

    # ------------------------------------------------------------- state
    def set_active(self, route: str) -> None:
        b = self._buttons.get(route)
        if b:
            b.setChecked(True)

    def set_user(self, label: str) -> None:
        self.user_lbl.setText(label)
        self.avatar.set_name(label)

    def set_hub_text(self, text: str, ok: bool) -> None:
        t = theme.current()
        dot = "●"
        color = t.success if ok else t.text_faint
        self.hub_dot.setText(f"<span style='color:{color}'>{dot}</span> {text}" if not self._collapsed else f"<span style='color:{color}'>{dot}</span>")
        self.hub_dot.setToolTip(text)

    def set_inbox_count(self, n: int) -> None:
        self._inbox = int(n or 0)
        self._place_badge()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._buttons.get("team") and event.type() == QEvent.Type.Resize:
            self._place_badge()
        return super().eventFilter(obj, event)

    def _place_badge(self) -> None:
        b = self._buttons["team"]
        badge = self.inbox_badge
        n = self._inbox
        if not n:
            badge.hide()
            b.setToolTip(self._labels["team"] if self._collapsed else "")
            return
        badge.setText(str(n) if not self._collapsed else "")
        badge.setFixedWidth(18 if self._collapsed else max(18, badge.fontMetrics().horizontalAdvance(str(n)) + 12))
        if self._collapsed:
            badge.setFixedSize(10, 10)
            badge.move(b.width() - 18, 8)
        else:
            badge.setFixedHeight(18)
            badge.move(b.width() - badge.width() - 10, (b.height() - 18) // 2)
        badge.setToolTip(f"{n} new in inbox")
        b.setToolTip(f"{self._labels['team']} · {n} new in inbox" if self._collapsed else f"{n} new in inbox")
        badge.show()
        badge.raise_()

    def toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._apply_collapsed(animate=True)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def _apply_collapsed(self, animate: bool) -> None:
        target = COLLAPSED if self._collapsed else EXPANDED
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self.width())
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.setMaximumWidth(target)
        self.brand_text.setVisible(not self._collapsed)
        self.user_lbl.setVisible(not self._collapsed)
        self.collapse_btn.refresh("fa5s.angle-double-right" if self._collapsed else "fa5s.angle-double-left")
        self.new_btn.setText("" if self._collapsed else "  New project")
        self.new_btn.setToolTip("New project  (Ctrl+N)" if self._collapsed else "")
        self.search_btn.setText("" if self._collapsed else "  Search  ·  Ctrl+K")
        for route, b in self._buttons.items():
            b.setText("" if self._collapsed else "  " + self._labels[route])
            b.setToolTip(self._labels[route] if self._collapsed else "")
        self.profile.setToolTip(self.user_lbl.text() if self._collapsed else "")
        self._place_badge()
