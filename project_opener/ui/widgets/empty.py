"""Empty-state placeholder with icon, text and an optional call to action."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from project_opener.ui import theme
from project_opener.ui.widgets.common import Button, IconCircle, label


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, text: str = "", action: str = "", on_action=None, parent=None):
        super().__init__(parent)
        t = theme.current()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 40, 24, 40)
        lay.setSpacing(10)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(IconCircle(icon_name, t.accent, 72), 0, Qt.AlignmentFlag.AlignHCenter)
        tl = label(title, "h2")
        tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(tl)
        if text:
            bl = label(text, "muted", wrap=True)
            bl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bl.setMaximumWidth(460)
            lay.addWidget(bl, 0, Qt.AlignmentFlag.AlignHCenter)
        if action:
            b = Button(action, "fa5s.plus", "primary")
            if on_action:
                b.clicked.connect(on_action)
            lay.addSpacing(6)
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
