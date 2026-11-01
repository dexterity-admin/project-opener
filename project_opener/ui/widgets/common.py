"""Small reusable widgets: buttons, chips, switches, avatars, labels, pills."""
from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
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


def _mix(a: str, b: str, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    return QColor(
        int(ca.red() + (cb.red() - ca.red()) * t),
        int(ca.green() + (cb.green() - ca.green()) * t),
        int(ca.blue() + (cb.blue() - ca.blue()) * t),
    )


def _ink_on(bg: str, hue: str, dark: bool) -> str:
    """Ink of ``hue`` on the pale tint ``bg``: darkened (light) or lightened (dark),
    then mixed towards the text colour until it reads at 4.5:1."""
    t = theme.current()
    ink = _mix(hue, "#0F1211" if not dark else "#FFFFFF", 0.45).name()
    step = 0.0
    while theme.contrast(ink, bg) < 4.5 and step < 1.0:
        step += 0.1
        ink = _mix(ink, t.text, step).name()
    return ink


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
            self.setIconSize(QSize(16, 16))


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
        self.setCursor(Qt.CursorShape.PointingHandCursor if checkable else Qt.CursorShape.ArrowCursor)


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


class SegmentLabel(QLabel):
    """One line of " · "-joined facts that drops whole segments from the right when the width
    is short, so it never says half a word ("2 launch s…just now")."""

    SEP = " · "

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: list[str] = []
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def set_segments(self, segments: list[str], drop_order: list[int] | None = None) -> None:
        """``drop_order`` lists the indices to remove first when the line is too long; indices not
        listed are kept as long as anything else can go (the health fact, for example)."""
        self._segments = [s for s in segments if s]
        kept = [i for i, s in enumerate(segments) if s]
        remap = {old: new for new, old in enumerate(kept)}
        self._drop = [remap[i] for i in (drop_order or []) if i in remap]
        self.setToolTip(self.SEP.join(self._segments))
        self._fit()

    def segments(self) -> list[str]:
        return list(self._segments)

    def fitted_text(self, width: int) -> str:
        fm = QFontMetrics(self.font())
        parts: list[str | None] = list(self._segments)
        order = list(getattr(self, "_drop", [])) + [i for i in range(len(parts) - 1, -1, -1) if i not in getattr(self, "_drop", [])]

        def text() -> str:
            return self.SEP.join(p for p in parts if p is not None)
        for i in order:
            if fm.horizontalAdvance(text()) <= width or sum(p is not None for p in parts) <= 1:
                break
            parts[i] = None
        return text()

    def _fit(self) -> None:
        self.setText(self.fitted_text(max(40, self.width() - 2)))

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._fit()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(120, QFontMetrics(self.font()).height() + 2)


def label(text: str, kind: str = "", wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if kind:
        lbl.setObjectName(kind)
    lbl.setWordWrap(wrap)
    return lbl


def kpi_value_label(text: str) -> QLabel:
    """A KPI value: 18 pt regular, tabular figures (objectName "kpi")."""
    lbl = QLabel(text)
    lbl.setObjectName("kpi")
    lbl.setFont(theme.ui_font(18, 400, tabular=True))
    return lbl


def hline() -> QFrame:
    f = QFrame()
    f.setObjectName("hline")
    f.setFrameShape(QFrame.Shape.HLine)
    return f


# ------------------------------------------------------------------- switch
class ToggleSwitch(QAbstractButton):
    """Animated toggle, 40 x 22: ink track when on (near-black on light, white on dark),
    strong-border track when off.  Colour stays on data; a switch is chrome (DESIGN.md)."""

    W, H = 40, 22

    def __init__(self, parent=None, checked: bool = False):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)
        self.setFixedSize(self.W, self.H)

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
        return QSize(self.W, self.H)

    def paintEvent(self, e) -> None:  # noqa: N802
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        track = _mix(t.border_strong, t.text, self._pos)
        if self.isDown():
            track = _mix(track.name(), t.text_muted, 0.2)
        if not self.isEnabled():
            track.setAlpha(110)
        p.setPen(Qt.PenStyle.NoPen)
        if self.hasFocus():
            p.setPen(QPen(QColor(t.accent), 2))
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), self.H / 2 - 1, self.H / 2 - 1)
            p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, self.H / 2, self.H / 2)
        knob_d = self.H - 6
        knob_x = 3 + self._pos * (self.width() - knob_d - 6)
        knob = _mix(t.surface, t.bg if not t.dark else t.bg, self._pos)
        if not self.isEnabled():
            knob.setAlpha(200)
        p.setBrush(knob)
        p.drawEllipse(QRectF(knob_x, 3, knob_d, knob_d))
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
    """A person: pale disc of their own hue with initials in the same hue, darkened.

    Identity, not data: six hues 60 degrees apart, chosen by a stable hash of the name.
    """

    HUES = [QColor.fromHsl(h, 150, 95).name() for h in range(0, 360, 60)]

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
        key = (name or "?").strip().lower()
        h = 0
        for ch in key:
            h = (h * 31 + ord(ch)) & 0xFFFFFFFF
        return Avatar.HUES[h % len(Avatar.HUES)]

    def paintEvent(self, e) -> None:  # noqa: N802
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hue = self._color or self.color_for(self._name)
        disc = theme.tint(hue, 0.18, t.dark)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(disc))
        p.drawEllipse(0, 0, self._size, self._size)
        parts = [x for x in self._name.replace(".", " ").replace("_", " ").split() if x]
        initials = "".join(x[0] for x in parts[:2]).upper() or "?"
        p.setFont(theme.ui_font(max(9, int(self._size * 0.34)), 600))
        p.setPen(QColor(_ink_on(disc, hue, t.dark)))
        p.drawText(QRect(0, 0, self._size, self._size), Qt.AlignmentFlag.AlignCenter, initials)
        if self._online is not None:
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
    """Status pill: pale tint with dark ink of the same hue, 20-22 px tall.

    ``level`` (ok | warn | bad | info | neutral) uses the theme's pill tokens; a
    hex ``color`` is rendered as a pale tint of that colour with readable ink.
    """

    def __init__(self, text: str, color: str | None = None, level: str = "", parent=None):
        super().__init__(text, parent)
        self._level = level
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(theme.ui_font(9, 500))
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.set_color(color)

    def set_level(self, level: str) -> None:
        self._level = level
        self.set_color(None)

    def set_color(self, color: str | None) -> None:
        t = theme.current()
        if color and QColor(color).isValid() and not self._level:
            bg = theme.tint(color, 0.14, t.dark)
            ink = _ink_on(bg, color, t.dark)
        else:
            bg, ink = theme.pill_colors(t, self._level or "neutral")
        self.setStyleSheet(f"QLabel {{ background-color: {bg}; color: {ink}; border-radius: 11px; padding: 0 9px; }}")


# ------------------------------------------------------------ icon circle
class IconCircle(QWidget):
    """An icon drawn in ``color``.  Plain by default; ``container=True`` adds a pale
    tinted rounded square (used once, on the Project detail header)."""

    def __init__(self, icon_name: str, color: str, size: int = 40, parent=None, container: bool = False):
        super().__init__(parent)
        self._icon = icon_name
        self._color = color
        self._size = size
        self._container = container
        self.setFixedSize(size, size)

    def set(self, icon_name: str | None = None, color: str | None = None) -> None:
        if icon_name:
            self._icon = icon_name
        if color:
            self._color = color
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._container:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.tint(self._color, 0.14, t.dark)))
            p.drawRoundedRect(QRectF(0, 0, self._size, self._size), self._size * 0.3, self._size * 0.3)
            px = int(self._size * 0.5)
        else:
            px = int(self._size * 0.8)
        pm = icons.pixmap(self._icon, px, self._color)
        w = pm.width() / pm.devicePixelRatio()
        off = (self._size - w) / 2
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
        pen = QPen(QColor(t.accent), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        r = QRectF(2, 2, self._size - 4, self._size - 4)
        p.drawArc(r, -self._angle * 16, 270 * 16)
        p.end()
