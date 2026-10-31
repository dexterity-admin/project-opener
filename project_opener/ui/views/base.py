"""Common page scaffold: scrollable content with a title row."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from project_opener.ui.context import AppContext
from project_opener.ui.widgets.common import label


class Page(QWidget):
    route = "page"

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.content = QVBoxLayout(self.body)
        self.content.setContentsMargins(28, 22, 28, 28)
        self.content.setSpacing(16)
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll)

    def title_row(self, title: str, subtitle: str = "", kicker: str = "") -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(2)
        if kicker:
            col.addWidget(label(kicker, "kicker"))
        self.title_label = label(title, "h1")
        col.addWidget(self.title_label)
        if subtitle:
            self.subtitle_label = label(subtitle, "muted", wrap=True)
            col.addWidget(self.subtitle_label)
        row.addLayout(col, 1)
        self.content.addLayout(row)
        return row

    def section(self, title: str, trailing: QWidget | None = None) -> QVBoxLayout:
        row = QHBoxLayout()
        row.addWidget(label(title.upper(), "eyebrow"))
        row.addStretch(1)
        if trailing:
            row.addWidget(trailing)
        self.content.addLayout(row)
        col = QVBoxLayout()
        col.setSpacing(10)
        self.content.addLayout(col)
        return col

    def panel(self) -> tuple[QFrame, QVBoxLayout]:
        f = QFrame()
        f.setObjectName("card")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        return f, lay

    # Hooks
    def on_show(self) -> None:
        """Called every time the page becomes visible."""

    def refresh(self) -> None:
        """Called when projects change."""


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())
