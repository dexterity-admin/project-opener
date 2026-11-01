"""Command palette (Ctrl+K): fuzzy search over projects, launch sets, items and actions."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from project_opener.core.search import Hit, search_everything
from project_opener.ui import icons, theme
from project_opener.ui.widgets.common import ElidedLabel

SHADOW_PAD = 40          # room around the frame for the drop shadow
ROW_H = 44


class _HitRow(QWidget):
    def __init__(self, hit: Hit, parent=None):
        super().__init__(parent)
        t = theme.current()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(12)
        ic = QLabel()
        color = hit.project.color if (hit.kind == "project" and hit.project) else t.text_muted
        ic.setPixmap(icons.pixmap(hit.icon, 16, color))
        ic.setFixedSize(16, 16)
        lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(0)
        title = ElidedLabel(hit.title, mode=Qt.TextElideMode.ElideRight)
        title.setFont(theme.ui_font(t.font_size, 500))
        col.addWidget(title)
        if hit.subtitle:
            sub = ElidedLabel(hit.subtitle, mode=Qt.TextElideMode.ElideMiddle)
            sub.setObjectName("muted")
            sub.setFont(theme.ui_font(9))
            col.addWidget(sub)
        lay.addLayout(col, 1)
        kind_label = {"project": "Project", "set": "Launch set", "item": "Item", "action": "Action"}.get(hit.kind, "")
        kind = QLabel(kind_label)
        kind.setObjectName("faint")
        kind.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(kind)


class CommandPalette(QDialog):
    hit_chosen = Signal(object)   # Hit

    def __init__(self, parent: QWidget, projects_fn, actions: list[tuple[str, str, str]]):
        super().__init__(parent)
        self._projects_fn = projects_fn
        self._actions = actions
        self._hits: list[Hit] = []
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        t = theme.current()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_PAD, SHADOW_PAD, SHADOW_PAD, SHADOW_PAD)
        frame = QFrame()
        frame.setObjectName("paletteFrame")
        frame.setStyleSheet(
            f"QFrame#paletteFrame {{ background-color: {t.surface}; border: 1px solid {t.border}; border-radius: {t.radius}px; }}")
        shadow = QGraphicsDropShadowEffect(frame)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(t.shadow))
        frame.setGraphicsEffect(shadow)
        outer.addWidget(frame)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 12, 12, 10)
        lay.setSpacing(8)

        field = QFrame()
        field.setObjectName("paletteField")
        field.setFixedHeight(40)
        field.setStyleSheet(
            f"QFrame#paletteField {{ background-color: {t.surface}; border: 1px solid {t.border_strong};"
            f" border-radius: {t.radius_sm}px; }}"
            f"QFrame#paletteField[focused=\"true\"] {{ border: 2px solid {t.accent}; }}")
        row = QHBoxLayout(field)
        row.setContentsMargins(12, 0, 10, 0)
        row.setSpacing(8)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("fa5s.search", 16, t.text_muted))
        ic.setFixedSize(16, 16)
        row.addWidget(ic)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Search projects, launch sets, items, actions")
        self.edit.setStyleSheet("QLineEdit { border: none; background: transparent; padding: 0; min-height: 0; }"
                                "QLineEdit:focus { border: none; padding: 0; }")
        self.edit.textChanged.connect(self._refresh)
        self.edit.installEventFilter(self)
        row.addWidget(self.edit, 1)
        self._field = field
        lay.addWidget(field)

        self.list = QListWidget()
        self.list.setStyleSheet(
            "QListWidget { border: none; background: transparent; padding: 0; }"
            f"QListWidget::item {{ padding: 0; border-radius: {t.radius_sm}px; }}"
            f"QListWidget::item:selected, QListWidget::item:hover {{ background-color: {t.surface_2}; }}")
        self.list.setUniformItemSizes(True)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.itemActivated.connect(self._activate)
        self.list.itemClicked.connect(self._activate)
        lay.addWidget(self.list, 1)

        foot = QHBoxLayout()
        self.footer = QLabel("")
        self.footer.setObjectName("faint")
        foot.addWidget(self.footer, 1)
        hints = QLabel("↑↓ navigate · Enter open · Esc close")
        hints.setObjectName("faint")
        foot.addWidget(hints)
        lay.addLayout(foot)
        self.resize(680 + 2 * SHADOW_PAD, 460 + 2 * SHADOW_PAD)

    def open_at(self, parent: QWidget) -> None:
        self.edit.clear()
        self._refresh("")
        g = parent.geometry()
        self.move(g.center().x() - self.width() // 2, g.top() + 90 - SHADOW_PAD)
        self.show()
        self.edit.setFocus()

    def _set_focused(self, on: bool) -> None:
        self._field.setProperty("focused", "true" if on else "false")
        self._field.style().unpolish(self._field)
        self._field.style().polish(self._field)

    def _refresh(self, text: str) -> None:
        self._hits = search_everything(text, self._projects_fn(), self._actions, limit=40)
        self.list.clear()
        for hit in self._hits:
            item = QListWidgetItem()
            row = _HitRow(hit)
            item.setSizeHint(QSize(0, ROW_H))
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
        if self._hits:
            self.list.setCurrentRow(0)
        n = len(self._hits)
        self.footer.setText((f"{n} result" + ("" if n == 1 else "s")) if text else "Recent and pinned projects first")

    def _activate(self, item: QListWidgetItem) -> None:
        row = self.list.row(item)
        if 0 <= row < len(self._hits):
            self.hit_chosen.emit(self._hits[row])
            self.accept()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.edit:
            if event.type() == QEvent.Type.FocusIn:
                self._set_focused(True)
            elif event.type() == QEvent.Type.FocusOut:
                self._set_focused(False)
            elif event.type() == QEvent.Type.KeyPress:
                assert isinstance(event, QKeyEvent)
                key = event.key()
                if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                    row = self.list.currentRow()
                    row = min(self.list.count() - 1, row + 1) if key == Qt.Key.Key_Down else max(0, row - 1)
                    self.list.setCurrentRow(row)
                    return True
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    cur = self.list.currentItem()
                    if cur:
                        self._activate(cur)
                    return True
                if key == Qt.Key.Key_Escape:
                    self.reject()
                    return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(e)
