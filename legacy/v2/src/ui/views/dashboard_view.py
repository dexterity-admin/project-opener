from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout
from PyQt6.QtCore import Qt
from src.utils.styles import COLOR_DARK_TEXT_MAIN, COLOR_DARK_TEXT_SEC, COLOR_DARK_CARD_BG, COLOR_DARK_ACCENT, COLOR_DARK_BORDER

class DashboardView(QWidget):
    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(30)
        
        # Welcome Header
        title = QLabel("Welcome Back, Engineer")
        title.setStyleSheet(f"font-size: 28pt; font-weight: bold; color: {COLOR_DARK_TEXT_MAIN};")
        layout.addWidget(title)
        
        subtitle = QLabel("Select a project from the sidebar to begin your work.")
        subtitle.setStyleSheet(f"font-size: 14pt; color: {COLOR_DARK_TEXT_SEC};")
        layout.addWidget(subtitle)
        
        # Stats Row
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(20)
        
        # Count Data
        local_count = len(self.config_manager.get_all_projects())
        shared_count = len(self.config_manager.get_shared_projects())
        
        stats_layout.addWidget(self._create_stat_card("My Projects", str(local_count), "🔒 Private"))
        stats_layout.addWidget(self._create_stat_card("Peer Shared", str(shared_count), "🌏 Explore"))
        stats_layout.addStretch()
        
        layout.addLayout(stats_layout)
        layout.addStretch()

    def _create_stat_card(self, title, value, footer):
        card = QFrame()
        card.setFixedSize(200, 120)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_DARK_CARD_BG};
                border-radius: 12px;
                border: 1px solid {COLOR_DARK_BORDER};
            }}
        """)
        
        clayout = QVBoxLayout(card)
        
        lbl_val = QLabel(value)
        lbl_val.setStyleSheet(f"font-size: 32pt; font-weight: bold; color: {COLOR_DARK_ACCENT}; border: none;")
        clayout.addWidget(lbl_val)
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"font-size: 11pt; color: {COLOR_DARK_TEXT_MAIN}; border: none;")
        clayout.addWidget(lbl_title)
        
        lbl_foot = QLabel(footer)
        lbl_foot.setStyleSheet(f"font-size: 9pt; color: {COLOR_DARK_TEXT_SEC}; border: none;")
        clayout.addWidget(lbl_foot)
        
        return card
