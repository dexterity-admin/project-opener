from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
import os
from src.utils.styles import COLOR_DARK_TEXT_MAIN, COLOR_DARK_BG

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Project Opener")
        self.setMinimumSize(400, 300)
        
        # Apply Base Style
        self.setStyleSheet(f"background-color: {COLOR_DARK_BG}; color: {COLOR_DARK_TEXT_MAIN};")

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        # Info Text
        info_label = QLabel(
            "<h2 style='text-align: center;'>Project Opener</h2>"
            "<p style='text-align: center; font-size: 14px;'>"
            "<b>Developed by:</b> Vikram & Yokesh<br>"
            "<b>Developed for:</b> Dexterity Design Services<br><br>"
            "<i>Engineering Workflow Hub Edition</i>"
            "</p>"
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addStretch(1)

        # Close Button
        btn = QPushButton("Close")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #313244; 
                color: #cdd6f4;
                border: 1px solid #45475a;
                padding: 8px 16px;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: #45475a;
            }}
        """)
        btn.clicked.connect(self.accept)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(btn)
        button_layout.addStretch(1)
        layout.addLayout(button_layout)
