"""Empty state: keeps the frame, names the next step in one sentence."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from project_opener.ui import icons, theme
from project_opener.ui.widgets.common import Button, label


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, text: str = "", action: str = "", on_action=None, parent=None):
        super().__init__(parent)
        t = theme.current()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 40, 24, 40)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, 20, t.text_muted))
        ic.setFixedSize(20, 20)
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignHCenter)
        tl = label(title, "h3")
        tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(tl)
        if text:
            bl = label(text, "muted", wrap=True)
            bl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bl.setMaximumWidth(420)
            lay.addWidget(bl, 0, Qt.AlignmentFlag.AlignHCenter)
        if action:
            b = Button(action, "fa5s.plus")
            if on_action:
                b.clicked.connect(on_action)
            lay.addSpacing(8)
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
