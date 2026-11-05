"""The pill and its panel: a separate focus-less QQuickWindow.  Owner: builder 3 (DESKTOP).

Window: ``Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint | WindowDoesNotAcceptFocus``,
then natively ``WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW`` (never in Alt+Tab, never takes focus).
The capture engine excludes this process's windows, so the pill is never in its own captures.
Position: one per monitor layout (``layout_key``), snapped to the nearest edge; default
bottom-right above the notification area.  QML: ``qml/desktop/Pill.qml`` (+ ``PillPanel.qml``),
context properties ``app`` (the facade) and ``pill`` (this controller).
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal, Slot


def layout_key(monitors: list[dict[str, Any]]) -> str:
    """A stable key for the current monitor arrangement: sorted "device@x,y,w,h" joined by "|"."""
    parts = sorted(f"{m.get('device', '')}@{','.join(str(v) for v in m.get('rect', []))}" for m in monitors)
    return "|".join(parts)


def snap_to_edge(x: int, y: int, w: int, h: int, work: tuple[int, int, int, int]) -> tuple[str, int]:
    """(edge, offset along it) for a pill dropped at (x, y) inside work area ``work`` (l, t, r, b)."""
    raise NotImplementedError("snap_to_edge")


def set_no_activate(hwnd: int) -> None:
    """Add WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW to ``hwnd`` (SetWindowLongPtrW, GWL_EXSTYLE)."""
    raise NotImplementedError("set_no_activate")


class PillController(QObject):
    geometryChanged = Signal()

    def __init__(self, facade: Any, engine: Any):
        super().__init__(facade)
        self.facade = facade
        self.engine = engine
        self.window = None          # QQuickWindow from Pill.qml

    def create(self) -> None:
        raise NotImplementedError("PillController.create")

    @Slot()
    def show(self) -> None:
        raise NotImplementedError("PillController.show")

    @Slot()
    def hide(self) -> None:
        raise NotImplementedError("PillController.hide")

    @Slot(int, int)
    def dropped(self, x: int, y: int) -> None:
        """The user dragged the pill and let go: snap, save per layout."""
        raise NotImplementedError("PillController.dropped")
