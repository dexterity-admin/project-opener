from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QTextEdit, QPushButton, QHBoxLayout, QMessageBox
from PyQt6.QtCore import Qt
from src.utils.styles import COLOR_DARK_BG, COLOR_DARK_TEXT_MAIN, COLOR_DARK_BORDER, COLOR_DARK_ACCENT, COLOR_DARK_TEXT_SEC

class ProjectEditorDialog(QDialog):
    def __init__(self, parent=None, project_data=None):
        super().__init__(parent)
        self.setWindowTitle("Project Details")
        self.setMinimumSize(400, 350)
        self.setStyleSheet(f"background-color: {COLOR_DARK_BG}; color: {COLOR_DARK_TEXT_MAIN};")
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Name
        layout.addWidget(QLabel("Project Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Turbine Refit 2025")
        self.name_edit.setStyleSheet(self._input_style())
        layout.addWidget(self.name_edit)
        
        # Description
        layout.addWidget(QLabel("Description / Role:"))
        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText("Describe what this project is for...")
        self.desc_edit.setStyleSheet(self._input_style())
        self.desc_edit.setMaximumHeight(100)
        layout.addWidget(self.desc_edit)
        
        # Icon / Color (Simplified)
        layout.addWidget(QLabel("Icon Placeholder (e.g. 🏗️, 🔧, ⚡):"))
        self.icon_edit = QLineEdit()
        self.icon_edit.setText("📁")
        self.icon_edit.setStyleSheet(self._input_style())
        layout.addWidget(self.icon_edit)
        
        layout.addStretch()
        
        # Buttons
        actions = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_save = QPushButton("Save Project")
        
        btn_cancel.clicked.connect(self.reject)
        btn_save.clicked.connect(self.validate_and_accept)
        
        style_base = "padding: 10px 20px; border-radius: 6px; font-weight: bold; cursor: pointer;"
        btn_cancel.setStyleSheet(f"background-color: transparent; color: {COLOR_DARK_TEXT_SEC}; {style_base}")
        btn_save.setStyleSheet(f"background-color: {COLOR_DARK_ACCENT}; color: #1e1e2e; {style_base}")
        
        actions.addStretch()
        actions.addWidget(btn_cancel)
        actions.addWidget(btn_save)
        layout.addLayout(actions)
        
        if project_data:
            self.name_edit.setText(project_data.get("name", ""))
            self.desc_edit.setPlainText(project_data.get("description", ""))
            self.icon_edit.setText(project_data.get("icon", "📁"))

    def _input_style(self):
        return f"""
            background-color: #1e1e2e;
            border: 1px solid {COLOR_DARK_BORDER};
            padding: 10px;
            border-radius: 6px;
            color: {COLOR_DARK_TEXT_MAIN};
            font-size: 11pt;
        """

    def validate_and_accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Missing Info", "Project name is required.")
            return
        self.accept()
        
    def get_data(self):
        return {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.toPlainText().strip(),
            "icon": self.icon_edit.text().strip(),
            "activities": []
        }
