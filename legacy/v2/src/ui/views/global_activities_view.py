from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem
from PyQt6.QtCore import Qt
from src.utils.styles import COLOR_DARK_TEXT_MAIN, COLOR_DARK_TEXT_SEC

class GlobalActivitiesView(QWidget):
    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        
        title = QLabel("All Activities")
        title.setStyleSheet(f"font-size: 20pt; font-weight: bold; color: {COLOR_DARK_TEXT_MAIN};")
        layout.addWidget(title)
        
        subtitle = QLabel("A quick glance at activities across all your projects.")
        subtitle.setStyleSheet(f"color: {COLOR_DARK_TEXT_SEC}; font-size: 11pt;")
        layout.addWidget(subtitle)
        
        layout.addSpacing(20)
        
        self.list = QListWidget()
        self.list.setStyleSheet(f"background: transparent; border: none; color: {COLOR_DARK_TEXT_MAIN}; font-size: 11pt;")
        layout.addWidget(self.list)
        
        self.refresh()
        
    def refresh(self):
        self.list.clear()
        
        # Gather all activities
        projects = self.config_manager.get_all_projects()
        for proj in projects:
            activities = proj["data"].get("activities", [])
            for act in activities:
                item_text = f"{act['name']}  ({proj['name']})"
                item = QListWidgetItem(item_text)
                self.list.addItem(item)
        
        if self.list.count() == 0:
            self.list.addItem("No activities found.")
