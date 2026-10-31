from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QHBoxLayout, QLineEdit, QFrame, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from src.ui.widgets.flow_layout import FlowLayout
from src.ui.widgets.project_card import ProjectCard
from src.utils.styles import COLOR_DARK_TEXT_MAIN, COLOR_DARK_BORDER

class ProjectsView(QWidget):
    project_selected = pyqtSignal(str)

    def __init__(self, config_manager, mode="local"):
        super().__init__()
        self.config_manager = config_manager
        self.mode = mode # 'local' or 'network'
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Header (Title + Search)
        header_layout = QHBoxLayout()
        title_text = "My Projects" if mode == "local" else "Explore Shared"
        title = QLabel(title_text)
        title.setStyleSheet(f"font-size: 20pt; font-weight: bold; color: {COLOR_DARK_TEXT_MAIN};")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search projects...")
        self.search_bar.setFixedWidth(250)
        self.search_bar.setStyleSheet(f"""
            QLineEdit {{
                background-color: #313244;
                border: 1px solid {COLOR_DARK_BORDER};
                border-radius: 8px;
                padding: 8px 12px;
                color: {COLOR_DARK_TEXT_MAIN};
            }}
            QLineEdit:focus {{
                border: 1px solid #cba6f7;
            }}
        """)
        self.search_bar.textChanged.connect(self.refresh_grid)
        header_layout.addWidget(self.search_bar)
        
        # Add Project Button (Only for Local)
        if mode == "local":
            header_layout.addSpacing(10)
            self.btn_add = QPushButton("+ New Project")
            self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_add.setStyleSheet("""
                QPushButton {
                    background-color: #cba6f7;
                    color: #1e1e2e;
                    border-radius: 8px;
                    padding: 8px 15px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #d8b4fe; }
            """)
            self.btn_add.clicked.connect(self.add_project)
            header_layout.addWidget(self.btn_add)
            
        layout.addLayout(header_layout)
        
        # Divider
        # line = QFrame()
        # line.setFrameShape(QFrame.Shape.HLine)
        # line.setStyleSheet(f"color: {COLOR_DARK_BORDER};")
        # layout.addWidget(line)
        
        layout.addSpacing(20)
        
        # Scroll Area for Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;") # Let grid custom bg show if needed
        
        self.grid_container = QWidget()
        self.grid_layout = FlowLayout(self.grid_container, margin=0, hSpacing=20, vSpacing=20)
        
        scroll.setWidget(self.grid_container)
        layout.addWidget(scroll)
        
        self.refresh_grid()

    def refresh_grid(self):
        # Clear existing items
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget: 
                widget.deleteLater()
                
        # Get Projects
        if self.mode == "local":
            projects = self.config_manager.get_all_projects()
        else:
            projects = self.config_manager.get_shared_projects()

        search_term = self.search_bar.text().lower()
        
        for proj in projects:
            # Filter by search
            if search_term and search_term not in proj["name"].lower(): continue
            
            card = ProjectCard(proj["name"], proj["data"], is_locked=proj["locked"])
            
            # If shared, add clone option
            if self.mode == "shared" or proj["source"] == "shared":
                card.set_sharing_mode(proj["author"])
                card.clone_requested.connect(lambda p=proj: self.clone_project(p))

            card.clicked.connect(self.project_selected.emit) 
            self.grid_layout.addWidget(card)

    def clone_project(self, project):
        new_name = self.config_manager.clone_project(project)
        QMessageBox.information(self, "Project Cloned", f"Project '{project['name']}' has been copied to your projects as '{new_name}'.")

    def add_project(self):
        from PyQt6.QtWidgets import QDialog
        from src.ui.widgets.project_editor import ProjectEditorDialog
        
        dialog = ProjectEditorDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            name = data["name"]
            
            # Save to config
            if "projects" not in self.config_manager.local_projects:
                self.config_manager.local_projects["projects"] = {}
                
            self.config_manager.local_projects["projects"][name] = data
            self.config_manager.save_local_projects()
            self.refresh_grid()
