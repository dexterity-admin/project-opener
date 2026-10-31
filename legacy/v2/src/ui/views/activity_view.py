from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QFrame, QScrollArea, QGridLayout
from PyQt6.QtCore import Qt, pyqtSignal
from src.utils.styles import COLOR_DARK_TEXT_MAIN, COLOR_DARK_TEXT_SEC, COLOR_DARK_ACCENT, COLOR_DARK_CARD_BG, COLOR_DARK_BORDER
from src.core.path_resolver import PathResolver

class ActivityView(QWidget):
    back_requested = pyqtSignal()
    
    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.resolver = PathResolver(config_manager)
        self.current_project = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Header
        header_layout = QHBoxLayout()
        
        self.btn_back = QPushButton("← Back")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.setStyleSheet(f"""
            QPushButton {{ color: {COLOR_DARK_TEXT_SEC}; font-size: 11pt; border: none; background: transparent; }}
            QPushButton:hover {{ color: {COLOR_DARK_ACCENT}; }}
        """)
        self.btn_back.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self.btn_back)
        
        header_layout.addStretch()
        
        self.btn_add = QPushButton("+ New Activity")
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setStyleSheet(f"background-color: {COLOR_DARK_ACCENT}; color: #1e1e2e; font-weight: bold; border-radius: 6px; padding: 6px 12px;")
        self.btn_add.clicked.connect(self.add_activity)
        header_layout.addWidget(self.btn_add)
        
        layout.addLayout(header_layout)
        
        self.title_label = QLabel("Project Title")
        self.title_label.setStyleSheet(f"font-size: 22pt; font-weight: bold; color: {COLOR_DARK_TEXT_MAIN}; margin-top: 10px; margin-bottom: 20px;")
        layout.addWidget(self.title_label)

        # Scroll Area for Activities
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        self.activities_container = QWidget()
        self.activities_layout = QGridLayout(self.activities_container)
        self.activities_layout.setSpacing(20)
        
        scroll.setWidget(self.activities_container)
        layout.addWidget(scroll)

    def load_project(self, project_name):
        self.current_project = project_name
        self.title_label.setText(project_name)
        
        # 1. Try Local
        local_projs = self.config_manager.get_all_projects()
        proj = next((p for p in local_projs if p["name"] == project_name), None)
        
        if not proj:
            # 2. Try Shared
            shared_projs = self.config_manager.get_shared_projects()
            proj = next((p for p in shared_projs if p["name"] == project_name), None)

        if not proj:
            self.title_label.setText(f"Error: {project_name} not found")
            return

        proj_data = proj["data"]
        is_shared = proj["source"] == "shared"
        
        # Toggle UI for Review Mode
        self.btn_add.setVisible(not is_shared)
        if is_shared:
            self.title_label.setText(f"{project_name} (Review Mode - by {proj['author']})")

        # Clear existing
        while self.activities_layout.count():
            item = self.activities_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        # Populate Activities
        activities = proj_data.get("activities", [])
        
        row, col = 0, 0
        for activity in activities:
            card = self._create_activity_card(activity)
            self.activities_layout.addWidget(card, row, col)
            col += 1
            if col > 1: # 2 Columns
                col = 0
                row += 1
                
        # Fill rest of grid to top-left alignment
        self.activities_layout.setRowStretch(row + 1, 1)

    def _create_activity_card(self, activity):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_DARK_CARD_BG};
                border-radius: 10px;
                border: 1px solid {COLOR_DARK_BORDER};
            }}
            QFrame:hover {{
                border-color: {COLOR_DARK_ACCENT};
            }}
        """)
        card.setMinimumHeight(150)
        
        layout = QVBoxLayout(card)
        
        # Title
        title = QLabel(activity.get("name", "Unnamed Activity"))
        title.setStyleSheet(f"font-size: 14pt; font-weight: bold; color: {COLOR_DARK_TEXT_MAIN}; border: none;")
        layout.addWidget(title)
        
        # List of resources (preview)
        items = activity.get("items", [])
        desc = QLabel(f"{len(items)} Resources Linked")
        desc.setStyleSheet(f"color: {COLOR_DARK_TEXT_SEC}; border: none;")
        layout.addWidget(desc)
        
        layout.addStretch()
        
        # Launch Button
        btn_launch = QPushButton("🚀 LAUNCH ACTIVITY")
        btn_launch.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_launch.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_DARK_ACCENT};
                color: #1e1e2e;
                font-weight: bold;
                border-radius: 6px;
                padding: 10px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: #d8b4fe;
            }}
        """)
        btn_launch.clicked.connect(lambda: self.launch_activity(activity))
        layout.addWidget(btn_launch)
        
        return card

    def launch_activity(self, activity):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        import os
        
        items = activity.get("items", [])
        if not items:
            QMessageBox.information(self, "No Resources", "This activity has no linked resources.")
            return
            
        for item in items:
            path = item.get("path")
            if not path: continue
            
            # Resolve path variables
            resolved_path = self.resolver.resolve(path)
            
            # 1. Check if it's a URL
            if resolved_path.startswith(("http://", "https://")):
                QDesktopServices.openUrl(QUrl(resolved_path))
                continue

            # 2. Check if it's a local file/folder
            if os.path.exists(resolved_path):
                # Special handling for .exe
                if resolved_path.lower().endswith(".exe"):
                    import subprocess
                    try:
                        # Launch .exe as a detached process
                        subprocess.Popen(resolved_path)
                    except Exception as e:
                        print(f"Failed to launch EXE: {e}")
                else:
                    url = QUrl.fromLocalFile(os.path.abspath(resolved_path))
                    QDesktopServices.openUrl(url)
            else:
                # Last ditch: try as URL if it looks like one but missing protocol
                if "." in resolved_path and "/" not in resolved_path:
                    QDesktopServices.openUrl(QUrl("https://" + resolved_path))
                else:
                    print(f"File not found or invalid URL: {resolved_path}")


    def add_activity(self):
        from PyQt6.QtWidgets import QDialog
        from src.ui.widgets.activity_editor import ActivityEditorDialog
        
        dialog = ActivityEditorDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if not data["name"]: return
            
            # Find and update project data
            if self.current_project:
                projects_map = self.config_manager.local_projects.get("projects", {})
                if self.current_project in projects_map:
                    proj = projects_map[self.current_project]
                    if "activities" not in proj: proj["activities"] = []
                    proj["activities"].append(data)
                    self.config_manager.save_local_projects()
                    self.load_project(self.current_project) # Refresh
                else:
                    print("Cannot edit network project")
