from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt
from src.utils.styles import COLOR_DARK_TEXT_MAIN, COLOR_DARK_BORDER, COLOR_DARK_CARD_BG, COLOR_DARK_ACCENT

class SettingsView(QWidget):
    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        title = QLabel("Personalize Your Folders")
        title.setStyleSheet(f"font-size: 22pt; font-weight: bold; color: {COLOR_DARK_TEXT_MAIN};")
        layout.addWidget(title)
        
        desc = QLabel("Sometimes the company uses different drive letters (like P: or Z:). \nTell us where your project files are stored locally so we can open them for you.")
        desc.setStyleSheet("color: #a6adc8; font-size: 11pt; line-height: 150%;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Company Reference", "My Computer Path"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False) # Hide the numeric index
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLOR_DARK_CARD_BG};
                color: {COLOR_DARK_TEXT_MAIN};
                gridline-color: {COLOR_DARK_BORDER};
                border: 1px solid {COLOR_DARK_BORDER};
                border-radius: 8px;
            }}
            QHeaderView::section {{
                background-color: #181825;
                color: {COLOR_DARK_TEXT_MAIN};
                padding: 10px;
                border: none;
            }}
        """)
        self.populate_table()
        layout.addWidget(self.table)
        
        # Save Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_save = QPushButton("Save Variables")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_DARK_ACCENT};
                color: #1e1e2e;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 6px;
            }}
            QPushButton:hover {{ background-color: #d8b4fe; }}
        """)
        btn_save.clicked.connect(self.save_settings)
        btn_layout.addWidget(btn_save)
        
        layout.addLayout(btn_layout)
        
    def populate_table(self):
        vars = self.config_manager.variables
        self.table.setRowCount(len(vars) + 5) # Extra empty rows
        
        row = 0
        for k, v in vars.items():
            self.table.setItem(row, 0, QTableWidgetItem(k))
            self.table.setItem(row, 1, QTableWidgetItem(v))
            row += 1
            
        # Fill empty rows
        for r in range(row, row + 5):
            self.table.setItem(r, 0, QTableWidgetItem(""))
            self.table.setItem(r, 1, QTableWidgetItem(""))

    def save_settings(self):
        new_vars = {}
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            val_item = self.table.item(row, 1)
            
            if key_item and val_item:
                k = key_item.text().strip()
                v = val_item.text().strip()
                if k and v:
                    new_vars[k] = v
        
        self.config_manager.variables = new_vars
        self.config_manager.save_settings()
        print("Variables Saved")
