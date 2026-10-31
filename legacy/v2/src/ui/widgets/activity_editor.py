from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout, QListWidget, QMessageBox, QFileDialog
from PyQt6.QtCore import Qt, QUrl
from src.utils.styles import COLOR_DARK_BG, COLOR_DARK_TEXT_MAIN, COLOR_DARK_BORDER, COLOR_DARK_ACCENT, COLOR_DARK_TEXT_SEC

class ActivityEditorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Activity")
        self.setMinimumSize(500, 450)
        self.setStyleSheet(f"background-color: {COLOR_DARK_BG}; color: {COLOR_DARK_TEXT_MAIN};")
        self.setAcceptDrops(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Name Input
        layout.addWidget(QLabel("Activity Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Schematic Design")
        self.name_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: #1e1e2e;
                border: 1px solid {COLOR_DARK_BORDER};
                padding: 10px;
                border-radius: 6px;
                color: {COLOR_DARK_TEXT_MAIN};
                font-size: 11pt;
            }}
            QLineEdit:focus {{ border-color: {COLOR_DARK_ACCENT}; }}
        """)
        layout.addWidget(self.name_edit)
        
        # Resources List
        layout.addWidget(QLabel("Resource Paths:"))
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: #1e1e2e;
                border: 1px solid {COLOR_DARK_BORDER};
                border-radius: 6px;
                padding: 5px;
            }}
        """)
        self.list_widget.setToolTip("Drag & drop files or folders here")
        layout.addWidget(self.list_widget)
        
        # Browse Buttons
        browse_layout = QHBoxLayout()
        self.btn_file = QPushButton("📁 Add File")
        self.btn_dir = QPushButton("📂 Add Folder")
        self.btn_link = QPushButton("🔗 Add Link")
        
        for btn in [self.btn_file, self.btn_dir, self.btn_link]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #313244;
                    color: {COLOR_DARK_TEXT_MAIN};
                    padding: 8px;
                    border-radius: 5px;
                    border: 1px solid {COLOR_DARK_BORDER};
                }}
                QPushButton:hover {{ background-color: #45475a; }}
            """)
        
        self.btn_file.clicked.connect(self.browse_file)
        self.btn_dir.clicked.connect(self.browse_dir)
        self.btn_link.clicked.connect(self.add_link)
        browse_layout.addWidget(self.btn_file)
        browse_layout.addWidget(self.btn_dir)
        browse_layout.addWidget(self.btn_link)
        layout.addLayout(browse_layout)
        
        self.info_lbl = QLabel("💡 Tip: You can also drag & drop files directly into this window.")
        self.info_lbl.setStyleSheet(f"color: {COLOR_DARK_TEXT_SEC}; font-size: 9pt; font-style: italic;")
        layout.addWidget(self.info_lbl)
        
        layout.addStretch()
        
        # Action Buttons
        actions_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_create = QPushButton("Create Activity")
        
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_create.clicked.connect(self.validate_and_accept)
        
        style_base = "padding: 10px 20px; border-radius: 6px; font-weight: bold;"
        self.btn_cancel.setStyleSheet(f"background-color: transparent; color: {COLOR_DARK_TEXT_SEC}; {style_base}")
        self.btn_create.setStyleSheet(f"background-color: {COLOR_DARK_ACCENT}; color: #1e1e2e; {style_base}")
        
        actions_layout.addStretch()
        actions_layout.addWidget(self.btn_cancel)
        actions_layout.addWidget(self.btn_create)
        layout.addLayout(actions_layout)

    def browse_file(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, 
            "Select Files", 
            "", 
            "All Files (*);;Executables (*.exe);;PDFs (*.pdf);;Images (*.png *.jpg)"
        )
        if files:
            for f in files:
                self.list_widget.addItem(f)

    def browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Folder")
        if d:
            self.list_widget.addItem(d)

    def add_link(self):
        from PyQt6.QtWidgets import QInputDialog
        url, ok = QInputDialog.getText(self, "Add Link", "Enter Website URL:")
        if ok and url:
            # Ensure protocol
            if "." in url and not url.startswith(("http://", "https://")):
                url = "https://" + url
            self.list_widget.addItem(url)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self.list_widget.addItem(path)
        event.acceptProposedAction()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            for item in self.list_widget.selectedItems():
                self.list_widget.takeItem(self.list_widget.row(item))
        else:
            super().keyPressEvent(event)

    def validate_and_accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Missing Info", "Please enter an activity name.")
            return
        self.accept()
    
    def get_data(self):
        items = []
        for i in range(self.list_widget.count()):
            path = self.list_widget.item(i).text()
            # Simple heuristic for type
            itype = "folder" if os.path.isdir(path) else "file"
            items.append({"type": itype, "path": path})
            
        return {
            "name": self.name_edit.text().strip(),
            "items": items
        }
import os
