"""The window picker: a transparent click-through overlay per monitor.  Owner: builder 3 (DESKTOP).

While active, a timer reads the cursor, takes ``WindowFromPoint`` -> ``GetAncestor(GA_ROOT)``
(skipping our own overlays), asks ``app.capture.identifyForPicker(hwnd)`` and frames
the window green (identifiable) or amber, with the label from ``hoverIdentified``.
Click adds (``app.capture.addWindow``), Esc cancels.  QML: ``qml/desktop/PickerOverlay.qml``.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal


def root_window_at(x: int, y: int, exclude: set[int] | None = None) -> int:
    """Top-level window under the screen point, ignoring ``exclude`` hwnds; 0 when none."""
    raise NotImplementedError("root_window_at")


class WindowPicker(QObject):
    hovered = Signal(int, "QVariantList")      # hwnd, [l, t, r, b] in screen pixels
    finished = Signal(int)                     # hwnd or 0

    def __init__(self, facade: Any, engine: Any):
        super().__init__(facade)
        self.facade = facade
        self.engine = engine

    def start(self) -> None:
        raise NotImplementedError("WindowPicker.start")

    def cancel(self) -> None:
        raise NotImplementedError("WindowPicker.cancel")
