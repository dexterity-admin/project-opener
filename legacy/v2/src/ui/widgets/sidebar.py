from PyQt6.QtWidgets import QFrame, QVBoxLayout, QPushButton, QLabel, QSpacerItem, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal
from src.utils.styles import get_sidebar_qss, COLOR_DARK_TEXT_MAIN

class Sidebar(QFrame):
    page_changed = pyqtSignal(int)  # Signal to change main view page
    show_about_requested = pyqtSignal()


    def __init__(self):
        super().__init__()
        self.setFixedWidth(250)
        self.setStyleSheet(get_sidebar_qss())
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 20)
        layout.setSpacing(5)

        # Title
        title = QLabel("PROJECT OPENER")
        title.setStyleSheet(f"color: {COLOR_DARK_TEXT_MAIN}; font-weight: bold; font-size: 14pt; padding-left: 20px; margin-bottom: 20px;")
        layout.addWidget(title)

        # Navigation Buttons
        self.btn_dashboard = self._create_btn("📊 Dashboard", 0)
        self.btn_my_projects = self._create_btn("📂 My Projects", 1)
        self.btn_network = self._create_btn("🌏 Explore Shared", 2)
        self.btn_activities = self._create_btn("🚀 Activities", 3)
        self.btn_settings = self._create_btn("🛠️ Personalize", 4)
        
        layout.addWidget(self.btn_dashboard)
        layout.addWidget(self.btn_my_projects)
        layout.addWidget(self.btn_network)
        layout.addWidget(self.btn_activities)
        
        layout.addStretch()
        
        self.btn_about = QPushButton("ℹ️ About")
        self.btn_about.clicked.connect(self.show_about_requested.emit)
        layout.addWidget(self.btn_about)
        
        layout.addWidget(self.btn_settings)

    def _create_btn(self, text, index):
        btn = QPushButton(text)
        btn.clicked.connect(lambda: self.page_changed.emit(index))
        return btn
