"""Non-blocking toast notifications stacked in the window's bottom-right.

A toast floats, so it is the one card with a shadow.  Qt allows one graphics
effect per widget and drops a child's effect under a parent's, so the arrival
motion is a short rise (not a fade), which keeps the shadow real.
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from project_opener.ui import icons, theme

LEVEL_ICONS = {"info": "fa5s.info-circle", "success": "fa5s.check-circle", "warning": "fa5s.exclamation-triangle",
               "error": "fa5s.times-circle"}
WIDTH = 380
WIDTH_WITH_ACTION = 440


class Toast(QFrame):
    closed = Signal(object)
    action_clicked = Signal()

    def __init__(self, title: str, body: str = "", level: str = "info", action: str = "", parent=None, timeout: int = 4500):
        super().__init__(parent)
        t = theme.current()
        color = {"info": t.info, "success": t.success, "warning": t.warning, "error": t.danger}.get(level, t.info)
        self.setObjectName("toast")
        self.setStyleSheet(
            f"QFrame#toast {{ background-color: {t.surface}; border: 1px solid {t.border}; border-radius: 14px; }}")
        self.setFixedWidth(WIDTH_WITH_ACTION if action else WIDTH)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 12, 14)
        lay.setSpacing(12)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(LEVEL_ICONS.get(level, "fa5s.info-circle"), 16, color))
        ic.setFixedSize(16, 20)
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        tl = QLabel(title)
        tl.setFont(theme.ui_font(t.font_size, 600))
        tl.setWordWrap(True)
        text.addWidget(tl)
        if body:
            bl = QLabel(body)
            bl.setObjectName("muted")
            bl.setWordWrap(True)
            text.addWidget(bl)
        lay.addLayout(text, 1)
        if action:
            btn = QPushButton(action)
            btn.setObjectName("primary")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(self.action_clicked.emit)
            btn.clicked.connect(self.dismiss)
            lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
        close = QPushButton()
        close.setObjectName("icon")
        close.setIcon(icons.icon("fa5s.times", t.text_faint))
        close.setToolTip("Dismiss")
        close.setFixedSize(24, 24)
        close.clicked.connect(self.dismiss)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        # Wrapped labels report a height only once the width is known.
        lay.activate()
        self.setFixedHeight(max(52, lay.heightForWidth(self.width()) if lay.hasHeightForWidth() else lay.sizeHint().height()))
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(t.shadow))
        self.setGraphicsEffect(shadow)
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._closing = False
        if timeout > 0:
            QTimer.singleShot(timeout, self.dismiss)

    def appear(self) -> None:
        target = self.pos()
        self.move(target + QPoint(0, 8))
        self.show()
        self._anim.stop()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(target)
        self._anim.start()

    def dismiss(self) -> None:
        if not self.isVisible() or self._closing:
            return
        self._closing = True
        self._anim.stop()
        self._anim.setDuration(150)
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(self.pos() + QPoint(0, 8))
        self._anim.finished.connect(self._done)
        self._anim.start()

    def _done(self) -> None:
        self.hide()
        self.closed.emit(self)
        self.deleteLater()


class ToastManager(QWidget):
    def __init__(self, host: QWidget):
        super().__init__(host)
        self.host = host
        self._toasts: list[Toast] = []
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.hide()

    def show_toast(self, title: str, body: str = "", level: str = "info", action: str = "", on_action=None,
                   timeout: int = 4500) -> Toast:
        toast = Toast(title, body, level, action, parent=self.host, timeout=timeout)
        if on_action:
            toast.action_clicked.connect(on_action)
        toast.closed.connect(self._remove)
        self._toasts.append(toast)
        toast.adjustSize()
        self._relayout()
        toast.raise_()
        toast.appear()
        return toast

    def _remove(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        self._relayout()

    def _relayout(self) -> None:
        margin = 24
        y = self.host.height() - margin
        for toast in reversed(self._toasts):
            toast.adjustSize()
            y -= toast.height()
            toast.move(QPoint(self.host.width() - toast.width() - margin, y))
            y -= 12

    def host_resized(self) -> None:
        self._relayout()
