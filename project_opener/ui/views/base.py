"""Common page scaffold: scrollable content with a title row.

Also hosts the small compatibility shims the views code against while the
widget layer (ui/widgets) is being rewritten in parallel: ``badge`` (status
pills by level), ``KpiStrip`` (one divided card), ``icon_container`` and
``kpi_value_label``.  Each prefers the real widget and falls back to a local
equivalent when the import or signature is not there yet.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from project_opener.ui import theme
from project_opener.ui.context import AppContext
from project_opener.ui.widgets.common import Badge, IconCircle, label

PAGE_MARGINS = (32, 28, 32, 32)
GAP = 16


class Page(QWidget):
    route = "page"

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._bound: list[tuple[object, object]] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.content = QVBoxLayout(self.body)
        self.content.setContentsMargins(*PAGE_MARGINS)
        self.content.setSpacing(GAP)
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll)

    def title_row(self, title: str, subtitle: str = "", kicker: str = "") -> QHBoxLayout:
        """Page title (24 px 600) with one optional grey line under it.

        ``kicker`` is accepted for compatibility and ignored: no eyebrow is
        ever drawn (DESIGN.md).  The subtitle is the finding or the scope,
        never a description of the interface.
        """
        del kicker
        row = QHBoxLayout()
        row.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(4)
        self.title_label = label(title, "h1")
        col.addWidget(self.title_label)
        self.subtitle_label = label(subtitle, "muted", wrap=True)
        self.subtitle_label.setFont(theme.ui_font(tabular=True))
        self.subtitle_label.setVisible(bool(subtitle))
        col.addWidget(self.subtitle_label)
        row.addLayout(col, 1)
        self.content.addLayout(row)
        return row

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))

    def section(self, title: str, trailing: QWidget | None = None) -> QVBoxLayout:
        """A sentence-case section heading (16 px 600) followed by a column."""
        row = QHBoxLayout()
        row.addWidget(label(title, "section"))
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
        pad = theme.current().pad
        lay = QVBoxLayout(f)
        lay.setContentsMargins(pad, pad, pad, pad)
        lay.setSpacing(10)
        return f, lay

    # Signal plumbing -------------------------------------------------
    def bind(self, signal, slot) -> None:
        """Connect a context signal and remember it so dispose() can undo it.

        Lambda slots are not disconnected automatically when the page is
        deleted (MainWindow.retheme rebuilds every page), so every page must
        connect through here.
        """
        signal.connect(slot)
        self._bound.append((signal, slot))

    def dispose(self) -> None:
        for signal, slot in self._bound:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._bound.clear()

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


def section_label(text: str) -> QLabel:
    """Sentence-case heading used inside panels (same role as Page.section)."""
    return label(text, "section")


def make_transparent(w: QWidget) -> None:
    """Stop a container painting the page ground, without touching its children.

    The selector is scoped to the widget itself: an unscoped ``background:
    transparent`` on a parent cascades to every child and would erase the
    filled primary button or a pill inside it.
    """
    w.setObjectName("transparent_row")
    w.setStyleSheet("#transparent_row { background: transparent; }")


def row_widget(height: int = 44) -> tuple[QWidget, QHBoxLayout]:
    """A fixed-height, transparent row for lists inside cards.

    A bare QWidget paints the page ground (QSS ``QWidget { background }``),
    which shows as a grey band on a white card; rows must be transparent.
    """
    w = QWidget()
    w.setFixedHeight(height)
    make_transparent(w)
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    return w, lay


# ------------------------------------------------------------- compat shims
def badge(text: str, level: str = "neutral") -> QLabel:
    """A status pill by level (ok | warn | bad | info | neutral).

    Uses ``common.Badge(text, level=...)`` when the widget layer provides it;
    until then paints the same pill from ``theme.pill_colors``.
    """
    try:
        return Badge(text, level=level)
    except TypeError:
        b = Badge(text)
        t = theme.current()
        bg, ink = theme.pill_colors(t, level)
        b.setStyleSheet(f"background-color: {bg}; color: {ink}; border-radius: 10px; padding: 2px 9px;"
                        f" font-size: {t.font_size - 1}pt; font-weight: 500;")
        return b


def icon_container(icon: str, color: str, size: int) -> QWidget:
    """The one tinted icon container in the app (project detail header)."""
    try:
        return IconCircle(icon, color, size, container=True)
    except TypeError:
        return IconCircle(icon, color, size)


def kpi_value_label(text: str) -> QLabel:
    try:
        from project_opener.ui.widgets.common import kpi_value_label as _kpi
        return _kpi(text)
    except ImportError:
        lbl = label(text, "kpi")
        lbl.setFont(theme.ui_font(theme.current().font_size + 8, 400, tabular=True))
        return lbl


try:
    from project_opener.ui.widgets.cards import KpiStrip
except ImportError:  # widget layer not landed yet: one divided card, label over value
    class KpiStrip(QFrame):  # type: ignore[no-redef]
        def __init__(self, items: list[tuple[str, str]], parent=None):
            super().__init__(parent)
            self.setObjectName("card")
            self._values: list[QLabel] = []
            lay = QHBoxLayout(self)
            pad = theme.current().pad
            lay.setContentsMargins(pad, pad - 4, pad, pad - 4)
            lay.setSpacing(0)
            for i, (title, value) in enumerate(items):
                if i:
                    rule = QFrame()
                    rule.setFixedWidth(1)
                    rule.setStyleSheet(f"background-color: {theme.current().border};")
                    lay.addWidget(rule)
                    lay.addSpacing(pad)
                col = QVBoxLayout()
                col.setSpacing(2)
                col.addWidget(label(title, "faint"))
                v = kpi_value_label(value)
                self._values.append(v)
                col.addWidget(v)
                lay.addLayout(col, 1)
                if i < len(items) - 1:
                    lay.addSpacing(pad)

        def set_values(self, values: list[str]) -> None:
            for lbl, v in zip(self._values, values, strict=False):
                lbl.setText(v)
