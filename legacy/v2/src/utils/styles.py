from PyQt6.QtGui import QColor

# --- Colors (Catppuccin Macchiato + Dracula Inspired) ---
COLOR_DARK_BG = "#1e1e2e"         # Base Base
COLOR_DARK_SIDEBAR = "#181825"    # Crust
COLOR_DARK_CARD_BG = "#313244"    # Surface0
COLOR_DARK_ACCENT = "#cba6f7"     # Mauve
COLOR_DARK_TEXT_MAIN = "#cdd6f4"  # Text
COLOR_DARK_TEXT_SEC = "#a6adc8"   # Subtext0
COLOR_DARK_BORDER = "#45475a"     # Surface1

# --- Dimensions ---
CARD_WIDTH_MIN = 280
CARD_HEIGHT = 160

def get_base_qss():
    return f"""
    QMainWindow, QWidget {{
        background-color: {COLOR_DARK_BG};
        color: {COLOR_DARK_TEXT_MAIN};
        font-family: 'Segoe UI', sans-serif;
    }}
    QScrollBar:vertical {{
        border: none;
        background: {COLOR_DARK_BG};
        width: 10px;
        margin: 0px 0px 0px 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {COLOR_DARK_BORDER};
        min-height: 20px;
        border-radius: 5px;
    }}
    """

def get_sidebar_qss():
    return f"""
    QFrame {{
        background-color: {COLOR_DARK_SIDEBAR};
        border-right: 1px solid {COLOR_DARK_BORDER};
    }}
    QPushButton {{
        background-color: transparent;
        color: {COLOR_DARK_TEXT_SEC};
        text-align: left;
        padding: 12px 20px;
        border: none;
        font-size: 11pt;
    }}
    QPushButton:hover {{
        background-color: {COLOR_DARK_CARD_BG};
        color: {COLOR_DARK_TEXT_MAIN};
        border-left: 3px solid {COLOR_DARK_ACCENT};
    }}
    """
