from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QColor
try:
    import qtawesome as qta
except ImportError:
    qta = None
from src.utils.styles import COLOR_DARK_CARD_BG, COLOR_DARK_TEXT_MAIN, COLOR_DARK_TEXT_SEC, COLOR_DARK_ACCENT, CARD_WIDTH_MIN, CARD_HEIGHT

class ProjectCard(QFrame):
    clicked = pyqtSignal(str) # Emits project name
    edit_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    clone_requested = pyqtSignal()

    def __init__(self, name, data, is_locked=False):
        super().__init__()
        self.name = name
        self.data = data
        self.is_locked = is_locked
        
        self.setFixedSize(CARD_WIDTH_MIN, CARD_HEIGHT)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_DARK_CARD_BG};
                border-radius: 12px;
                border: 1px solid #3b3e54;
            }}
            QFrame:hover {{
                border: 1px solid {COLOR_DARK_ACCENT};
                background-color: #383a50;
            }}
        """)
        
        # Shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Top Row: Icon + Name
        top_layout = QHBoxLayout()
        name_label = QLabel(name)
        name_label.setStyleSheet(f"font-weight: bold; font-size: 13pt; color: {COLOR_DARK_TEXT_MAIN}; border: none; background: transparent;")
        name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        name_label.setWordWrap(True) # Handle long names
        
        top_layout.addWidget(name_label)
        
        if is_locked and qta:
            lock_label = QLabel()
            lock_label.setPixmap(qta.icon('fa5s.lock', color="#e78284").pixmap(16, 16))
            lock_label.setStyleSheet("border: none; background: transparent;")
            lock_label.setToolTip("Company Project (Read-Only)")
            top_layout.addWidget(lock_label)
            
        layout.addLayout(top_layout)
        
        # Activity Count / Desc
        act_count = len(data.get("activities", []))
        sub_label = QLabel(f"{act_count} Activities")
        sub_label.setStyleSheet(f"color: {COLOR_DARK_TEXT_SEC}; font-size: 10pt; border: none; background: transparent;")
        layout.addWidget(sub_label)
        
        layout.addStretch()
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_open = QPushButton("Open")
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_DARK_ACCENT};
                color: #1e1e2e;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: #d8b4fe;
            }}
        """)
        self.btn_open.clicked.connect(lambda: self.clicked.emit(self.name))
        btn_layout.addWidget(self.btn_open)
        
        btn_layout.addStretch()
        
        # Edit/Delete (Only if not locked)
        if not is_locked:
            self.btn_edit = self._create_icon_btn('fa5s.pen', "Edit")
            self.btn_edit.clicked.connect(lambda: self.edit_requested.emit(self.name))
            btn_layout.addWidget(self.btn_edit)
            
            self.btn_del = self._create_icon_btn('fa5s.trash', "Delete")
            self.btn_del.clicked.connect(lambda: self.delete_requested.emit(self.name))
            btn_layout.addWidget(self.btn_del)
            
        layout.addLayout(btn_layout)

    def set_sharing_mode(self, author):
        """Transform card for Explore Shared view."""
        # 1. Add Author label
        author_lbl = QLabel(f"by {author}")
        author_lbl.setStyleSheet(f"color: {COLOR_DARK_TEXT_SEC}; font-size: 9pt; font-style: italic; border: none; background: transparent;")
        self.layout().insertWidget(2, author_lbl)
        
        # 2. Add Clone Button
        self.btn_clone = QPushButton("Clone to My Projects")
        self.btn_clone.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clone.setStyleSheet(f"""
            QPushButton {{
                background-color: #313244;
                color: {COLOR_DARK_TEXT_MAIN};
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
                border: 1px solid #45475a;
            }}
            QPushButton:hover {{
                background-color: #cba6f7;
                color: #1e1e2e;
            }}
        """)
        self.btn_clone.clicked.connect(self.clone_requested.emit)
        
        # Replace 'Open' or add next to it? Let's add it.
        self.layout().addWidget(self.btn_clone)
        self.btn_open.setText("Review")

    def _create_icon_btn(self, icon_name, tooltip):
        btn = QPushButton()
        if qta:
            btn.setIcon(qta.icon(icon_name, color=COLOR_DARK_TEXT_SEC))
        else:
            btn.setText("?" if "pen" in icon_name else "X")
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 10);
                border-radius: 4px;
            }
        """)
        return btn
