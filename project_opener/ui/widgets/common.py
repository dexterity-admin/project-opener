"""Small reusable widgets: buttons, chips, switches, avatars, labels."""
from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from project_opener.ui import icons, theme


# ------------------------------------------------------------------ buttons
class Button(QPushButton):
    def __init__(self, text: str = "", icon_name: str = "", kind: str = "", parent=None, icon_color: str | None = None):
        super().__init__(text, parent)
        if kind:
            self.setObjectName(kind)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_name:
            t = theme.current()
            color = icon_color or (t.accent_fg if kind == "primary" else t.text_muted)
            self.setIcon(icons.icon(icon_name, color))
            self.setIconSize(QSize(15, 15))


class IconButton(QPushButton):
    def __init__(self, icon_name: str, tooltip: str = "", parent=None, size: int = 16, color: str | None = None,
                 checkable: bool = False):
        super().__init__(parent)
        self.setObjectName("icon")
        self._name = icon_name
        self._color = color
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setCheckable(checkable)
        self.setIconSize(QSize(size, size))
        self.refresh()

    def refresh(self, icon_name: str | None = None, color: str | None = None) -> None:
        if icon_name:
            self._name = icon_name
        if color:
            self._color = color
        self.setIcon(icons.icon(self._name, self._color))


class Chip(QPushButton):
    def __init__(self, text: str, checkable: bool = True, parent=None):
        super().__init__(text, parent)
        self.setObjectName("chip")
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


# ------------------------------------------------------------------- labels
class ElidedLabel(QLabel):
    """Single-line label that elides instead of growing.

    The size hint never depends on the text, otherwise re-eliding on resize
    would change the hint, invalidate the layout, resize the label again and
    thrash for seconds on a busy page.  The text is painted directly.
    """

    def __init__(self, text: str = "", parent=None, mode=Qt.TextElideMode.ElideMiddle):
        super().__init__(parent)
        self._full = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text or ""
        self.setToolTip(self._full if len(self._full) > 40 else "")
        self.update()

    def text(self) -> str:  # noqa: D102
        return self._full

    def fullText(self) -> str:  # noqa: N802
        return self._full

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(120, QFontMetrics(self.font()).height() + 2)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(24, QFontMetrics(self.font()).height() + 2)

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        fm = QFontMetrics(self.font())
        elided = fm.elidedText(self._full, self._mode, max(10, self.width() - 2))
        p.setPen(self.palette().color(self.foregroundRole()))
        p.setFont(self.font())
        p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), elided)
        p.end()


def label(text: str, kind: str = "", wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if kind:
        lbl.setObjectName(kind)
    lbl.setWordWrap(wrap)
    return lbl


def hline() -> QFrame:
    f = QFrame()
    f.setObjectName("hline")
    f.setFrameShape(QFrame.Shape.HLine)
    return f


# ------------------------------------------------------------------- switch
class ToggleSwitch(QAbstractButton):
    """Animated iOS-style toggle."""

    def __init__(self, parent=None, checked: bool = False):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)
        self.setFixedSize(42, 24)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def get_knob(self) -> float:
        return self._pos

    def set_knob(self, v: float) -> None:
        self._pos = v
        self.update()

    knob = Property(float, get_knob, set_knob)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(42, 24)

    def paintEvent(self, e) -> None:  # noqa: N802
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        track_off = QColor(t.border_strong)
        track_on = QColor(t.accent)
        track = QColor(
            int(track_off.red() + (track_on.red() - track_off.red()) * self._pos),
            int(track_off.green() + (track_on.green() - track_off.green()) * self._pos),
            int(track_off.blue() + (track_on.blue() - track_off.blue()) * self._pos),
        )
        if not self.isEnabled():
            track.setAlpha(120)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, 12, 12)
        knob_x = 3 + self._pos * (self.width() - 24)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(knob_x, 3, 18, 18))
        p.end()


class SwitchRow(QWidget):
    toggled = Signal(bool)

    def __init__(self, title: str, subtitle: str = "", checked: bool = False, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 6)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label(title, "h3"))
        if subtitle:
            text.addWidget(label(subtitle, "muted", wrap=True))
        lay.addLayout(text, 1)
        self.switch = ToggleSwitch(checked=checked)
        self.switch.toggled.connect(self.toggled.emit)
        lay.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignVCenter)

    def isChecked(self) -> bool:  # noqa: N802
        return self.switch.isChecked()

    def setChecked(self, v: bool) -> None:  # noqa: N802
        self.switch.setChecked(v)


# ------------------------------------------------------------------- avatar
class Avatar(QWidget):
    def __init__(self, name: str, size: int = 32, color: str | None = None, online: bool | None = None, parent=None):
        super().__init__(parent)
        self._name = name or "?"
        self._size = size
        self._color = color
        self._online = online
        self.setFixedSize(size, size)

    def set_name(self, name: str) -> None:
        self._name = name or "?"
        self.update()

    def set_online(self, online: bool | None) -> None:
        self._online = online
        self.update()

    @staticmethod
    def color_for(name: str) -> str:
        pal = ["#4F7DFF", "#8B5CF6", "#EC4899", "#F97316", "#10B981", "#14B8A6", "#F59E0B", "#6366F1"]
        return pal[sum(ord(c) for c in name) % len(pal)]

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self._color or self.color_for(self._name))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(0, 0, self._size, self._size)
        parts = [x for x in self._name.replace(".", " ").replace("_", " ").split() if x]
        initials = "".join(x[0] for x in parts[:2]).upper() or "?"
        f = QFont(theme.display_font(), max(7, int(self._size * 0.36)))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.readable_on(color.name())))
        p.drawText(QRect(0, 0, self._size, self._size), Qt.AlignmentFlag.AlignCenter, initials)
        if self._online is not None:
            t = theme.current()
            d = max(8, self._size // 4)
            p.setBrush(QColor(t.success if self._online else t.text_faint))
            p.setPen(QPen(QColor(t.surface), 2))
            p.drawEllipse(self._size - d, self._size - d, d, d)
        p.end()


# ---------------------------------------------------------------- color dot
class ColorDot(QWidget):
    def __init__(self, color: str, size: int = 12, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(size, size)

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._color))
        p.drawEllipse(0, 0, self.width(), self.height())
        p.end()


# ---------------------------------------------------------------- badge
class Badge(QLabel):
    def __init__(self, text: str, color: str | None = None, parent=None):
        super().__init__(text, parent)
        self.set_color(color)

    def set_color(self, color: str | None) -> None:
        t = theme.current()
        c = color or t.accent
        self.setStyleSheet(
            f"background-color: {theme.alpha(c, 0.16)}; color: {c}; border-radius: 9px; padding: 2px 8px;"
            f" font-size: {t.font_size - 1}pt; font-weight: 700;")


# ------------------------------------------------------------ icon circle
class IconCircle(QWidget):
    def __init__(self, icon_name: str, color: str, size: int = 40, parent=None):
        super().__init__(parent)
        self._icon = icon_name
        self._color = color
        self._size = size
        self.setFixedSize(size, size)

    def set(self, icon_name: str | None = None, color: str | None = None) -> None:
        if icon_name:
            self._icon = icon_name
        if color:
            self._color = color
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(self._color)
        bg.setAlpha(46)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(0, 0, self._size, self._size), self._size * 0.3, self._size * 0.3)
        pm = icons.pixmap(self._icon, int(self._size * 0.5), self._color)
        off = (self._size - pm.width() / pm.devicePixelRatio()) / 2
        p.drawPixmap(QPoint(int(off), int(off)), pm)
        p.end()


class Spinner(QWidget):
    """Tiny indeterminate spinner for background work."""

    def __init__(self, size: int = 16, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import QTimer
        self._angle = 0
        self._size = size
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(30)

    def start(self) -> None:
        self.show()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(t.accent), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        r = QRectF(2, 2, self._size - 4, self._size - 4)
        p.drawArc(r, -self._angle * 16, 270 * 16)
        p.end()
