"""Flow layout (wrapping grid) with uniform animated reflow on resize."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin: int = 0, h_spacing: int = 14, v_spacing: int = 14,
                 justify: bool = False, max_columns: int = 4):
        """``justify``: items share the row width in equal columns (the column
        count comes from the widest minimum width), so a row of cards always
        ends on the canvas edge and a lone card does not float in empty ground."""
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h = h_spacing
        self._v = v_spacing
        self._justify = justify
        self._max_cols = max_columns
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        while self.count():
            self.takeAt(0)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def clear(self) -> None:
        while self.count():
            item = self.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effective.x()
        y = effective.y()
        line_h = 0
        visible = [it for it in self._items
                   if not (it.widget() is not None and it.widget().isHidden())]
        col_w = None
        if self._justify and visible:
            min_w = max(max(it.minimumSize().width(), 1) for it in visible)
            avail = max(effective.width(), min_w)
            cols = max(1, min(self._max_cols, (avail + self._h) // (min_w + self._h)))
            col_w = (avail - (cols - 1) * self._h) // cols
        for item in visible:
            hint = item.sizeHint()
            if col_w is not None:
                hint = QSize(col_w, hint.height())
            next_x = x + hint.width() + self._h
            if next_x - self._h > effective.right() + 1 and line_h > 0:
                x = effective.x()
                y += line_h + self._v
                next_x = x + hint.width() + self._h
                line_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y() + m.bottom()
