# -*- coding: utf-8 -*-
import os
import sys
import json
import time
from datetime import datetime
import re

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QFileDialog, QLineEdit, QTextEdit, QScrollArea,
    QFrame, QDialog, QInputDialog, QMessageBox, QDialogButtonBox,
    QListWidgetItem, QSpacerItem, QSizePolicy, QStyle, QGraphicsDropShadowEffect,
    QCheckBox, QColorDialog, QTextBrowser
)
from PyQt6.QtCore import Qt, QUrl, QTimer, QSize, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QDesktopServices, QIcon, QKeyEvent, QColor, QPalette, QPainter, QPixmap
from PyQt6.QtWidgets import QStyleOptionButton, QLayout, QStyleOption


# --- Resource Path Helper ---
def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))
    return os.path.join(base_path, relative_path)


app_icon_path = resource_path("resources/1.ico")
if not os.path.exists(app_icon_path):
    print(f"Warning: App icon not found at {app_icon_path}", file=sys.stderr)
    app_icon_path = ""

# --- JSON Management & Settings ---
try:
    if sys.platform == "win32":
        config_dir = os.path.join(os.getenv('APPDATA'), "ProjectOpener")
    elif sys.platform == "darwin":
        config_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "ProjectOpener")
    else:  # Linux, etc.
        config_dir = os.path.join(os.path.expanduser("~"), ".config", "ProjectOpener")
except Exception:
    config_dir = os.path.join(os.path.expanduser("~"), "Documents", "ProjectOpener")
os.makedirs(config_dir, exist_ok=True)
PROJECTS_FILE = os.path.join(config_dir, "projects.json")
AUTO_LAUNCH_FILE = os.path.join(config_dir, "auto_launch.json")
SETTINGS_FILE = os.path.join(config_dir, "settings.json")

# --- Constants ---
DEFAULT_PROJECT_COLOR = "#e0e0e0"  # Slightly lighter default grey
MIN_CARD_WIDTH = 350  # Minimum width for project cards


# --- Load/Save Functions ---
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        print(f"Error saving settings: {e}", file=sys.stderr)


def load_projects():
    projects = {}
    if os.path.exists(PROJECTS_FILE):
        try:
            with open(PROJECTS_FILE, "r", encoding='utf-8') as f:
                projects_data = json.load(f)
            if not isinstance(projects_data, dict):
                print(f"Warning: Projects file '{PROJECTS_FILE}' does not contain a valid dictionary. Starting fresh.",
                      file=sys.stderr)
                return {}
            for name, proj_data in projects_data.items():
                if not isinstance(proj_data, dict):
                    print(f"Warning: Skipping invalid project entry '{name}'.", file=sys.stderr)
                    continue
                raw_files = proj_data.get("files", [])
                if not isinstance(raw_files, list):
                    print(f"Warning: 'files' for project '{name}' is not a list. Resetting.", file=sys.stderr)
                    raw_files = []
                new_files = []
                for item in raw_files:
                    if isinstance(item, dict) and "path" in item and isinstance(item.get("selected"), bool):
                        new_files.append(item)
                    elif isinstance(item, str):
                        # Convert old string format to new dict format
                        new_files.append({"path": item, "selected": True})
                proj_data["files"] = new_files
                # Ensure 'notes' exists and is a string
                if "notes" not in proj_data or not isinstance(proj_data.get("notes"), str):
                    proj_data["notes"] = ""
                # Ensure 'color' exists and is valid, else use default
                if "color" not in proj_data or not QColor(proj_data.get("color", "")).isValid():
                    proj_data["color"] = DEFAULT_PROJECT_COLOR
                # Ensure 'last_opened' exists (can be None)
                if "last_opened" not in proj_data:
                    proj_data["last_opened"] = None
                # Ensure 'pinned' exists (can be None/False or a timestamp)
                if "pinned" not in proj_data:
                    proj_data["pinned"] = None # Use None for not pinned, timestamp for pinned
                projects[name] = proj_data
        except json.JSONDecodeError:
            print(f"Error: Projects file '{PROJECTS_FILE}' corrupted.", file=sys.stderr)
            return {}
        except Exception as e:
            print(f"Error loading projects from {PROJECTS_FILE}: {e}", file=sys.stderr)
            return {}
    return projects


def save_projects(projects):
    try:
        with open(PROJECTS_FILE, "w", encoding='utf-8') as f:
            # Pinned status is now part of the project dict, so it gets saved automatically
            json.dump(projects, f, indent=4, default=str)
    except Exception as e:
        print(f"Error saving projects: {e}", file=sys.stderr)


def load_auto_launch():
    if os.path.exists(AUTO_LAUNCH_FILE):
        try:
            with open(AUTO_LAUNCH_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
                # Ensure only valid project names (present in projects) and boolean values are kept
                return {k: v for k, v in data.items() if isinstance(v, bool)}
        except json.JSONDecodeError:
            print(f"Error: Auto-launch file '{AUTO_LAUNCH_FILE}' corrupted.", file=sys.stderr)
            return {}
        except Exception as e:
            print(f"Error loading auto-launch: {e}", file=sys.stderr)
            return {}
    return {}


def save_auto_launch(auto_launch):
    try:
        with open(AUTO_LAUNCH_FILE, "w", encoding='utf-8') as f:
            json.dump(auto_launch, f, indent=4)
    except Exception as e:
        print(f"Error saving auto-launch: {e}", file=sys.stderr)


# --- Color Definitions & Brightness Function ---
COLOR_LIGHT_BG = "#f3f4f6" # Lighter gray
COLOR_LIGHT_BORDER = "#e5e7eb"
COLOR_LIGHT_BUTTON = "#ffffff"
COLOR_LIGHT_BUTTON_HOVER = "#f9fafb"
COLOR_LIGHT_ACCENT = "#3b82f6" # Vibrant blue
COLOR_LIGHT_SIDEBAR_BG = "#ffffff"
COLOR_LIGHT_SIDEBAR_FG = "#1f2937"
COLOR_LIGHT_STATUSBAR_BG = "#f3f4f6"

COLOR_DARK_BG = "#1e1e2e" # Deep blue-gray (Dracula/Catppuccin inspired)
COLOR_DARK_BORDER = "#313244" # Lighter mostly transparent
COLOR_DARK_BUTTON = "rgba(255, 255, 255, 0.05)"
COLOR_DARK_BUTTON_HOVER = "rgba(255, 255, 255, 0.1)"
COLOR_DARK_ACCENT = "#89b4fa" # Soft blue
COLOR_DARK_SIDEBAR_BG = "#181825" # Darker sidebar
COLOR_DARK_SIDEBAR_FG = "#cdd6f4" # Text color
COLOR_DARK_STATUSBAR_BG = "#11111b"

COLOR_TEXT_PRIMARY_ON_CARD = "#000000"
COLOR_TEXT_SECONDARY_ON_CARD = "#4b5563"



def adjust_color_brightness(hex_color, factor=1.2):
    if not hex_color: return "#ffffff"
    try:
        color = QColor(hex_color)
        if not color.isValid(): return "#ffffff"
        h, s, v, a = color.getHsv()
        new_v = max(0, min(255, int(v * factor)))
        hover_color = QColor.fromHsv(h, s, new_v, a)
        if QColor(hex_color).alpha() != 255:
            return hover_color.name(QColor.NameFormat.HexArgb)
        else:
            return hover_color.name(QColor.NameFormat.HexRgb)
    except Exception as e:
        print(f"Error adjusting color {hex_color}: {e}")
        return hex_color


def get_brightness(hex_color):
    try:
        color = QColor(hex_color)
        if not color.isValid(): return 128
        r = color.red()
        g = color.green()
        b = color.blue()
        # Standard luminance calculation
        return (r * 299 + g * 587 + b * 114) / 1000
    except Exception:
        return 128 # Default brightness


# --- Custom CheckBox ---
class CustomCheckBox(QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(20) # Ensure minimum height

    def paintEvent(self, event):
        super().paintEvent(event)
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        painter = QPainter(self)
        indicator_rect = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, opt, self)

        # Draw custom tick mark if checked
        if self.isChecked():
            painter.save()
            # Use a standard checkmark character
            tick_text = "✔"
            font = self.font()
            font.setPixelSize(int(indicator_rect.height() * 0.9)) # Adjust size based on indicator box
            painter.setFont(font)
            # Set tick color (adjust as needed, maybe based on theme)
            tick_color = QColor("#1a9c34") # A visible green
            painter.setPen(tick_color)
            painter.drawText(indicator_rect, Qt.AlignmentFlag.AlignCenter, tick_text)
            painter.restore()


try:
    import qtawesome as qta
except ImportError:
    qta = None


# --- Flow Layout ---
class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, hSpacing=-1, vSpacing=-1):
        super(FlowLayout, self).__init__(parent)
        self._hSpace = hSpacing
        self._vSpace = vSpacing
        self._itemList = []
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._itemList.append(item)

    def horizontalSpacing(self):
        if self._hSpace >= 0:
            return self._hSpace
        else:
            return self.smartSpacing(QStyle.PixelMetric.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self):
        if self._vSpace >= 0:
            return self._vSpace
        else:
            return self.smartSpacing(QStyle.PixelMetric.PM_LayoutVerticalSpacing)

    def count(self):
        return len(self._itemList)

    def itemAt(self, index):
        if 0 <= index < len(self._itemList):
            return self._itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._itemList):
            return self._itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super(FlowLayout, self).setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._itemList:
             size = size.expandedTo(item.minimumSize())
        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0
        spacingX = self.horizontalSpacing()
        spacingY = self.verticalSpacing()

        for item in self._itemList:
            wid = item.widget()
            spaceX = spacingX
            spaceY = spacingY
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()

    def smartSpacing(self, pm):
        parent = self.parent()
        if not parent:
            return -1
        elif parent.isWidgetType():
            return parent.style().pixelMetric(pm, None, parent)
        else:
            return parent.style().pixelMetric(pm, None, parent.parentWidget())


# ***** START OF THE SINGLE CHANGE AREA (Part 1/2) *****
# --- File Item Widget ---
class FileItemWidget(QWidget):
    # Add 'is_light_mode' parameter with a default (though it will always be passed)
    def __init__(self, file_path, selected=True, is_light_mode=True, parent=None):
        super().__init__(parent)
        # Use a horizontal layout with no extra top margin (closer to your original behavior)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2) # Reduced margins for compactness
        # Do not force vertical alignment via layout; instead, set a fixed height.
        self.setFixedHeight(self.fontMetrics().height() + 6) # Small padding around text height

        self.checkbox = CustomCheckBox("", self)
        self.checkbox.setObjectName("ListItemCheckbox")
        self.checkbox.setChecked(selected)
        layout.addWidget(self.checkbox)

        self.label = QLabel(file_path)
        self.label.setWordWrap(False) # Single-line display

        # Use the passed 'is_light_mode' flag directly
        if is_light_mode:
            self.label.setStyleSheet("color: #000000;") # Force black in light mode
        else:
            # In dark mode, rely on the global QSS for color
            self.label.setStyleSheet("") # Clear specific style to use theme/QSS color

        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.label.setFixedHeight(self.fontMetrics().height() + 4) # Ensure label height matches text + padding
        layout.addWidget(self.label)

        layout.addStretch() # Push content to the left

    def get_data(self):
        return {"path": self.label.text(), "selected": self.checkbox.isChecked()}
# ***** END OF THE SINGLE CHANGE AREA (Part 1/2) *****


# --- QSS Generation ---
def generate_qss(dark_mode=False):
    # Define colors based on mode
    bg = COLOR_DARK_BG if dark_mode else COLOR_LIGHT_BG
    border = COLOR_DARK_BORDER if dark_mode else COLOR_LIGHT_BORDER
    button_bg = COLOR_DARK_BUTTON if dark_mode else COLOR_LIGHT_BUTTON
    button_hover = COLOR_DARK_BUTTON_HOVER if dark_mode else COLOR_LIGHT_BUTTON_HOVER
    accent = COLOR_DARK_ACCENT if dark_mode else COLOR_LIGHT_ACCENT
    sidebar_bg = COLOR_DARK_SIDEBAR_BG if dark_mode else COLOR_LIGHT_SIDEBAR_BG
    sidebar_fg = COLOR_DARK_SIDEBAR_FG if dark_mode else COLOR_LIGHT_SIDEBAR_FG
    statusbar_bg = COLOR_DARK_STATUSBAR_BG if dark_mode else COLOR_LIGHT_STATUSBAR_BG
    general_fg = sidebar_fg # Use sidebar foreground for general text
    card_fg_primary = COLOR_TEXT_PRIMARY_ON_CARD # Always black for card titles for contrast
    card_fg_secondary = COLOR_TEXT_SECONDARY_ON_CARD # Always grey for card details
    scroll_handle = "rgba(255,255,255,0.3)" if dark_mode else "#cccccc"
    scroll_handle_hover = "rgba(255,255,255,0.5)" if dark_mode else "#aaaaaa"
    base_font = "'Segoe UI', sans-serif" # Cleaner font
    
    # Modern Glassmorphism touches
    card_radius = "12px"
    input_radius = "6px"

    # Define list item text color based on mode for default state
    # Note: Explicit black for light mode is now handled directly in FileItemWidget
    # We still define the default dark mode color here via general_fg
    list_item_fg = general_fg # Use theme color for dark mode items

    return f"""
 /* Global Styles */
 QMainWindow, QDialog, QWidget {{
     background-color: {bg};
     font-family: {base_font};
     color: {general_fg};
 }}
 QFrame {{
     background-color: transparent; /* Avoid overriding card backgrounds */
     border: none;
 }}
 QLabel {{
     border: none;
     padding: 0; /* Reset padding */
     background: transparent;
     color: {general_fg};
 }}
 QTextBrowser {{ /* For Help/About if used */
    background-color: {bg};
    color: {general_fg};
    border: 1px solid {border};
    border-radius: {input_radius};
 }}

 /* Input Fields */
 QLineEdit, QTextEdit {{
     color: {general_fg};
     background-color: {bg};
     border: 1px solid {border};
     padding: 8px;
     border-radius: {input_radius};
 }}
 QLineEdit:focus, QTextEdit:focus {{
     border: 1px solid {accent};
 }}
 QLineEdit#SearchBar {{ /* Specific styling for search */
     padding: 8px 12px;
     margin-bottom: 10px; /* Space below search */
     font-size: 11pt;
     background-color: {button_bg};
 }}

 /* List Widgets (like in Edit Dialog) */
 QListWidget {{
     border: 1px solid {border};
     border-radius: {input_radius};
     background-color: {bg};
 }}
 QListWidget::item {{
     padding: 8px;
     border-bottom: 1px solid {border}; /* Separator */
     color: {list_item_fg}; /* Default item text color (for dark mode) */
 }}
 QListWidget::item:last {{
     border-bottom: none; /* No border on last item */
 }}
 QListWidget::item:selected {{
     background-color: {adjust_color_brightness(accent, 0.8)}; /* Slightly darker accent */
     border-radius: 4px;
 }}
 /* Ensure text in selected item is readable (overrides FileItemWidget style on selection) */
 QListWidget::item:selected QLabel {{
     color: {COLOR_DARK_SIDEBAR_FG if get_brightness(accent) < 128 else COLOR_LIGHT_SIDEBAR_FG};
 }}
 QListWidget::item:selected CustomCheckBox::indicator {{
     border-color: {COLOR_DARK_SIDEBAR_FG if get_brightness(accent) < 128 else COLOR_LIGHT_SIDEBAR_FG};
 }}


 /* Status Bar */
 QStatusBar {{
     background-color: {statusbar_bg};
     color: {general_fg};
 }}

 /* Sidebar Specifics */
 #SidebarFrame {{
     background-color: {sidebar_bg};
     border-right: 1px solid {border};
     color: {sidebar_fg};
 }}
 #SidebarFrame QLabel {{ /* Labels within sidebar */
      color: {sidebar_fg};
 }}
 #TitleLabel {{
     font-size: 20pt;
     font-weight: 800;
     color: {sidebar_fg};
     margin: 20px 0;
     padding-left: 5px;
     letter-spacing: 0.5px;
 }}
 #SidebarFrame QPushButton {{ /* Buttons within sidebar */
     background-color: {button_bg};
     color: {sidebar_fg};
     border: 1px solid {border};
     padding: 10px 16px;
     margin: 6px 0; /* Vertical spacing */
     border-radius: 8px;
     font-size: 10pt;
     text-align: left; /* Modern sidebar look */
     padding-left: 20px;
 }}
 #SidebarFrame QPushButton:hover {{
     background-color: {button_hover};
     border: 1px solid {accent};
 }}
 #SidebarFrame QPushButton:pressed {{
     background-color: {accent};
     color: {COLOR_DARK_SIDEBAR_FG if get_brightness(accent) < 128 else COLOR_LIGHT_SIDEBAR_FG}; /* Ensure readable text on press */
 }}
 #SidebarFrame QCheckBox {{ /* Checkboxes within sidebar (e.g., Dark Mode) */
     color: {sidebar_fg};
     background: transparent;
     border: none;
     padding: 8px 5px;
     spacing: 8px; /* Space between indicator and text */
 }}
 #SidebarFrame QCheckBox::indicator {{
     width: 18px;
     height: 18px;
     border: 1px solid {sidebar_fg}; /* Border matches text color */
     background-color: transparent;
     border-radius: 4px;
 }}
 #SidebarFrame QCheckBox::indicator:checked {{
     background-color: {accent};
     border-color: {accent};
 }}

 /* Right Content Area */
 #RightContainer {{
     background-color: {bg}; /* Match main background */
 }}
 #ProjectsContainer {{
     background-color: {bg}; /* Match main background */
 }}

 /* Project Card Specifics */
 QFrame#ProjectCard {{
     border-radius: {card_radius};
 }}
 /* Ensure children inherit transparency */
 QFrame#ProjectCard > QWidget,
 QFrame#ProjectCard > QLayoutWidget {{
    background: transparent;
 }}
 /* Labels within the card */
 QFrame#ProjectCard QLabel {{
     background: transparent; /* No background */
     border: none; /* No border */
     padding: 0; /* Reset padding */
 }}
 QFrame#ProjectCard QLabel#ProjectName {{
     font-size: 14pt;
     font-weight: bold;
     color: {card_fg_primary}; /* Always black */
     padding: 0 2px; /* Minimal horizontal padding */
 }}
 QFrame#ProjectCard QLabel#FileCountLabel,
 QFrame#ProjectCard QLabel#TimestampLabel {{
     font-size: 9pt;
     color: {card_fg_secondary}; /* Always grey */
     padding: 0 5px; /* Padding for spacing */
 }}
 QFrame#ProjectCard QLabel#ProjectNotes {{
     font-size: 10pt;
     color: {card_fg_secondary}; /* Always grey */
     padding: 8px 2px; /* Padding around notes */
     line-height: 140%; /* Improve readability */
 }}

 /* Buttons within the card (Open, Edit, Delete, Pin) */
 QFrame#ProjectCard QPushButton {{
     background-color: transparent; /* Start transparent */
     color: {card_fg_secondary}; /* Grey icon/text */
     border: none; /* No border */
     padding: 6px; /* Padding around icon */
     border-radius: 6px; /* Slightly rounded */
     margin: 0 2px; /* Horizontal spacing between buttons */
     font-size: 12pt;
     min-width: 32px; /* Ensure clickable area */
     min-height: 32px;
 }}
 QFrame#ProjectCard QPushButton:hover {{
     color: {card_fg_primary}; /* Black on hover */
     background-color: rgba(0, 0, 0, 0.08); /* Subtle background highlight */
 }}
 QFrame#ProjectCard QPushButton:pressed {{
     background-color: {accent}; /* Use accent color on press */
     color: {COLOR_DARK_SIDEBAR_FG if get_brightness(accent) < 128 else COLOR_LIGHT_SIDEBAR_FG}; /* Ensure icon is visible */
 }}

 /* Auto Launch Checkbox within the card */
 QFrame#ProjectCard QCheckBox {{
     color: {card_fg_primary}; /* Black text */
     font-size: 9pt;
     background: transparent;
     border: none;
     padding: 4px 0px;
     spacing: 8px; /* Space between box and text */
 }}
 QFrame#ProjectCard QCheckBox::indicator {{
     width: 16px;
     height: 16px;
     border: 1px solid {card_fg_primary}; /* Black border */
     background-color: transparent; /* Match card background */
     border-radius: 4px;
 }}
 QFrame#ProjectCard QCheckBox::indicator:checked {{
      /* Custom check mark is drawn via paintEvent */
      border-color: {accent};
 }}

 /* Scroll Bar Styling */
 QScrollBar:vertical {{
     background: {bg}; /* Match background */
     width: 14px;
     margin: 0px; /* No margin */
     border: none; /* No border */
 }}
 QScrollBar::handle:vertical {{
     background: {scroll_handle}; /* Handle color */
     border-radius: 7px; /* Rounded handle */
     min-height: 30px; /* Minimum handle size */
     border: 3px solid {bg}; /* Padding effect */
 }}
 QScrollBar::handle:vertical:hover {{
     background: {scroll_handle_hover}; /* Hover color */
 }}
 QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
     height: 0px; /* Hide arrows */
     border: none;
     background: none;
 }}
 QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
     background: none; /* No background for track */
 }}

 /* Styling for CustomCheckBox when inside QListWidget (Edit Dialog) */
 QListWidget CustomCheckBox {{
    /* Inherits general widget style, might need adjustments if conflicting */
    color: {general_fg};
    background-color: transparent;
    border: none;
    padding: 0;
    margin: 0;
    spacing: 8px; /* Space between indicator and text (if any) */
 }}
 QListWidget CustomCheckBox::indicator {{
     width: 18px;
     height: 18px;
     border: 1px solid {general_fg}; /* Use general foreground color for border */
     background-color: {bg}; /* Match list background */
     border-radius: 4px;
     margin-right: 8px; /* Space indicator from the label */
 }}
 QListWidget CustomCheckBox::indicator:checked {{
     /* Custom check mark drawn via paintEvent */
 }}
    """


# --- Custom File List Widget (Edit Dialog) ---
class FileListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection) # Allow multiple selections
        self.setWordWrap(False) # Keep paths on one line
        self.setUniformItemSizes(False) # Allow items to have different heights if needed

    def keyPressEvent(self, event: QKeyEvent):
        # Handle Delete key press for removing selected items
        if event.key() == Qt.Key.Key_Delete:
            items = self.selectedItems()
            if items:
                # Confirmation dialog
                reply = QMessageBox.question(self, "Confirm Item Removal",
                                             # Use simple text, styling can be inconsistent across platforms
                                             f"Remove {len(items)} selected item(s) from this project?",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                             QMessageBox.StandardButton.No) # Default to No
                if reply == QMessageBox.StandardButton.Yes:
                    # Remove items in reverse order to avoid index issues
                    indices_to_remove = sorted([self.row(item) for item in items], reverse=True)
                    for index in indices_to_remove:
                        item = self.item(index)
                        widget = self.itemWidget(item)
                        # Also remove from the dialog's internal data structure
                        if widget and isinstance(self.parent(), EditProjectDialog):
                            file_path = widget.label.text()
                            # Filter out the item based on path
                            self.parent().internal_files_data = [
                                file_data for file_data in self.parent().internal_files_data
                                if file_data.get("path") != file_path
                            ]
                        self.takeItem(index) # Remove item from the visual list
        else:
            super().keyPressEvent(event) # Pass other key events to the base class


# --- About Dialog ---
class AboutDialog(QDialog):
    def __init__(self, parent=None, dark_mode=False):
        super().__init__(parent)
        self.setWindowTitle("About Project Opener")
        self.setMinimumSize(400, 350) # Adjusted size

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # App Icon
        if app_icon_path and os.path.exists(app_icon_path):
            icon_label = QLabel()
            icon = QIcon(app_icon_path)
            pixmap = icon.pixmap(QSize(96, 96)) # Larger icon
            icon_label.setPixmap(pixmap)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon_label)

        # Info Text (Using simple HTML for bolding)
        info_label = QLabel(
            "<b>Project Opener</b><br><br>"
            "Developed by: Vikram & Yokesh<br>"
            "Developed for Dexterity Design Services<br><br>"
            "<i>Configuration stored in:</i><br>" + config_dir
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addStretch(1) # Pushes button to the bottom

        # Close Button
        btn = QPushButton("Close")
        btn.clicked.connect(self.accept) # Closes the dialog
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(btn)
        button_layout.addStretch(1)
        layout.addLayout(button_layout)


# --- Help Dialog ---
class HelpDialog(QDialog):
    def __init__(self, parent=None, dark_mode=False):
        super().__init__(parent)
        self.setWindowTitle("Project Opener - Help")
        self.setMinimumSize(600, 500)
        self.dark_mode = dark_mode

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Use QTextBrowser for rich text display
        self.help_content = QTextBrowser()
        self.help_content.setOpenExternalLinks(True) # Allow opening links if any
        self.help_content.setReadOnly(True)
        self.populate_help_text() # Fill with content
        layout.addWidget(self.help_content, 1) # Allow browser to expand

        # Close Button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(close_button)
        button_layout.addStretch(1)
        layout.addLayout(button_layout)

    def populate_help_text(self):
        # Basic HTML structure for formatting
        help_html = """
        <!DOCTYPE html>
        <html><head><style>
            /* Basic styling for readability */
            body {{ line-height: 1.6; }}
            h1 {{ border-bottom: 1px solid #ccc; padding-bottom: 5px; margin-bottom: 15px;}}
            h2 {{ margin-top: 20px; margin-bottom: 10px;}}
            ul, ol {{ margin-left: 20px; }}
            li {{ margin-bottom: 5px; }}
            code {{ background-color: rgba(128, 128, 128, 0.2); padding: 2px 4px; border-radius: 3px; }}
            b {{ font-weight: bold; }}
            i {{ font-style: italic; }}
            .pin-icon {{ font-size: 1.1em; display: inline-block; width: 1em; text-align: center; }} /* Style for pin icons */
        </style></head><body>
        <h1>Project Opener - Usage Guide</h1>
        <p>Welcome! This tool helps you quickly open related files, folders, and links for your projects.</p>

        <h2>Core Concepts</h2>
        <ul>
            <li><b>Project:</b> A named collection for your items and notes.</li>
            <li><b>Project Card:</b> Shows info about one project with buttons to Open, Edit, Remove, and Pin/Unpin it.</li>
            <li><b>Sidebar:</b> Contains main actions (Add, Import/Export) and Settings.</li>
        </ul>

        <h2>Getting Started</h2>
        <ol>
            <li><b>Add a Project:</b>
                <ul>
                    <li>Click "Add Project" in the sidebar.</li>
                    <li>Enter a unique name.</li>
                    <li>Pick a background color for the project's card.</li>
                    <li>Your new (empty) project card appears.</li>
                </ul>
            </li>
            <li><b>Edit & Add Items:</b>
                <ul>
                    <li>Click the <b>Edit</b> button (<span class="pin-icon">📝</span> or similar) on the card.</li>
                    <li>You can add files using the "Add File", "Add Folder", "Add Link" buttons or by dragging and dropping files/folders into the list area.</li>
                    <li>Toggle each file’s checkbox to select/unselect it for opening.</li>
                    <li>Add optional notes.</li>
                    <li>Click "Save".</li>
                </ul>
            </li>
            <li><b>Open Items:</b>
                <ul>
                    <li>Click the <b>Open</b> button (<span class="pin-icon">📂</span>) on the card.</li>
                    <li>Only the items with checked boxes will be opened.</li>
                </ul>
            </li>
            <li><b>Pinning Projects:</b>
                <ul>
                    <li>Click the Pin button (<span class="pin-icon">📍</span>) on a card to pin it to the top. The icon changes (<span class="pin-icon">📌</span>).</li>
                    <li>Pinned projects appear first, in the order they were pinned.</li>
                    <li>Click the Unpin button (<span class="pin-icon">📌</span>) to unpin it. It will return to its alphabetical position among unpinned projects.</li>
                </ul>
            </li>
        </ol>

        <h2>Project Card Details</h2>
        <ul>
            <li><b>Name & Color:</b> Your chosen project name and background color.</li>
            <li><b>Items Count:</b> Format: <code>Checked/Total</code> (e.g., <code>3/7 Items</code>).</li>
            <li><b>Buttons (Left to Right):</b>
                <ul>
                    <li><span class="pin-icon">📂</span> (Open): Opens checked items.</li>
                    <li><span class="pin-icon">📝</span> (Edit): Modify project details & items (Icon may vary).</li>
                    <li><span class="pin-icon">⛔</span> (Remove): Deletes the project (prompts for confirmation).</li>
                    <li><span class="pin-icon">📍</span> / <span class="pin-icon">📌</span> (Pin/Unpin): Toggles the project's pinned status.</li>
                </ul>
            </li>
            <li><b>Auto Launch Checkbox:</b> Enables automatic opening of checked items on startup.</li>
            <li><b>Notes:</b> Displays your project notes. The card adjusts vertically if the notes are long.</li>
            <li><b>Last Opened:</b> Shows when the project was last opened.</li>
        </ul>

        <h2>Editing Project Items (in Edit Dialog)</h2>
        <ul>
            <li><b>Check/Uncheck:</b> Toggle the checkbox beside each file to include/exclude it from opening.</li>
            <li><b>Drag and Drop:</b> Drag files or folders directly into the project items list to add them.</li>
            <li><b>Remove Item(s):</b> Select an item (or items) and press the <code>Delete</code> key to remove them.</li>
            <li><b>Change Color:</b> Click "Change..." next to the color preview to select a new card background.</li>
            <li><b>Save As New:</b> Saves a new project based on the current selection and notes.</li>
        </ul>

        <h2>Other Features</h2>
        <ul>
            <li><b>Search:</b> Use the search bar to filter projects by name or notes.</li>
            <li><b>Import/Export:</b> Backup or restore all projects/settings via a JSON file.</li>
            <li><b>Dark Mode:</b> Toggle between dark and light mode using the sidebar checkbox.</li>
            <li><b>About/Help:</b> Access additional information and usage instructions.</li>
        </ul>
        <p><i>Tip: Project cards have a minimum width but adjust height for notes. Pinned items always appear first.</i></p>
        </body></html>
        """
        self.help_content.setHtml(help_html)


# --- Main Window ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.dark_mode = self.settings.get("dark_mode", False)
        self.projects = load_projects() # Load includes pinned status now
        self.auto_launch = load_auto_launch()
        self.setWindowTitle("Project Opener")
        if app_icon_path:
            try:
                self.setWindowIcon(QIcon(app_icon_path)) # Use correct path
            except Exception as e:
                print(f"Warning: Could not set window icon: {e}", file=sys.stderr)

        self.setMinimumSize(1000, 600)
        self._project_card_widgets = {} # Cache for project card widgets
        self.init_ui()
        self.apply_style() # Apply initial style
        self.refresh_projects() # Initial display of projects
        QTimer.singleShot(700, self.auto_launch_projects) # Delay auto-launch slightly

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # --- Sidebar ---
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("SidebarFrame")
        self.sidebar_frame.setMinimumWidth(240)
        self.sidebar_frame.setMaximumWidth(300) # Limit sidebar width
        sidebar_layout = QVBoxLayout(self.sidebar_frame)
        sidebar_layout.setSpacing(10)
        sidebar_layout.setContentsMargins(15, 15, 15, 15)

        title_label = QLabel("Project Opener")
        title_label.setObjectName("TitleLabel")
        sidebar_layout.addWidget(title_label)

        add_btn = QPushButton("Add Project")
        add_btn.clicked.connect(self.add_project)
        sidebar_layout.addWidget(add_btn)

        import_btn = QPushButton("Import Projects")
        import_btn.clicked.connect(self.import_projects)
        sidebar_layout.addWidget(import_btn)

        export_btn = QPushButton("Export Projects")
        export_btn.clicked.connect(self.export_projects)
        sidebar_layout.addWidget(export_btn)

        about_btn = QPushButton("About")
        about_btn.setObjectName("AboutButton")
        about_btn.setToolTip(f"Application Info\nConfig: {config_dir}")
        about_btn.clicked.connect(self.show_about_dialog)
        sidebar_layout.addWidget(about_btn)

        help_btn = QPushButton("Help")
        help_btn.setObjectName("HelpButton")
        help_btn.setToolTip("Show Usage Guide")
        help_btn.clicked.connect(self.show_help_dialog)
        sidebar_layout.addWidget(help_btn)

        sidebar_layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)) # Push settings down

        settings_label = QLabel("Settings")
        settings_label.setStyleSheet("font-weight: bold; margin-top: 10px; padding-left: 5px;")
        sidebar_layout.addWidget(settings_label)

        self.dark_mode_checkbox = CustomCheckBox("Dark Mode")
        self.dark_mode_checkbox.setObjectName("DarkModeCheckbox")
        self.dark_mode_checkbox.setChecked(self.dark_mode)
        self.dark_mode_checkbox.toggled.connect(self.toggle_dark_mode)
        sidebar_layout.addWidget(self.dark_mode_checkbox)

        main_layout.addWidget(self.sidebar_frame, 0) # Sidebar takes fixed width

        # --- Right Content Area ---
        self.right_container = QFrame()
        self.right_container.setObjectName("RightContainer")
        right_layout = QVBoxLayout(self.right_container)
        right_layout.setSpacing(0) # No spacing between search and scroll area
        right_layout.setContentsMargins(0, 0, 0, 0) # No internal margins

        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("SearchBar")
        self.search_bar.setPlaceholderText("Search Projects...")
        self.search_bar.textChanged.connect(self.filter_projects) # Filter as user types
        right_layout.addWidget(self.search_bar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True) # Important for layout
        self.scroll_area.setStyleSheet("QScrollArea { border: none; }") # Remove scroll area border
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff) # No horizontal scroll
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded) # Vertical scroll as needed

        self.projects_container = QWidget() # Container for project cards
        self.projects_container.setObjectName("ProjectsContainer")
        self.projects_layout = FlowLayout(self.projects_container, margin=20, hSpacing=20, vSpacing=20)

        self.scroll_area.setWidget(self.projects_container)
        right_layout.addWidget(self.scroll_area, 1) # Scroll area takes remaining space

        main_layout.addWidget(self.right_container, 1) # Right side takes expanding width

        self.statusBar().showMessage("Ready")

    def show_about_dialog(self):
        dialog = AboutDialog(self, self.dark_mode)
        dialog.setStyleSheet(self.styleSheet()) # Apply current theme
        dialog.exec()

    def show_help_dialog(self):
        dialog = HelpDialog(self, self.dark_mode)
        dialog.setStyleSheet(self.styleSheet()) # Apply current theme
        dialog.exec()

    def apply_style(self):
        qss = generate_qss(self.dark_mode)
        self.setStyleSheet(qss)
        # Re-apply dynamic card styles after global QSS change
        self.apply_project_card_styles()
        self.statusBar().showMessage(f"{'Dark' if self.dark_mode else 'Light'} mode active. Ready.")

    def apply_project_card_styles(self):
        # Apply individual background, border, hover colors based on project settings
        for name, widget in self._project_card_widgets.items():
            if not widget or name not in self.projects:
                continue

            project_data = self.projects[name]
            base_color_hex = project_data.get("color", DEFAULT_PROJECT_COLOR)
            base_color = QColor(base_color_hex)
            if not base_color.isValid():
                base_color = QColor(DEFAULT_PROJECT_COLOR)
                base_color_hex = DEFAULT_PROJECT_COLOR

            brightness = get_brightness(base_color_hex)
            # Adjust hover/border based on brightness for better visibility
            hover_factor = 0.92 if brightness > 128 else 1.15
            border_factor = 0.95 if brightness > 128 else 1.10
            hover_color = adjust_color_brightness(base_color_hex, hover_factor)
            border_color = adjust_color_brightness(base_color_hex, border_factor)

            # Apply drop shadow for depth
            shadow = widget.graphicsEffect()
            if not isinstance(shadow, QGraphicsDropShadowEffect):
                shadow = QGraphicsDropShadowEffect(widget)
                widget.setGraphicsEffect(shadow)
            shadow.setBlurRadius(15)
            shadow.setOffset(3, 3)
            # Subtle shadow color based on theme
            shadow_color = QColor(0, 0, 0, 90) if not self.dark_mode else QColor(220, 220, 255, 60)
            shadow.setColor(shadow_color)
            shadow.setEnabled(True)

            # Set dynamic CSS for the card
            # Include base QSS for card elements that don't change with color
            base_card_qss = f"""
                QFrame#ProjectCard QLabel#ProjectName {{ color: {COLOR_TEXT_PRIMARY_ON_CARD}; }}
                QFrame#ProjectCard QLabel#FileCountLabel,
                QFrame#ProjectCard QLabel#TimestampLabel,
                QFrame#ProjectCard QLabel#ProjectNotes {{ color: {COLOR_TEXT_SECONDARY_ON_CARD}; }}
                QFrame#ProjectCard QPushButton {{ color: {COLOR_TEXT_SECONDARY_ON_CARD}; }}
                QFrame#ProjectCard QPushButton:hover {{ color: {COLOR_TEXT_PRIMARY_ON_CARD}; }}
                QFrame#ProjectCard QCheckBox {{ color: {COLOR_TEXT_PRIMARY_ON_CARD}; }}
                QFrame#ProjectCard QCheckBox::indicator {{ border-color: {COLOR_TEXT_PRIMARY_ON_CARD}; }}
            """
            widget.setStyleSheet(f"""
                QFrame#ProjectCard {{
                    background-color: {base_color_hex};
                    border: 1px solid {border_color};
                    border-radius: 10px;
                }}
                QFrame#ProjectCard:hover {{
                    background-color: {hover_color};
                    border: 1px solid {adjust_color_brightness(border_color, 1.1)}; /* Slightly stronger border on hover */
                }}
                /* Ensure button hover inside card uses adjusted hover color */
                QFrame#ProjectCard QPushButton:hover {{
                    background-color: {adjust_color_brightness(hover_color, 1.0 if brightness > 128 else 1.1)};
                }}
                /* Keep non-button labels transparent (override general label styles) */
                QFrame#ProjectCard QLabel {{ background: transparent; border: none; padding: 0; }}
                QFrame#ProjectCard QCheckBox {{ background: transparent; border: none; }}
                QFrame#ProjectCard QCheckBox::indicator {{ background-color: transparent; }}
                /* Apply base text/icon colors */
                {base_card_qss}
            """)

    def toggle_dark_mode(self, checked):
        self.dark_mode = checked
        self.settings["dark_mode"] = self.dark_mode
        save_settings(self.settings)
        self.apply_style() # Re-apply all styles
        self.refresh_projects() # Refresh needed to update FileItemWidget colors

    def refresh_projects(self):
        """Refreshes the project display area, sorting by pin status then alphabetically."""
        search_term = self.search_bar.text() # Preserve search term
        current_project_names = set(self.projects.keys())
        existing_widget_names = set(self._project_card_widgets.keys())

        # 1. Remove widgets for projects that no longer exist
        names_to_remove = existing_widget_names - current_project_names
        for name in names_to_remove:
            widget = self._project_card_widgets.pop(name, None)
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        # 2. Sorting Logic: Pinned first (by timestamp), then Unpinned (alphabetically)
        pinned_projects = []
        unpinned_projects = []
        for name, data in self.projects.items():
            if not isinstance(data, dict):
                print(f"Warning: Invalid data for project '{name}', skipping display.", file=sys.stderr)
                continue
            # Check if 'pinned' exists and is a valid timestamp (float or int)
            pinned_timestamp = data.get("pinned")
            if isinstance(pinned_timestamp, (float, int)) and pinned_timestamp > 0:
                pinned_projects.append((name, pinned_timestamp))
            else:
                # Ensure invalid 'pinned' values are treated as unpinned
                if pinned_timestamp is not None:
                    data['pinned'] = None # Correct invalid data
                unpinned_projects.append(name)

        # Sort pinned projects by pin timestamp (ascending - oldest pin first)
        pinned_projects.sort(key=lambda item: item[1])
        # Sort unpinned projects alphabetically (case-insensitive)
        unpinned_projects.sort(key=str.lower)

        # Combine the lists: pinned first, then unpinned
        sorted_names = [name for name, ts in pinned_projects] + unpinned_projects

        # 3. Create/Update and reorder widgets in the layout
        items_in_layout_order = []
        for name in sorted_names:
            widget = self._project_card_widgets.get(name)
            if not widget: # Create widget if it doesn't exist
                widget = self.create_project_card(name)
                self._project_card_widgets[name] = widget
            # Always update content (incl. pin icon) as data might have changed
            self.update_project_card_content(widget, name)
            items_in_layout_order.append(widget)

        # 4. Efficiently clear and repopulate the layout
        # Temporarily disable updates to the layout for performance
        self.projects_layout.setEnabled(False)
        while self.projects_layout.count():
            item = self.projects_layout.takeAt(0)
            if item and item.widget():
                # Set parent to None *before* adding back, avoids potential issues
                item.widget().setParent(None)

        # Add widgets back in the new sorted order
        for widget in items_in_layout_order:
            self.projects_layout.addWidget(widget)
            widget.setParent(self.projects_container) # Ensure correct parentage

        # Re-enable layout updates
        self.projects_layout.setEnabled(True)
        self.projects_layout.update() # Force layout update

        # 5. Update auxiliary UI elements
        self.update_no_projects_label(len(current_project_names))
        self.apply_project_card_styles() # Apply colors/shadows after layout changes
        self.filter_projects(search_term) # Re-apply filter to the newly ordered list

        # 6. Adjust container size and scroll to top (deferred slightly for stability)
        QTimer.singleShot(10, self.projects_container.adjustSize)
        QTimer.singleShot(20, lambda: self.scroll_area.ensureVisible(0, 0)) # Scroll to top


    def update_no_projects_label(self, project_count):
        # Find existing label
        no_projects_label = self.projects_container.findChild(QLabel, "NoProjectsLabel")

        # Show label only if there are no projects AND no active search filter
        if project_count == 0 and not self.search_bar.text():
            if not no_projects_label:
                lbl = QLabel("No projects added yet.\nClick 'Add Project' in the sidebar.")
                lbl.setObjectName("NoProjectsLabel")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                # Use secondary text color from theme
                text_color = COLOR_TEXT_SECONDARY_ON_CARD # Grey
                lbl.setStyleSheet(f"color: {text_color}; padding: 30px; font-style: italic;")
                # Ensure it's added correctly even if layout is empty
                self.projects_layout.insertWidget(0, lbl)
        else:
            # Remove label if it exists and shouldn't be shown
            if no_projects_label:
                no_projects_label.setParent(None)
                no_projects_label.deleteLater()

    def create_project_card(self, name):
        card = QFrame()
        card.setObjectName("ProjectCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum) # Expand width, minimum height
        card.setMinimumWidth(MIN_CARD_WIDTH)
        card.setProperty("projectName", name) # Store name for reference

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(6) # Spacing between elements
        card_layout.setContentsMargins(12, 10, 12, 10) # Padding inside the card

        # --- Top Row: Name and File Count ---
        top_row_layout = QHBoxLayout()
        project_name_label = QLabel(name)
        project_name_label.setObjectName("ProjectName")
        project_name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred) # Name takes available space
        top_row_layout.addWidget(project_name_label)

        count_label = QLabel() # Placeholder for "X/Y Items"
        count_label.setObjectName("FileCountLabel")
        count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top_row_layout.addWidget(count_label)
        card_layout.addLayout(top_row_layout)

        # --- Action Row: Buttons ---
        action_row_layout = QHBoxLayout()
        action_row_layout.setSpacing(5) # Spacing between buttons
        style = QApplication.style()
        icon_size = QSize(16, 16) # Standard size for icons

        # Open Button (📂)
        open_btn = QPushButton()
        # Use text icon for better cross-platform consistency? Or standard pixmap? Let's try text.
        if qta:
            open_btn.setIcon(qta.icon('fa5s.folder-open', color=COLOR_DARK_ACCENT if self.dark_mode else COLOR_TEXT_SECONDARY_ON_CARD))
            open_btn.setIconSize(QSize(20, 20))
        else:
            open_btn.setText("📂")
        open_btn.setToolTip("Open Checked Items")
        open_btn.setObjectName("OpenButton")
        open_btn.clicked.connect(lambda checked=False, n=name: self.open_project(n))
        action_row_layout.addWidget(open_btn)

        # Edit Button (📝)
        edit_btn = QPushButton()
        if qta:
            edit_btn.setIcon(qta.icon('fa5s.pen', color=COLOR_TEXT_SECONDARY_ON_CARD))
            edit_btn.setIconSize(QSize(18, 18))
        else:
            edit_btn.setText("📝")
        edit_btn.setToolTip("Edit Project Details")
        edit_btn.setObjectName("EditButton")
        edit_btn.clicked.connect(lambda checked=False, n=name: self.edit_project(n))
        action_row_layout.addWidget(edit_btn)

        # Remove Button (⛔)
        remove_btn = QPushButton()
        if qta:
            remove_btn.setIcon(qta.icon('fa5s.trash-alt', color=COLOR_TEXT_SECONDARY_ON_CARD))
            remove_btn.setIconSize(QSize(18, 18))
        else:
            remove_btn.setText("⛔")
        remove_btn.setToolTip("Remove Project")
        remove_btn.setObjectName("RemoveButton")
        remove_btn.clicked.connect(lambda checked=False, n=name: self.remove_project(n))
        action_row_layout.addWidget(remove_btn)

        # Pin/Unpin Button (Set icon/text in update_project_card_content)
        pin_btn = QPushButton()
        pin_btn.setObjectName("PinButton") # Name used to find the button later
        pin_btn.clicked.connect(lambda checked=False, n=name: self.toggle_pin_project(n))
        action_row_layout.addWidget(pin_btn)


        action_row_layout.addStretch(1) # Push Auto Launch checkbox to the right

        # Auto Launch Checkbox
        auto_checkbox = CustomCheckBox("Auto Launch")
        auto_checkbox.setObjectName("AutoLaunchCheckbox")
        auto_checkbox.setToolTip("Automatically Open Checked Items on Startup")
        auto_checkbox.setFixedWidth(95) # Fixed width for consistent alignment
        auto_checkbox.stateChanged.connect(
            lambda state, n=name: self.toggle_auto_launch(n, state == Qt.CheckState.Checked.value)
        )
        action_row_layout.addWidget(auto_checkbox)
        card_layout.addLayout(action_row_layout)

        # --- Notes Area ---
        note_label = QLabel()
        note_label.setObjectName("ProjectNotes")
        note_label.setWordWrap(True)
        note_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        note_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum) # Expand width, minimum height
        card_layout.addWidget(note_label)

        # --- Timestamp Area ---
        timestamp_label = QLabel()
        timestamp_label.setObjectName("TimestampLabel")
        timestamp_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        card_layout.addWidget(timestamp_label)

        # Populate content and apply dynamic styles
        self.update_project_card_content(card, name) # Includes pin button update

        return card


    def update_project_card_content(self, card_widget, project_name):
        """Updates the content displayed on a project card widget."""
        if not card_widget or project_name not in self.projects:
            print(f"Warning: update_project_card_content called for invalid state ({project_name})", file=sys.stderr)
            return

        project_data = self.projects[project_name]
        content_changed = False # Flag to check if redraw needed

        # Update Project Name Label
        if name_label := card_widget.findChild(QLabel, "ProjectName"):
            if name_label.text() != project_name:
                name_label.setText(project_name)
                content_changed = True

        # Update File Count Label
        files = project_data.get("files", [])
        total_count = len(files)
        selected_count = sum(1 for item in files if isinstance(item, dict) and item.get("selected", True))
        count_text = f"{selected_count}/{total_count} Items"
        if count_label := card_widget.findChild(QLabel, "FileCountLabel"):
            if count_label.text() != count_text:
                count_label.setText(count_text)
                content_changed = True

        # Update Notes Label
        if notes_label := card_widget.findChild(QLabel, "ProjectNotes"):
            notes = project_data.get("notes", "").strip()
            current_text = notes_label.text()
            is_visible = notes_label.isVisible()
            should_be_visible = bool(notes) # Visible only if notes exist
            if current_text != notes or is_visible != should_be_visible:
                notes_label.setText(notes)
                # Set tooltip only if notes are long
                notes_label.setToolTip(notes if len(notes) > 100 else "")
                notes_label.setVisible(should_be_visible)
                content_changed = True

        # Update Timestamp Label
        if timestamp_label := card_widget.findChild(QLabel, "TimestampLabel"):
            last_opened_ts = project_data.get("last_opened")
            display_time = "Never Opened"
            tooltip_time = "" # Full timestamp for tooltip
            if last_opened_ts:
                try:
                    dt_object = datetime.fromtimestamp(float(last_opened_ts))
                    now = datetime.now()
                    delta = now - dt_object

                    # Relative time formatting
                    if delta.days == 0:
                        if delta.seconds < 60: display_time = "Opened: Just now"
                        elif delta.seconds < 3600: display_time = f"Opened: {delta.seconds // 60}m ago"
                        else: display_time = f"Opened: {delta.seconds // 3600}h ago"
                    elif delta.days == 1: display_time = "Opened: Yesterday"
                    elif delta.days < 7: display_time = f"Opened: {delta.days}d ago"
                    else: display_time = f"Opened: {dt_object.strftime('%Y-%m-%d')}" # Older than a week

                    tooltip_time = f"Last Opened: {dt_object.strftime('%Y-%m-%d %H:%M:%S')}"
                except (ValueError, TypeError, OSError):
                    display_time = "Invalid Date" # Handle potential errors

            if timestamp_label.text() != display_time:
                timestamp_label.setText(display_time)
                content_changed = True
            timestamp_label.setToolTip(tooltip_time)

        # Update Auto Launch Checkbox State
        if auto_checkbox := card_widget.findChild(CustomCheckBox, "AutoLaunchCheckbox"):
            is_auto = self.auto_launch.get(project_name, False)
            if auto_checkbox.isChecked() != is_auto:
                auto_checkbox.blockSignals(True) # Prevent triggering signal during update
                auto_checkbox.setChecked(is_auto)
                auto_checkbox.blockSignals(False) # Re-enable signals

        # Update Pin Button Icon and Tooltip
        if pin_btn := card_widget.findChild(QPushButton, "PinButton"):
            # Check the 'pinned' status - True if it's a valid timestamp > 0
            pinned_timestamp = project_data.get("pinned")
            is_pinned = isinstance(pinned_timestamp, (float, int)) and pinned_timestamp > 0

            current_tooltip = pin_btn.toolTip()
            # Use distinct icons/colors for pinned state
            new_tooltip = "Unpin Project" if is_pinned else "Pin Project to Top"
            
            # Check if update is needed (using tooltip as a proxy for state change)
            if pin_btn.toolTip() != new_tooltip:
                pin_btn.setToolTip(new_tooltip)
                
                if qta:
                    # Choose color based on state
                    if is_pinned:
                        # PINNED: Accent color (High visibility)
                        icon_color = COLOR_DARK_ACCENT if self.dark_mode else COLOR_LIGHT_ACCENT
                        # Use a slightly larger/solid icon
                        pin_btn.setIcon(qta.icon('fa5s.thumbtack', color=icon_color))
                    else:
                        # UNPINNED: Grey/dimmed (Low visibility)
                        pin_btn.setIcon(qta.icon('fa5s.thumbtack', color=COLOR_TEXT_SECONDARY_ON_CARD, opacity=0.5))
                    
                    pin_btn.setIconSize(QSize(18, 18))
                    pin_btn.setText("") # Clear text if using icon
                else:
                    # Fallback to emoji
                    pin_btn.setText("📍" if is_pinned else "📌")
                
                content_changed = True


        # If content changed, trigger layout update and size adjustment
        if content_changed:
            # Use activate() for immediate layout recalculation if needed,
            # but adjustSize() should handle most visual updates.
            # card_widget.layout().activate()
            card_widget.adjustSize() # Adjust widget size to content

    def toggle_pin_project(self, name):
        """Toggles the pinned state of a project and refreshes the list."""
        if name not in self.projects:
            print(f"Error: Cannot toggle pin for non-existent project '{name}'", file=sys.stderr)
            return

        project_data = self.projects[name]
        pinned_timestamp = project_data.get("pinned")
        is_currently_pinned = isinstance(pinned_timestamp, (float, int)) and pinned_timestamp > 0

        if is_currently_pinned:
            # Unpin: Set pinned status to None
            project_data["pinned"] = None
            self.statusBar().showMessage(f"Project '{name}' unpinned.")
        else:
            # Pin: Set pinned status to current timestamp
            project_data["pinned"] = time.time()
            self.statusBar().showMessage(f"Project '{name}' pinned.")

        save_projects(self.projects) # Save the updated pinned status
        self.refresh_projects() # Re-sort and update the display immediately


    def add_project(self):
        name, ok = QInputDialog.getText(self, "Add New Project", "Enter project name:")
        if not ok or not name:
            return # User cancelled or entered empty name

        clean_name = name.strip()
        if not clean_name:
            QMessageBox.warning(self, "Invalid Name", "Project name cannot be empty.")
            return
        if clean_name in self.projects:
            QMessageBox.warning(self, "Duplicate Name", f"A project named '{clean_name}' already exists!")
            return

        # Ask for color
        initial_color = QColor(DEFAULT_PROJECT_COLOR)
        color = QColorDialog.getColor(initial_color, self, "Select Project Card Color",
                                      QColorDialog.ColorDialogOption.ShowAlphaChannel) # Allow transparency

        if not color.isValid():
            # Ask if default color should be used if none selected
            reply = QMessageBox.question(self, "Color Not Selected",
                                         "No color was selected. Use the default background color?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.Yes)
            if reply == QMessageBox.StandardButton.No:
                self.statusBar().showMessage("Project creation cancelled.")
                return
            color_hex = DEFAULT_PROJECT_COLOR # Use default
        else:
            # Get hex string (including alpha if needed)
            color_hex = color.name(QColor.NameFormat.HexArgb if color.alpha() != 255 else QColor.NameFormat.HexRgb)

        # Add new project data (including the new 'pinned' field)
        self.projects[clean_name] = {
            "files": [],
            "notes": "",
            "color": color_hex,
            "last_opened": None,
            "pinned": None # Default to not pinned
        }
        save_projects(self.projects)
        self.statusBar().showMessage(f"Project '{clean_name}' added.")
        self.refresh_projects() # Update display to show the new card


    def filter_projects(self, text=""):
        search_lower = text.lower().strip()
        any_visible = False
        has_projects = len(self.projects) > 0

        # Iterate through the widgets currently managed *in the layout order*
        # This ensures the visibility check happens on the current visual state
        for i in range(self.projects_layout.count()):
            widget_item = self.projects_layout.itemAt(i)
            if widget_item and (widget := widget_item.widget()):
                 # Get project name from the widget property
                name = widget.property("projectName")
                if name and name in self.projects:
                    project_data = self.projects.get(name, {})
                    project_notes = project_data.get("notes", "").lower()
                    # Match if search term is in name or notes (or if search is empty)
                    match = not search_lower or search_lower in name.lower() or search_lower in project_notes
                    widget.setVisible(match) # Show/hide widget based on match
                    if match:
                        any_visible = True
                elif name:
                     # Widget exists but project data doesn't? Hide it.
                     widget.setVisible(False)
                     print(f"Warning: Widget found for non-existent project '{name}' during filter.", file=sys.stderr)


        # Show "no results" label if filter active and nothing matches
        self.update_no_filter_results_label(has_projects and not any_visible and search_lower, search_lower)
        # Show/hide the general "no projects" label based on total count and filter state
        self.update_no_projects_label(len(self.projects))


    def update_no_filter_results_label(self, show, search_term=""):
        # Find existing label
        no_results_label = self.projects_container.findChild(QLabel, "NoResultsLabel")

        if show:
            # Create label if it doesn't exist
            if not no_results_label:
                lbl = QLabel(f"No projects match your search for:\n'{search_term}'")
                lbl.setObjectName("NoResultsLabel")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                # Use secondary text color
                text_color = COLOR_TEXT_SECONDARY_ON_CARD
                lbl.setStyleSheet(f"color: {text_color}; padding: 30px; font-style: italic;")
                # Insert at the top of the layout
                self.projects_layout.insertWidget(0, lbl)
        else:
            # Remove label if it exists and shouldn't be shown
            if no_results_label:
                no_results_label.setParent(None)
                no_results_label.deleteLater()

    def edit_project(self, name):
        if name not in self.projects:
            QMessageBox.critical(self, "Error", f"Project '{name}' not found. Cannot edit.")
            return

        original_data = self.projects[name]
        # Pass current data and dark mode status to the dialog
        dialog = EditProjectDialog(name, original_data, self.dark_mode, self)
        dialog.saveAsNewRequested.connect(self.handle_save_as_new) # Connect signal for "Save As New"

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Retrieve potentially updated data from the dialog
            new_name = dialog.project_name
            new_data = {
                "files": dialog.files, # Updated file list
                "notes": dialog.notes, # Updated notes
                "color": dialog.project_color, # Updated color
                "last_opened": original_data.get("last_opened"), # Preserve last opened time
                "pinned": original_data.get("pinned") # Preserve pinned status
            }

            name_changed = (new_name != name)

            if name_changed:
                # Handle rename: check for duplicates, update project dict, auto-launch, widget cache
                if new_name in self.projects:
                    QMessageBox.critical(self, "Error Renaming", f"Project name '{new_name}' already exists!")
                    # Optionally re-open dialog or revert name? For now, just abort.
                    return
                # Remove old entry, add new one
                del self.projects[name]
                self.projects[new_name] = new_data
                # Update auto-launch if necessary
                if name in self.auto_launch:
                    self.auto_launch[new_name] = self.auto_launch.pop(name)
                # Update widget cache key
                widget = self._project_card_widgets.pop(name, None)
                if widget:
                    widget.setProperty("projectName", new_name) # Update property
                    self._project_card_widgets[new_name] = widget
                else:
                    # This case shouldn't happen if refresh is working, but log if it does
                    print(f"Warning: Widget for '{name}' not found during rename.", file=sys.stderr)
            else:
                # Update existing project data if name hasn't changed
                self.projects[name] = new_data

            # Save changes
            save_projects(self.projects)
            if name_changed or name in self.auto_launch: # Save auto-launch only if relevant keys changed
                save_auto_launch(self.auto_launch)

            self.statusBar().showMessage(f"Project '{new_name}' updated.")

            # Refresh display
            # Always refresh fully after edit to ensure correct state and order
            self.refresh_projects()
            # This handles both rename and content update cases correctly


    def handle_save_as_new(self, new_name, new_data):
        """Handles the 'Save As New' action from the edit dialog."""
        if not new_name:
            QMessageBox.critical(self, "Error", "Cannot 'Save As New': Project name cannot be empty.")
            return
        if new_name in self.projects:
            QMessageBox.critical(self, "Error", f"Cannot 'Save As New': Project name '{new_name}' already exists.")
            return

        # Add the new project (ensure 'pinned' is reset for the new copy)
        new_data['pinned'] = None # New projects start unpinned
        self.projects[new_name] = new_data
        save_projects(self.projects)

        self.statusBar().showMessage(f"New project '{new_name}' saved from existing.")
        QMessageBox.information(self, "Project Saved As New",
                                f"Project '{new_name}' saved with {len(new_data.get('files', []))} item(s).")
        self.refresh_projects() # Update display to include the new project


    def remove_project(self, name):
        reply = QMessageBox.question(self, "Confirm Removal",
                                     f"Permanently remove project '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel) # Default to Cancel

        if reply == QMessageBox.StandardButton.Yes:
            project_existed = name in self.projects
            auto_launch_existed = name in self.auto_launch
            widget_existed = name in self._project_card_widgets

            # Remove from data structures
            if project_existed: del self.projects[name]
            if auto_launch_existed: del self.auto_launch[name]
            # Remove widget from cache (actual deletion from layout happens in refresh)
            if widget_existed:
                self._project_card_widgets.pop(name)
                # Don't manually delete here, let refresh handle it

            # Save changes if data was modified
            if project_existed: save_projects(self.projects)
            if auto_launch_existed: save_auto_launch(self.auto_launch)

            self.statusBar().showMessage(f"Project '{name}' removed.")
            self.refresh_projects() # Update display


    def open_project(self, name):
        if name not in self.projects:
            QMessageBox.critical(self, "Error", f"Project '{name}' not found. Cannot open.")
            return

        project_data = self.projects[name]
        # Get paths of selected items
        items_to_try = [
            item["path"] for item in project_data.get("files", [])
            if isinstance(item, dict) and item.get("selected", True) and item.get("path") # Check path exists
        ]

        if not items_to_try:
            QMessageBox.information(self, "Nothing to Open", f"No items checked in project '{name}'.")
            self.statusBar().showMessage(f"No selected items to open in '{name}'")
            return

        # Update last opened timestamp before attempting to open
        current_timestamp = time.time()
        self.projects[name]["last_opened"] = current_timestamp
        save_projects(self.projects) # Save immediately

        # Update the card display immediately
        if widget := self._project_card_widgets.get(name):
            self.update_project_card_content(widget, name)
        QApplication.processEvents() # Allow UI to update

        opened_any = False
        missing_files = []
        failed_to_open = []

        # Attempt to open each selected item
        for path in items_to_try:
            try:
                url = None
                lpath = path.lower()
                # Check for web links first
                if lpath.startswith(("http://", "https://", "ftp://", "mailto:")):
                    url = QUrl(path, QUrl.ParsingMode.TolerantMode) # Be tolerant of link format
                else:
                    # Assume local file/folder
                    norm_path = os.path.normpath(path)
                    if os.path.exists(norm_path):
                        # Use QUrl.fromLocalFile for proper handling of local paths
                        url = QUrl.fromLocalFile(os.path.abspath(norm_path))
                    else:
                        missing_files.append(path)
                        print(f"Missing: {path}") # Log missing file

                # Attempt to open if a valid URL was created
                if url and url.isValid():
                    print(f"Attempting to open: {url.toString()}") # Log opening attempt
                    if QDesktopServices.openUrl(url):
                        opened_any = True
                    else:
                        # Log if openUrl failed (might happen for unsupported types/permissions)
                        print(f"Warning: QDesktopServices failed to open {url.toString()}")
                        failed_to_open.append(path)
                elif url and not url.isValid():
                    # Log if URL parsing failed (unlikely for local files, maybe bad links)
                    print(f"Warning: Invalid URL generated for path '{path}'")
                    failed_to_open.append(f"{path} (Invalid URL)")

            except Exception as e:
                # Catch any unexpected errors during path processing or opening
                error_msg = f"Error trying to open:\n{path}\n\n{str(e)}"
                print(error_msg, file=sys.stderr)
                QMessageBox.warning(self, "Opening Error", error_msg)
                failed_to_open.append(f"{path} (Error: {e})")

        # Report issues after trying all files
        if missing_files:
            QMessageBox.warning(self, "Missing Items",
                                f"Checked items not found in '{name}':\n\n" + "\n".join(missing_files))
        if failed_to_open:
            QMessageBox.warning(self, "Opening Issues",
                                f"Could not open some checked items in '{name}':\n\n" + "\n".join(failed_to_open))

        # Update status bar based on outcome
        if opened_any:
            self.statusBar().showMessage(f"Opened checked items in '{name}'. Timestamp updated.")
        elif not missing_files and not failed_to_open:
             # Only show this if no other errors occurred
            self.statusBar().showMessage(f"No valid selected items found to open in '{name}'")


    def toggle_auto_launch(self, name, state):
        is_checked = bool(state)
        if name in self.projects:
            changed = self.auto_launch.get(name) != is_checked
            self.auto_launch[name] = is_checked
            if changed:
                save_auto_launch(self.auto_launch) # Save only if state changed
            status_msg = f"Auto-launch {'enabled' if is_checked else 'disabled'} for '{name}'"
            self.statusBar().showMessage(status_msg)
        else:
            # Should not happen if UI is consistent with data
            print(f"Warning: Attempted toggle auto-launch for non-existent '{name}'", file=sys.stderr)


    def export_projects(self):
        # Suggest a default directory and filename
        default_dir = os.path.join(os.path.expanduser("~"), "Documents")
        default_filename = os.path.join(default_dir, "project_opener_backup.json")
        os.makedirs(default_dir, exist_ok=True) # Ensure directory exists

        file_path, _ = QFileDialog.getSaveFileName(self, "Export Projects & Settings", default_filename,
                                                   "JSON Backup Files (*.json);;All Files (*)")
        if file_path:
            try:
                # Combine projects (including pinned status) and auto-launch settings
                export_data = {
                    "projects": self.projects,
                    "auto_launch": self.auto_launch
                    # Add settings export here if needed later:
                    # "settings": self.settings
                }
                with open(file_path, "w", encoding='utf-8') as f:
                    json.dump(export_data, f, indent=4, default=str) # Use default=str for Timestamps/QColor etc. if needed

                self.statusBar().showMessage(f"Data exported to {os.path.basename(file_path)}")
                QMessageBox.information(self, "Export Successful", f"Projects and settings exported to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export data: {str(e)}")
                print(f"Export Error: {e}", file=sys.stderr)


    def import_projects(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Import Projects & Settings", "",
                                                   "JSON Backup Files (*.json);;All Files (*)")
        if not file_path:
            return # User cancelled

        try:
            with open(file_path, "r", encoding='utf-8') as f:
                import_data = json.load(f)

            # Basic validation of imported data structure
            imported_projects = import_data.get("projects", {})
            imported_auto_launch = import_data.get("auto_launch", {})
            # imported_settings = import_data.get("settings", {}) # Prepare for settings import

            if not isinstance(imported_projects, dict) or not isinstance(imported_auto_launch, dict):
                QMessageBox.critical(self, "Import Error",
                                     "Invalid data format: 'projects' and 'auto_launch' must be dictionaries.")
                return
            if not imported_projects and not imported_auto_launch:
                 # Check if settings exist if implemented
                QMessageBox.warning(self, "Import Warning",
                                    "Selected file contains no 'projects' or 'auto_launch' data.")
                return

            # Ask user for Merge or Replace mode
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle("Import Mode")
            msg_box.setText("Choose import mode:")
            msg_box.setInformativeText(
                "<b>Merge:</b> Adds new projects, updates existing ones based on name. Keeps current projects not in the file.<br>"
                "<b>Replace:</b> Deletes all current projects and settings before importing."
            )
            merge_button = msg_box.addButton("Merge", QMessageBox.ButtonRole.YesRole)
            replace_button = msg_box.addButton("Replace", QMessageBox.ButtonRole.NoRole)
            cancel_button = msg_box.addButton(QMessageBox.StandardButton.Cancel)
            msg_box.setDefaultButton(merge_button) # Default to Merge
            msg_box.exec()

            reply = msg_box.clickedButton()
            merge_mode = False
            if reply == merge_button:
                merge_mode = True
            elif reply == replace_button:
                merge_mode = False
            else: # Cancelled
                self.statusBar().showMessage("Import cancelled.")
                return

            # --- Perform Import ---
            proj_added = 0
            proj_updated = 0
            auto_updated = 0

            if not merge_mode:
                # Clear existing data
                self.projects.clear()
                self.auto_launch.clear()
                # Clear widget cache before clearing layout in refresh
                self._project_card_widgets.clear()
                # Clear settings if importing them
                # self.settings.clear()

            # Import Projects data
            for name, data in imported_projects.items():
                if isinstance(data, dict):
                     # Validate and normalize imported project data (like in load_projects)
                    if "files" not in data or not isinstance(data.get("files"), list): data["files"] = []
                    valid_files = []
                    for item in data.get("files", []):
                         # Convert old string format or keep dict format
                        if isinstance(item, dict) and "path" in item and isinstance(item.get("selected"), bool):
                            valid_files.append(item)
                        elif isinstance(item, str):
                             valid_files.append({"path": item, "selected": True})
                    data["files"] = valid_files

                    if "notes" not in data or not isinstance(data.get("notes"), str): data["notes"] = ""
                    if "color" not in data or not QColor(data.get("color", "")).isValid(): data["color"] = DEFAULT_PROJECT_COLOR
                    if "last_opened" not in data: data["last_opened"] = None
                    if "pinned" not in data: data["pinned"] = None # Ensure pinned field exists

                    # Update counts and store data
                    if name not in self.projects: proj_added += 1
                    else: proj_updated += 1
                    self.projects[name] = data
                else:
                    # Skip invalid entries
                    print(f"Warning: Skipping invalid import data for project '{name}'.", file=sys.stderr)

            # Import Auto-Launch data
            current_auto_launch_keys = set(self.auto_launch.keys()) # Store before modification
            for name, value in imported_auto_launch.items():
                # Only import if the project exists and value is boolean
                if name in self.projects and isinstance(value, bool):
                    if self.auto_launch.get(name) != value: auto_updated += 1
                    self.auto_launch[name] = value

            # In replace mode, remove auto-launch entries for projects that were not imported
            if not merge_mode:
                # Use the current projects keys after import as the reference
                imported_project_keys = set(self.projects.keys())
                keys_to_remove_from_auto = current_auto_launch_keys - imported_project_keys
                for key in keys_to_remove_from_auto:
                     if key in self.auto_launch:
                         del self.auto_launch[key]
                 # Also ensure auto_launch only contains keys present in the newly loaded projects
                auto_launch_keys = list(self.auto_launch.keys())
                for key in auto_launch_keys:
                    if key not in imported_project_keys:
                        del self.auto_launch[key]


            # Import Settings data (if implemented)
            # if imported_settings:
            #   self.settings.update(imported_settings) # Simple update or more complex merge logic
            #   self.dark_mode = self.settings.get("dark_mode", False) # Update dark mode state
            #   self.dark_mode_checkbox.setChecked(self.dark_mode) # Update checkbox UI

            # Save all imported data
            save_projects(self.projects)
            save_auto_launch(self.auto_launch)
            # save_settings(self.settings) # If settings are imported

            # Refresh the entire UI
            self.refresh_projects()
            # Re-apply styles if settings changed (e.g., dark mode)
            # self.apply_style()

            self.statusBar().showMessage("Import complete.")
            # Show summary message
            if merge_mode:
                summary = f"Import Complete (Merged):\n- {proj_added} Project(s) Added\n- {proj_updated} Project(s) Updated\n- {auto_updated} Auto-Launch Setting(s) Updated"
            else:
                summary = f"Import Complete (Replaced):\n- {len(self.projects)} Project(s) Loaded\n- {len(self.auto_launch)} Auto-Launch Setting(s) Applied"
                # Add settings count if implemented
            QMessageBox.information(self, "Import Summary", summary)

        except json.JSONDecodeError:
            QMessageBox.critical(self, "Import Error", "Failed to read JSON file. It might be corrupted.")
            print(f"Import Error: JSONDecodeError in {file_path}", file=sys.stderr)
        except FileNotFoundError:
            QMessageBox.critical(self, "Import Error", f"File not found: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"An unexpected error occurred during import: {str(e)}")
            print(f"Import Error: {e}", file=sys.stderr)


    def auto_launch_projects(self):
        launched_count = 0
        projects_to_launch = []
        # Find projects marked for auto-launch
        for name, enabled in self.auto_launch.items():
            if enabled and name in self.projects:
                project_data = self.projects[name]
                # Check if there are actually selected items to open
                has_selected_items = any(
                    isinstance(item, dict) and item.get("selected", True) and item.get("path")
                    for item in project_data.get("files", [])
                )
                if has_selected_items:
                    projects_to_launch.append(name)

        if not projects_to_launch:
            return # Nothing to auto-launch

        print(f"Auto-launching projects: {', '.join(projects_to_launch)}")
        self.statusBar().showMessage(f"Auto-launching {len(projects_to_launch)} project(s)...")

        # Open each project sequentially
        for name in projects_to_launch:
            print(f"--> Auto-opening {name}")
            self.open_project(name)
            # Allow some processing time between opening multiple projects
            QApplication.processEvents()
            # time.sleep(0.1) # Optional small delay

        # Update status bar after completion
        if projects_to_launch:
            # Show message briefly
            QTimer.singleShot(1500, lambda: self.statusBar().showMessage(
                f"Auto-launched {len(projects_to_launch)} project(s). Ready.", 5000))


    def closeEvent(self, event):
        # Ensure all data is saved on exit
        save_settings(self.settings)
        save_projects(self.projects)
        save_auto_launch(self.auto_launch)
        print("Settings, Projects, and Auto-Launch saved on exit.")
        super().closeEvent(event)


# --- Edit Project Dialog ---
class EditProjectDialog(QDialog):
    # Signal emitted when "Save As New" is clicked
    saveAsNewRequested = pyqtSignal(str, dict) # new_name, new_data

    def __init__(self, project_name, project_data, dark_mode, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Project: {project_name}")
        self.setMinimumSize(600, 550)
        self.dark_mode = dark_mode # Store mode passed from main window
        self.original_name = project_name
        # Get main window instance to check project names on save
        self.main_window = parent

        # Store editable data locally
        self.project_name = project_name
        self.project_color = project_data.get("color", DEFAULT_PROJECT_COLOR)
        self.notes = project_data.get("notes", "")
        # Create a deep copy of files data to allow modification without affecting original until save
        self.internal_files_data = [item.copy() for item in project_data.get("files", [])]

        self.init_ui()
        self.apply_dialog_style() # Apply theme

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 15)

        # --- Enable Drag & Drop on the whole dialog ---
        self.setAcceptDrops(True)

        # Project Name Input
        name_layout = QHBoxLayout()
        name_label = QLabel("Project Name:")
        name_layout.addWidget(name_label)
        self.name_edit = QLineEdit(self.project_name)
        # Explicitly set text color for light mode if needed, but QSS should handle it
        # self.name_edit.setStyleSheet("color: #000000;") # Example if needed
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)

        # Color Selection
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Card Color:"))
        self.color_preview_label = QLabel()
        self.color_preview_label.setFixedSize(40, 20)
        self.color_preview_label.setAutoFillBackground(True) # Needed for palette background
        self.color_preview_label.setFrameStyle(QFrame.Shape.Panel | QFrame.Shadow.Sunken) # Visual indication
        self.update_color_preview() # Set initial color
        color_layout.addWidget(self.color_preview_label)
        change_color_btn = QPushButton("Change...")
        change_color_btn.clicked.connect(self.change_color)
        color_layout.addWidget(change_color_btn)
        color_layout.addStretch() # Push elements left
        layout.addLayout(color_layout)

        # Project Notes Input
        layout.addWidget(QLabel("Project Notes:"))
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlainText(self.notes) # Use plain text
        self.notes_edit.setAcceptRichText(False) # Disable rich text pasting
        self.notes_edit.setFixedHeight(80) # Fixed height for notes area
        layout.addWidget(self.notes_edit)

        # Project Items List
        layout.addWidget(QLabel("Project Items:"))
        self.files_list = FileListWidget(self) # Use custom list widget
        self.files_list.setToolTip("Drag & drop files/folders here.\nSelect item(s) and press DEL to remove.")
        self.populate_files_list() # Populate with initial items
        layout.addWidget(self.files_list, 1) # List takes expanding space

        # File Action Buttons (Add File/Folder/Link)
        file_buttons_layout = QHBoxLayout()
        file_buttons_layout.setSpacing(8)
        style = QApplication.style()
        icon_size = QSize(16, 16)

        add_file_btn = QPushButton(style.standardIcon(QStyle.StandardPixmap.SP_FileIcon), " Add File(s)")
        add_file_btn.setIconSize(icon_size)
        add_file_btn.clicked.connect(self.add_file)
        file_buttons_layout.addWidget(add_file_btn)

        add_folder_btn = QPushButton(style.standardIcon(QStyle.StandardPixmap.SP_DirIcon), " Add Folder")
        add_folder_btn.setIconSize(icon_size)
        add_folder_btn.clicked.connect(self.add_folder)
        file_buttons_layout.addWidget(add_folder_btn)

        add_link_btn = QPushButton(style.standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon), " Add Link") # Using network drive icon for link
        add_link_btn.setIconSize(icon_size)
        add_link_btn.clicked.connect(self.add_link)
        file_buttons_layout.addWidget(add_link_btn)

        file_buttons_layout.addStretch() # Push buttons left
        layout.addLayout(file_buttons_layout)

        # Dialog Buttons (Save, Save As New, Cancel)
        self.button_box = QDialogButtonBox()
        self.save_btn = self.button_box.addButton(QDialogButtonBox.StandardButton.Save)
        self.save_as_new_btn = self.button_box.addButton("Save As New...", QDialogButtonBox.ButtonRole.ActionRole) # Custom button
        self.cancel_btn = self.button_box.addButton(QDialogButtonBox.StandardButton.Cancel)

        # Connect signals
        self.button_box.accepted.connect(self.save_changes) # Connected to Save button by default role
        self.button_box.rejected.connect(self.reject) # Connected to Cancel button
        self.save_as_new_btn.clicked.connect(self.save_as_new) # Connect custom button

        layout.addWidget(self.button_box)

    # --- Drag and Drop Support ---
    def dragEnterEvent(self, event):
        # Accept drop only if it contains URLs (files/folders)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        # Process dropped URLs
        if event.mimeData().hasUrls():
            added_paths = set(item['path'] for item in self.internal_files_data) # Avoid duplicates on drop
            newly_added = False
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path and path not in added_paths: # Check if it's a local file/folder and not already added
                    self.internal_files_data.append({"path": path, "selected": True})
                    added_paths.add(path)
                    newly_added = True
            if newly_added:
                self.populate_files_list() # Refresh list if items were added
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def apply_dialog_style(self):
        # Apply the main window's stylesheet to the dialog
        self.setStyleSheet(generate_qss(self.dark_mode))

    def update_color_preview(self):
        # Update the color preview label background
        palette = self.color_preview_label.palette()
        try:
            color = QColor(self.project_color)
            if not color.isValid(): color = QColor(DEFAULT_PROJECT_COLOR) # Fallback
        except Exception:
            color = QColor(DEFAULT_PROJECT_COLOR)
        palette.setColor(QPalette.ColorRole.Window, color)
        self.color_preview_label.setPalette(palette)
        self.color_preview_label.setAutoFillBackground(True) # Ensure background is drawn

    def change_color(self):
        # Open color dialog
        try:
            current_color = QColor(self.project_color)
            if not current_color.isValid(): current_color = QColor(DEFAULT_PROJECT_COLOR)
        except Exception:
            current_color = QColor(DEFAULT_PROJECT_COLOR)

        color = QColorDialog.getColor(current_color, self, "Select New Card Color",
                                      QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            # Update stored color and preview
            self.project_color = color.name(
                QColor.NameFormat.HexArgb if color.alpha() != 255 else QColor.NameFormat.HexRgb)
            self.update_color_preview()

    # ***** START OF THE SINGLE CHANGE AREA (Part 2/2) *****
    def populate_files_list(self):
        self.files_list.clear() # Clear existing items
        # Determine light mode status from the dialog's dark_mode attribute
        is_light_mode = not self.dark_mode
        # Add items based on internal_files_data
        for file_data in self.internal_files_data:
            file_path = file_data.get("path", "")
            selected = file_data.get("selected", True)
            if not file_path: continue # Skip if path is empty

            item = QListWidgetItem()
            # Create the custom widget for the item, passing the light mode status
            widget = FileItemWidget(file_path, selected, is_light_mode, parent=self.files_list)
            item.setSizeHint(widget.sizeHint()) # Set item size hint for proper layout
            self.files_list.addItem(item)
            self.files_list.setItemWidget(item, widget) # Associate widget with item
    # ***** END OF THE SINGLE CHANGE AREA (Part 2/2) *****

    def get_files_data(self):
        """Retrieve the current state of files from the list widget."""
        # This is now handled by modifying internal_files_data directly via add/remove/drag&drop
        # We just need to update the 'selected' state based on checkboxes before saving.
        updated_files_data = []
        for i in range(self.files_list.count()):
            item = self.files_list.item(i)
            widget = self.files_list.itemWidget(item)
            if widget:
                # Find the corresponding entry in internal_files_data and update its 'selected' status
                path = widget.label.text()
                is_selected = widget.checkbox.isChecked()
                # Update the entry in internal_files_data or just return the current widget state
                # Let's return the current widget state for simplicity when saving
                updated_files_data.append({"path": path, "selected": is_selected})

        # Overwrite internal list with current UI state on save
        self.internal_files_data = updated_files_data
        return self.internal_files_data


    def add_file(self):
        # Allow selecting multiple files
        files, _ = QFileDialog.getOpenFileNames(self, "Select File(s)")
        if files:
            added_paths = set(item['path'] for item in self.internal_files_data)
            newly_added = False
            for file_path in files:
                if file_path not in added_paths:
                    self.internal_files_data.append({"path": file_path, "selected": True})
                    added_paths.add(file_path)
                    newly_added = True
            if newly_added:
                self.populate_files_list() # Refresh list


    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            added_paths = set(item['path'] for item in self.internal_files_data)
            if folder not in added_paths:
                self.internal_files_data.append({"path": folder, "selected": True})
                self.populate_files_list() # Refresh list


    def add_link(self):
        link, ok = QInputDialog.getText(self, "Add Link", "Enter URL (e.g., http://..., https://..., mailto:...):")
        if ok and link:
            clean_link = link.strip()
            if clean_link:
                added_paths = set(item['path'] for item in self.internal_files_data)
                if clean_link not in added_paths:
                    self.internal_files_data.append({"path": clean_link, "selected": True})
                    self.populate_files_list() # Refresh list


    def save_changes(self):
        """Update internal variables from UI elements and accept the dialog."""
        new_name = self.name_edit.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "Project name cannot be empty.")
            self.name_edit.setFocus()
            return # Prevent closing dialog

        # Check if name changed to one that already exists (excluding the original name)
        # Access projects dict from the parent (MainWindow)
        if self.main_window and hasattr(self.main_window, 'projects'):
            if new_name != self.original_name and new_name in self.main_window.projects:
                 QMessageBox.warning(self, "Duplicate Name", f"A project named '{new_name}' already exists.")
                 self.name_edit.setFocus()
                 return # Prevent closing dialog
        else:
            # Fallback if parent doesn't have projects dict (shouldn't happen)
            print("Warning: Cannot access main window projects for name check.", file=sys.stderr)


        self.project_name = new_name
        self.notes = self.notes_edit.toPlainText() # Get plain text notes
        # Get the final state of files data from the list/internal representation
        self.files = self.get_files_data() # Updates self.internal_files_data and returns it
        self.accept() # Close dialog with Accepted code


    def save_as_new(self):
        """Prompt for a new name and emit the saveAsNewRequested signal."""
        new_name, ok = QInputDialog.getText(self, "Save As New", "Enter new project name:")
        if ok and new_name:
            clean_new_name = new_name.strip()
            if not clean_new_name:
                QMessageBox.warning(self, "Invalid Name", "New project name cannot be empty.")
                return # Keep dialog open

            # Check if the new name already exists in the main window's projects
            if self.main_window and hasattr(self.main_window, 'projects'):
                if clean_new_name in self.main_window.projects:
                    QMessageBox.warning(self, "Duplicate Name", f"A project named '{clean_new_name}' already exists.")
                    return # Keep dialog open
            else:
                print("Warning: Cannot access main window projects for name check.", file=sys.stderr)


            # Get current data from the dialog fields
            current_notes = self.notes_edit.toPlainText()
            current_files = self.get_files_data() # Get final state from UI/internal list
            current_color = self.project_color

            # Emit signal with the new name and current data
            self.saveAsNewRequested.emit(clean_new_name, {
                "files": current_files,
                "notes": current_notes,
                "color": current_color,
                "last_opened": None, # New project hasn't been opened
                "pinned": None # New project starts unpinned
            })
            self.accept() # Close the dialog after emitting


# --- Main Execution ---
if __name__ == '__main__':
    # Enable high DPI scaling for better visuals (Qt6 handles this mostly automatically)
    # Check Qt documentation if specific scaling attributes are needed for your environment
    # QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough) # Example

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())