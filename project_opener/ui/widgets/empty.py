"""Empty state: keeps the frame, names the next step in one sentence, offers one action."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from project_opener.ui import icons, theme
from project_opener.ui.widgets.common import Button, label

TEXT_WIDTH = 420


class EmptyState(QWidget):
    """Spans the block it stands in (never a narrow island in a flow); the text is
    a fixed 420 px measure so its wrapped height is known before the first paint."""

    def __init__(self, icon_name: str, title: str, text: str = "", action: str = "", on_action=None, parent=None,
                 action_icon: str = "fa5s.plus"):
        super().__init__(parent)
        t = theme.current()
        self.setObjectName("transparent_row")
        self.setStyleSheet("#transparent_row { background: transparent; }")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 36, 24, 36)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, 20, t.text_muted))
        ic.setFixedSize(20, 20)
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignHCenter)
        tl = label(title, "h3")
        tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(tl, 0, Qt.AlignmentFlag.AlignHCenter)
        if text:
            bl = label(text, "muted", wrap=True)
            bl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bl.setFixedWidth(TEXT_WIDTH)
            bl.setFixedHeight(bl.heightForWidth(TEXT_WIDTH))   # box layouts size a wrapped label by one line otherwise
            lay.addWidget(bl, 0, Qt.AlignmentFlag.AlignHCenter)
        if action:
            self.button = Button(action, action_icon)
            if on_action:
                self.button.clicked.connect(on_action)
            lay.addSpacing(8)
            lay.addWidget(self.button, 0, Qt.AlignmentFlag.AlignHCenter)
