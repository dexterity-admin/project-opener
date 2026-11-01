"""The launch sheet: live feedback while a project opens.

One frameless surface centred over the content area (never over the sidebar),
titled "Opening <project>", with one row per item whose status pill changes as
the launcher reports it: Opening… → Opened / Not found / Server offline /
Undefined variable / Skipped / Failed.  The footer counts, times the launch
and offers the project's launch sets.  When every item opened the sheet
closes itself after a moment; otherwise it stays until dismissed (Esc or ×).

It floats, so like the toast it carries the one drop shadow.  It is not a
notification: it shows even when notifications are off.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from project_opener.core import models as M
from project_opener.core.launcher import LaunchReport, LaunchResult
from project_opener.core.search import item_icon
from project_opener.ui import icons, theme
from project_opener.ui.widgets.common import Badge, ElidedLabel, IconButton, hline

WIDTH = 640
AUTO_CLOSE_MS = 2500
STEP_W = 22
GROUP_H = 24
MAX_HEIGHT_FRACTION = 0.6

# LaunchResult.code -> (pill level, pill text); the same levels and words as the project page
STATUS_PILLS = {
    "opened": ("ok", "Opened"),
    "missing": ("warn", "Not found"),
    "offline": ("bad", "Server offline"),
    "variable": ("warn", "Undefined variable"),
    "skipped": ("neutral", "Skipped"),
    "failed": ("bad", "Failed"),
}
PENDING_PILL = ("neutral", "Opening…")


def pill_for(result: LaunchResult) -> tuple[str, str]:
    """(level, text) of the status pill for one launcher result."""
    return STATUS_PILLS.get(result.code or result.status, STATUS_PILLS["failed"])


def footer_text(results: list[LaunchResult | None], elapsed: float) -> tuple[str, str]:
    """("4 opened", " · 2 not opened · 1.8 s"): the bold part and the rest.

    "Not opened" is the count of items that failed, were not found, whose server
    was offline or whose variable is undefined; "skipped" only counts items the
    launcher skipped on purpose (``code == "skipped"``), the sheet's own word for them."""
    done = [r for r in results if r is not None]
    opened = sum(1 for r in done if r.code == "opened")
    skipped = sum(1 for r in done if r.code == "skipped")
    not_opened = len(done) - opened - skipped
    tail = f" · {not_opened} not opened" if not_opened else ""
    tail += f" · {skipped} skipped" if skipped else ""
    if elapsed >= 0.1:
        tail += f" · {elapsed:.1f} s"
    return f"{opened} opened", tail


class _Bar(QWidget):
    """A quiet 3 px progress line under the heading (accent on surface_3)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self.setFixedHeight(3)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, v: float) -> None:
        self._value = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.surface_3))
        p.drawRoundedRect(self.rect(), 1.5, 1.5)
        w = int(self.width() * self._value)
        if w > 0:
            p.setBrush(QColor(t.accent))
            p.drawRoundedRect(QRect(0, 0, w, self.height()), 1.5, 1.5)
        p.end()


class _Row(QWidget):
    def __init__(self, item: M.Item, shown_path: str, height: int, parent=None, step: int = 0):
        super().__init__(parent)
        t = theme.current()
        self.setObjectName("launchRow")
        self.setStyleSheet("#launchRow { background: transparent; }")
        self.setFixedHeight(height)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        num = QLabel(str(step) if step else "")      # the step in launch order: the set is the trade's checklist
        num.setObjectName("faint")
        num.setFont(theme.ui_font(t.font_size, 500, tabular=True))
        num.setFixedWidth(STEP_W)
        num.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(num)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(item_icon(item), 16, t.text_muted))
        ic.setFixedWidth(20)
        lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(0)
        name = ElidedLabel(item.display_name, mode=Qt.TextElideMode.ElideRight)
        name.setFont(theme.ui_font(weight=500))
        col.addWidget(name)
        path = ElidedLabel(shown_path, mode=Qt.TextElideMode.ElideMiddle)
        path.setObjectName("faint")
        col.addWidget(path)
        lay.addLayout(col, 1)
        self.pill = Badge("", level="neutral")
        self.pill.hide()                      # queued: no pill until the launcher reaches this item
        lay.addWidget(self.pill, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_pending(self) -> None:
        self._set(*PENDING_PILL, tooltip="")

    def set_result(self, result: LaunchResult) -> None:
        level, text = pill_for(result)
        tip = result.message if result.code in ("failed", "offline", "variable", "missing") else ""
        self._set(level, text, tooltip=tip)

    def _set(self, level: str, text: str, tooltip: str) -> None:
        self.pill.setText(text)
        self.pill.set_level(level)
        self.pill.setToolTip(tooltip)
        self.pill.adjustSize()
        self.pill.show()


class LaunchSheet(QFrame):
    """Hosted by the main window; ``begin(run)`` shows it for a ``LaunchRun``."""

    set_requested = Signal(object, object)   # project, launch set
    closed = Signal()

    def __init__(self, host: QWidget, area_fn: Callable[[], QRect], compact: bool = False,
                 auto_close_ms: int = AUTO_CLOSE_MS):
        super().__init__(host)
        self.host = host
        self.area_fn = area_fn
        self.compact = compact
        self.auto_close_ms = auto_close_ms
        self.run = None
        self.rows: list[_Row] = []
        self._set_buttons: list[QPushButton] = []
        self._close_token = 0
        t = theme.current()
        self.setObjectName("launchSheet")
        self.setStyleSheet(
            f"QFrame#launchSheet {{ background-color: {t.surface}; border: 1px solid {t.border}; border-radius: {t.radius}px; }}")
        self.setFixedWidth(WIDTH)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        pad = 20 if not compact else 16
        lay = QVBoxLayout(self)
        lay.setContentsMargins(pad, pad - 4, pad, pad - 6)
        lay.setSpacing(0)

        head = QHBoxLayout()
        head.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = ElidedLabel("", mode=Qt.TextElideMode.ElideRight)
        self.title.setFont(theme.ui_font(t.font_size + 2, 600))
        titles.addWidget(self.title)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("muted")
        self.subtitle.setFont(theme.ui_font(tabular=True))
        titles.addWidget(self.subtitle)
        head.addLayout(titles, 1)
        self.close_btn = IconButton("fa5s.times", "Close (Esc)", size=14, color=t.text_faint)
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.close_btn.clicked.connect(self.dismiss)
        head.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)
        lay.addSpacing(12)
        self.bar = _Bar()
        lay.addWidget(self.bar)
        lay.addSpacing(6)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_body = QWidget()
        self.list_body.setObjectName("launchList")
        self.list_body.setStyleSheet("#launchList { background: transparent; }")
        self.list_lay = QVBoxLayout(self.list_body)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(0)
        self.scroll.setWidget(self.list_body)
        lay.addWidget(self.scroll)

        lay.addSpacing(10)
        foot = QHBoxLayout()
        foot.setSpacing(0)
        self.foot_main = QLabel("")
        self.foot_main.setFont(theme.ui_font(t.font_size, 600, tabular=True))
        foot.addWidget(self.foot_main)
        self.foot_rest = QLabel("")
        self.foot_rest.setObjectName("muted")
        self.foot_rest.setFont(theme.ui_font(tabular=True))
        foot.addWidget(self.foot_rest)
        foot.addStretch(1)
        self.sets_label = QLabel("Launch sets")
        self.sets_label.setObjectName("faint")
        foot.addWidget(self.sets_label)
        self.sets_lay = QHBoxLayout()
        self.sets_lay.setContentsMargins(6, 0, 0, 0)
        self.sets_lay.setSpacing(4)
        foot.addLayout(self.sets_lay)
        lay.addLayout(foot)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(t.shadow))
        self.setGraphicsEffect(shadow)
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc.activated.connect(self.dismiss)
        self.hide()

    # ------------------------------------------------------------- lifecycle
    def begin(self, run, localise: Callable[[str], str] | None = None) -> None:
        """Show the sheet for ``run`` (an ``AppContext.LaunchRun``), replacing any earlier launch."""
        self._unbind()
        self.run = run
        self._close_token += 1
        project = run.project
        self.title.setText(f"Opening {project.title}")
        parts = [f"{len(run.items)} item{'s' if len(run.items) != 1 else ''}"]
        if run.set_name:
            parts.append(run.set_name)
        if project.job_number.strip() and project.client.strip():
            parts.append(project.client.strip())
        self.subtitle.setText(" · ".join(parts))
        self.bar.set_value(0.0)
        self._build_rows(run, localise or (lambda s: s))
        self._build_sets(project)
        self.foot_main.setText("")
        self.foot_rest.setText("Opening…")
        self._refresh_footer()
        run.item_started.connect(self._item_started)
        run.item_finished.connect(self._item_finished)
        run.finished.connect(self._finished)
        if run.done and run.report is not None:            # a run that already finished (replay)
            for i, r in enumerate(run.results):
                if r is not None:
                    self.rows[i].set_result(r)
            self._finished(run.report)
        self.reposition()
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def dismiss(self) -> None:
        if not self.isVisible():
            return
        self._close_token += 1
        self.hide()
        self.closed.emit()

    def reposition(self) -> None:
        """Centre over the content area; the list scrolls past ~60 % of the window height."""
        area = self.area_fn()
        chrome = self.layout().sizeHint().height() - self.scroll.sizeHint().height()
        rows_h = self.list_body.sizeHint().height()
        max_h = int(self.host.height() * MAX_HEIGHT_FRACTION) - chrome
        self.scroll.setFixedHeight(max(0, min(rows_h, max_h)))
        self.adjustSize()
        self.resize(WIDTH, self.layout().sizeHint().height())
        x = area.x() + (area.width() - self.width()) // 2
        y = area.y() + (area.height() - self.height()) // 2
        self.move(max(area.x(), x), max(area.y(), y))

    # -------------------------------------------------------------- content
    def _unbind(self) -> None:
        if self.run is not None:
            for sig, slot in ((self.run.item_started, self._item_started),
                              (self.run.item_finished, self._item_finished),
                              (self.run.finished, self._finished)):
                try:
                    sig.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        self.run = None

    def _build_rows(self, run, localise: Callable[[str], str]) -> None:
        while self.list_lay.count():
            it = self.list_lay.takeAt(0)
            if it.widget() is not None:
                it.widget().deleteLater()
        self.rows = []
        height = 40 if self.compact else 48
        show_groups = any(it.group for it in run.items)
        last_group = None
        for i, item in enumerate(run.items):
            group = item.group or ""
            if show_groups and group != last_group:
                gl = QLabel(group or "Ungrouped")
                gl.setObjectName("faint")
                gl.setFixedHeight(GROUP_H)
                gl.setContentsMargins(STEP_W + 10, 4, 0, 0)
                self.list_lay.addWidget(gl)
                last_group = group
            elif i:
                self.list_lay.addWidget(hline())
            row = _Row(item, localise(item.path), height, step=i + 1)
            self.rows.append(row)
            self.list_lay.addWidget(row)
        self.list_lay.addStretch(0)

    def _build_sets(self, project: M.Project) -> None:
        while self.sets_lay.count():
            it = self.sets_lay.takeAt(0)
            if it.widget() is not None:
                it.widget().deleteLater()
        self._set_buttons = []
        t = theme.current()
        for ls in project.launch_sets:
            b = QPushButton(ls.name)
            b.setObjectName("ghost")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(f"Open the {ls.name} launch set")
            b.setFont(theme.ui_font(t.font_size - 1, 500))
            b.setStyleSheet("QPushButton { min-height: 22px; max-height: 22px; padding: 0 10px; border-radius: 11px; }"
                            "QPushButton:focus { padding: 0 9px; }")
            b.clicked.connect(lambda _=False, s=ls: self.set_requested.emit(project, s))
            self.sets_lay.addWidget(b)
            self._set_buttons.append(b)
        self.sets_label.setVisible(bool(project.launch_sets))
        prev: QWidget = self.close_btn
        for b in self._set_buttons:
            QWidget.setTabOrder(prev, b)
            prev = b

    def _refresh_footer(self) -> None:
        if self.run is None:
            return
        main, rest = footer_text(self.run.results, self.run.elapsed)
        if not any(r is not None for r in self.run.results):
            self.foot_main.setText("")
            self.foot_rest.setText("Opening…")
            return
        self.foot_main.setText(main)
        self.foot_rest.setText(rest)

    # -------------------------------------------------------------- progress
    def _item_started(self, idx: int) -> None:
        if 0 <= idx < len(self.rows):
            self.rows[idx].set_pending()
            self.scroll.ensureWidgetVisible(self.rows[idx], 0, 8)

    def _item_finished(self, idx: int, result: LaunchResult) -> None:
        if 0 <= idx < len(self.rows):
            self.rows[idx].set_result(result)
        if self.run is not None and self.run.items:
            self.bar.set_value((idx + 1) / len(self.run.items))
        self._refresh_footer()

    def _finished(self, report: LaunchReport) -> None:
        self.bar.set_value(1.0)
        self._refresh_footer()
        if all(r.code == "opened" for r in report.results) and self.auto_close_ms > 0:
            token = self._close_token
            QTimer.singleShot(self.auto_close_ms, lambda: self._auto_dismiss(token))

    def _auto_dismiss(self, token: int) -> None:
        if token == self._close_token:          # not replaced or dismissed meanwhile
            self.dismiss()

    # -------------------------------------------------------------- keyboard
    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self.dismiss()
            return
        super().keyPressEvent(e)
