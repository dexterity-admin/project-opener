"""Non-blocking toast notifications stacked in the window's bottom-right."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from project_opener.ui import icons, theme

LEVEL_ICONS = {"info": "fa5s.info-circle", "success": "fa5s.check-circle", "warning": "fa5s.exclamation-triangle",
               "error": "fa5s.times-circle"}


class Toast(QFrame):
    closed = Signal(object)
    action_clicked = Signal()

    def __init__(self, title: str, body: str = "", level: str = "info", action: str = "", parent=None, timeout: int = 4500):
        super().__init__(parent)
        t = theme.current()
        color = {"info": t.info, "success": t.success, "warning": t.warning, "error": t.danger}.get(level, t.info)
        self.setObjectName("toast")
        self.setStyleSheet(
            f"QFrame#toast {{ background-color: {t.surface_2}; border: 1px solid {t.border_strong};"
            f" border-left: 3px solid {color}; border-radius: 10px; }}")
        self.setFixedWidth(360)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 10, 10)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(LEVEL_ICONS.get(level, "fa5s.info-circle"), 18, color))
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        tl = QLabel(title)
        tl.setStyleSheet("font-weight: 700;")
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
            btn.setObjectName("ghost")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(self.action_clicked.emit)
            btn.clicked.connect(self.dismiss)
            lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
        close = QPushButton()
        close.setObjectName("icon")
        close.setIcon(icons.icon("fa5s.times", t.text_faint))
        close.setFixedSize(24, 24)
        close.clicked.connect(self.dismiss)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if timeout > 0:
            QTimer.singleShot(timeout, self.dismiss)

    def appear(self) -> None:
        self.show()
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def dismiss(self) -> None:
        if not self.isVisible():
            return
        self._anim.stop()
        self._anim.setStartValue(self._fx.opacity())
        self._anim.setEndValue(0.0)
        try:
            self._anim.finished.disconnect()
        except RuntimeError:
            pass
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
        margin = 18
        y = self.host.height() - margin
        for toast in reversed(self._toasts):
            toast.adjustSize()
            y -= toast.height()
            toast.move(QPoint(self.host.width() - toast.width() - margin, y))
            y -= 10

    def host_resized(self) -> None:
        self._relayout()
