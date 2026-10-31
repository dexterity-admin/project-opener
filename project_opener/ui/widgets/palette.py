"""Command palette (Ctrl+K): fuzzy search over projects, launch sets, items and actions."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
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
from project_opener.ui.widgets.common import Badge, ElidedLabel


class _HitRow(QWidget):
    def __init__(self, hit: Hit, parent=None):
        super().__init__(parent)
        t = theme.current()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(10)
        ic = QLabel()
        color = {"project": hit.project.color if hit.project else t.accent, "set": t.info, "item": t.text_muted,
                 "action": t.accent}.get(hit.kind, t.text_muted)
        ic.setPixmap(icons.pixmap(hit.icon, 16, color))
        ic.setFixedWidth(20)
        lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(0)
        title = QLabel(hit.title)
        title.setStyleSheet("font-weight: 600;")
        col.addWidget(title)
        sub = ElidedLabel(hit.subtitle, mode=Qt.TextElideMode.ElideMiddle)
        sub.setObjectName("faint")
        col.addWidget(sub)
        lay.addLayout(col, 1)
        kind_label = {"project": "Project", "set": "Launch set", "item": "Item", "action": "Action"}.get(hit.kind, "")
        lay.addWidget(Badge(kind_label, color))


class CommandPalette(QDialog):
    hit_chosen = Signal(object)   # Hit

    def __init__(self, parent: QWidget, projects_fn, actions: list[tuple[str, str, str]]):
        super().__init__(parent)
        self._projects_fn = projects_fn
        self._actions = actions
        self._hits: list[Hit] = []
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        t = theme.current()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("paletteFrame")
        frame.setStyleSheet(f"QFrame#paletteFrame {{ background-color: {t.surface}; border: 1px solid {t.border_strong}; border-radius: 14px; }}")
        outer.addWidget(frame)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("fa5s.search", 16, t.text_muted))
        row.addWidget(ic)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Search projects, launch sets, files, actions…   (↑↓ to move, Enter to open, Esc to close)")
        self.edit.setStyleSheet(f"QLineEdit {{ border: none; background: transparent; font-size: {t.font_size + 3}pt; padding: 6px; }}")
        self.edit.textChanged.connect(self._refresh)
        self.edit.installEventFilter(self)
        row.addWidget(self.edit, 1)
        hint = Badge("Ctrl+K", t.text_faint)
        row.addWidget(hint)
        lay.addLayout(row)
        self.list = QListWidget()
        self.list.setStyleSheet("QListWidget { border: none; background: transparent; }")
        self.list.setUniformItemSizes(False)
        self.list.itemActivated.connect(self._activate)
        self.list.itemClicked.connect(self._activate)
        lay.addWidget(self.list, 1)
        self.footer = QLabel("")
        self.footer.setObjectName("faint")
        lay.addWidget(self.footer)
        self.resize(680, 460)

    def open_at(self, parent: QWidget) -> None:
        self.edit.clear()
        self._refresh("")
        g = parent.geometry()
        self.move(g.center().x() - self.width() // 2, g.top() + 90)
        self.show()
        self.edit.setFocus()

    def _refresh(self, text: str) -> None:
        self._hits = search_everything(text, self._projects_fn(), self._actions, limit=40)
        self.list.clear()
        for hit in self._hits:
            item = QListWidgetItem()
            row = _HitRow(hit)
            item.setSizeHint(QSize(0, 48))
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
        if self._hits:
            self.list.setCurrentRow(0)
        self.footer.setText(f"{len(self._hits)} result(s)" if text else "Type to search · recent and pinned projects first")

    def _activate(self, item: QListWidgetItem) -> None:
        row = self.list.row(item)
        if 0 <= row < len(self._hits):
            self.hit_chosen.emit(self._hits[row])
            self.accept()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.edit and event.type() == QEvent.Type.KeyPress:
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
