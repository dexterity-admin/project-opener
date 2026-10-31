"""Design tokens and the generated Qt stylesheet.

Everything visual derives from a small ``Tokens`` set so a theme change
(dark/light/accent/density) is one function call: ``apply_theme(app, settings)``.
Widgets that need colours at paint time read them from ``current()``.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Tokens:
    name: str
    dark: bool
    bg: str
    bg_alt: str
    surface: str
    surface_2: str
    surface_3: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_faint: str
    accent: str
    accent_hover: str
    accent_soft: str
    accent_fg: str
    success: str
    warning: str
    danger: str
    info: str
    shadow: str
    radius: int = 12
    radius_sm: int = 8
    pad: int = 12
    font_size: int = 10


def _mix(a: str, b: str, t: float) -> str:
    ca, cb = QColor(a), QColor(b)
    r = ca.red() + (cb.red() - ca.red()) * t
    g = ca.green() + (cb.green() - ca.green()) * t
    bl = ca.blue() + (cb.blue() - ca.blue()) * t
    return QColor(int(r), int(g), int(bl)).name()


def alpha(hex_color: str, a: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{a:.3f})"


def luminance(hex_color: str) -> float:
    c = QColor(hex_color)
    return (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255


def readable_on(hex_color: str) -> str:
    return "#0B1020" if luminance(hex_color) > 0.6 else "#FFFFFF"


def build_tokens(dark: bool, accent: str = "#4F7DFF", density: str = "comfortable") -> Tokens:
    accent = accent if QColor(accent).isValid() else "#4F7DFF"
    pad = 12 if density == "comfortable" else 8
    if dark:
        return Tokens(
            name="dark", dark=True,
            bg="#0D111C", bg_alt="#0A0E17", surface="#151B29", surface_2="#1C2334", surface_3="#242C40",
            border="#273047", border_strong="#34405C", text="#E8ECF5", text_muted="#9AA4BA", text_faint="#5F6A84",
            accent=accent, accent_hover=_mix(accent, "#FFFFFF", 0.14), accent_soft=alpha(accent, 0.16),
            accent_fg=readable_on(accent), success="#34D399", warning="#FBBF24", danger="#F87171", info="#38BDF8",
            shadow="rgba(0,0,0,0.55)", pad=pad,
        )
    return Tokens(
        name="light", dark=False,
        bg="#F3F5FA", bg_alt="#E9EDF5", surface="#FFFFFF", surface_2="#F4F6FB", surface_3="#E8ECF4",
        border="#DCE2EE", border_strong="#C3CCDD", text="#141A2A", text_muted="#5B6680", text_faint="#9AA3B8",
        accent=accent, accent_hover=_mix(accent, "#000000", 0.12), accent_soft=alpha(accent, 0.14),
        accent_fg=readable_on(accent), success="#16A34A", warning="#D97706", danger="#DC2626", info="#0284C7",
        shadow="rgba(16,24,40,0.18)", pad=pad,
    )


_current: Tokens = build_tokens(True)


def current() -> Tokens:
    return _current


def preferred_font() -> str:
    families = set(QFontDatabase.families())
    for name in ("Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", "Helvetica Neue", "Arial"):
        if name in families:
            return name
    return QApplication.font().family()


def display_font() -> str:
    families = set(QFontDatabase.families())
    for name in ("Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI", "Inter"):
        if name in families:
            return name
    return preferred_font()


def build_qss(t: Tokens) -> str:
    font = preferred_font()
    fs = t.font_size
    return f"""
    * {{ outline: none; }}
    QWidget {{
        background-color: {t.bg};
        color: {t.text};
        font-family: "{font}";
        font-size: {fs}pt;
        selection-background-color: {t.accent};
        selection-color: {t.accent_fg};
    }}
    QMainWindow, QDialog {{ background-color: {t.bg}; }}
    QToolTip {{
        background-color: {t.surface_3}; color: {t.text}; border: 1px solid {t.border_strong};
        padding: 6px 8px; border-radius: 6px;
    }}
    QLabel {{ background: transparent; }}
    QLabel#h1 {{ font-size: {fs + 12}pt; font-weight: 700; font-family: "{display_font()}"; }}
    QLabel#h2 {{ font-size: {fs + 5}pt; font-weight: 700; }}
    QLabel#h3 {{ font-size: {fs + 2}pt; font-weight: 600; }}
    QLabel#muted {{ color: {t.text_muted}; }}
    QLabel#faint {{ color: {t.text_faint}; font-size: {fs - 1}pt; }}
    QLabel#eyebrow {{ color: {t.text_muted}; font-size: {fs - 1}pt; font-weight: 600; letter-spacing: 1px; }}
    QLabel#kicker {{ color: {t.accent}; font-size: {fs - 1}pt; font-weight: 700; letter-spacing: 1px; }}

    /* ---------- surfaces ---------- */
    QFrame#card, QFrame#panel {{
        background-color: {t.surface}; border: 1px solid {t.border}; border-radius: {t.radius}px;
    }}
    QFrame#panel2 {{ background-color: {t.surface_2}; border: 1px solid {t.border}; border-radius: {t.radius}px; }}
    QFrame#sidebar {{ background-color: {t.bg_alt}; border-right: 1px solid {t.border}; }}
    QFrame#header {{ background-color: {t.bg}; border-bottom: 1px solid {t.border}; }}
    QFrame#hline {{ background-color: {t.border}; max-height: 1px; min-height: 1px; border: none; }}
    QFrame#banner {{ background-color: {t.accent_soft}; border: 1px solid {alpha(t.accent, 0.35)}; border-radius: {t.radius_sm}px; }}
    QFrame#banner_warn {{ background-color: {alpha(t.warning, 0.14)}; border: 1px solid {alpha(t.warning, 0.4)}; border-radius: {t.radius_sm}px; }}
    QFrame#banner_danger {{ background-color: {alpha(t.danger, 0.14)}; border: 1px solid {alpha(t.danger, 0.4)}; border-radius: {t.radius_sm}px; }}

    /* ---------- scroll areas ---------- */
    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QAbstractScrollArea {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t.border_strong}; border-radius: 4px; min-height: 36px; }}
    QScrollBar::handle:vertical:hover {{ background: {t.text_faint}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {t.border_strong}; border-radius: 4px; min-width: 36px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal, QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; width: 0; }}

    /* ---------- inputs ---------- */
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
        background-color: {t.surface_2}; border: 1px solid {t.border}; border-radius: {t.radius_sm}px;
        padding: 7px 10px; color: {t.text};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {t.accent}; }}
    QLineEdit:disabled, QTextEdit:disabled {{ color: {t.text_faint}; }}
    QLineEdit#search {{ padding-left: 32px; background-color: {t.surface}; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox::down-arrow {{ image: none; }}
    QComboBox QAbstractItemView {{
        background-color: {t.surface_2}; border: 1px solid {t.border_strong}; border-radius: 8px;
        selection-background-color: {t.accent_soft}; selection-color: {t.text}; padding: 4px; outline: 0;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
    QCheckBox {{ spacing: 8px; background: transparent; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {t.border_strong}; border-radius: 4px; background: {t.surface_2}; }}
    QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}
    QRadioButton {{ spacing: 8px; background: transparent; }}
    QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {t.border_strong}; border-radius: 7px; background: {t.surface_2}; }}
    QRadioButton::indicator:checked {{ background: {t.accent}; border: 3px solid {t.surface_2}; }}

    /* ---------- buttons ---------- */
    QPushButton {{
        background-color: {t.surface_2}; border: 1px solid {t.border}; border-radius: {t.radius_sm}px;
        padding: 7px 14px; color: {t.text}; font-weight: 600;
    }}
    QPushButton:hover {{ background-color: {t.surface_3}; border-color: {t.border_strong}; }}
    QPushButton:pressed {{ background-color: {t.surface}; }}
    QPushButton:disabled {{ color: {t.text_faint}; background-color: {t.surface}; }}
    QPushButton#primary {{ background-color: {t.accent}; color: {t.accent_fg}; border: 1px solid {t.accent}; }}
    QPushButton#primary:hover {{ background-color: {t.accent_hover}; border-color: {t.accent_hover}; }}
    QPushButton#primary:disabled {{ background-color: {alpha(t.accent, 0.4)}; border-color: transparent; }}
    QPushButton#danger {{ background-color: {alpha(t.danger, 0.14)}; color: {t.danger}; border: 1px solid {alpha(t.danger, 0.4)}; }}
    QPushButton#danger:hover {{ background-color: {alpha(t.danger, 0.25)}; }}
    QPushButton#ghost {{ background: transparent; border: 1px solid transparent; color: {t.text_muted}; }}
    QPushButton#ghost:hover {{ background-color: {t.surface_2}; color: {t.text}; }}
    QPushButton#icon {{ background: transparent; border: 1px solid transparent; padding: 6px; min-width: 18px; }}
    QPushButton#icon:hover {{ background-color: {t.surface_3}; }}
    QPushButton#icon:checked {{ background-color: {t.accent_soft}; }}
    QPushButton#chip {{ background-color: {t.surface_2}; border: 1px solid {t.border}; border-radius: 12px; padding: 3px 10px; font-weight: 500; color: {t.text_muted}; }}
    QPushButton#chip:hover {{ border-color: {t.border_strong}; color: {t.text}; }}
    QPushButton#chip:checked {{ background-color: {t.accent_soft}; border-color: {t.accent}; color: {t.text}; }}
    QPushButton#nav {{
        background: transparent; border: 1px solid transparent; border-radius: 10px; text-align: left;
        padding: 9px 12px; color: {t.text_muted}; font-weight: 600;
    }}
    QPushButton#nav:hover {{ background-color: {t.surface_2}; color: {t.text}; }}
    QPushButton#nav:checked {{ background-color: {t.accent_soft}; color: {t.text}; }}
    QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 5px; }}
    QToolButton:hover {{ background-color: {t.surface_3}; }}
    QToolButton::menu-indicator {{ image: none; }}

    /* ---------- menus ---------- */
    QMenu {{
        background-color: {t.surface_2}; border: 1px solid {t.border_strong}; border-radius: 10px; padding: 6px;
    }}
    QMenu::item {{ padding: 7px 28px 7px 12px; border-radius: 6px; }}
    QMenu::item:selected {{ background-color: {t.accent_soft}; }}
    QMenu::separator {{ height: 1px; background: {t.border}; margin: 6px 8px; }}
    QMenu::icon {{ padding-left: 8px; }}

    /* ---------- lists / tables ---------- */
    QListWidget, QListView, QTreeView, QTableView, QTableWidget {{
        background-color: {t.surface}; border: 1px solid {t.border}; border-radius: {t.radius_sm}px; padding: 4px;
        alternate-background-color: {t.surface_2};
    }}
    QListWidget::item, QListView::item {{ padding: 6px 8px; border-radius: 6px; }}
    QListWidget::item:selected, QListView::item:selected {{ background-color: {t.accent_soft}; color: {t.text}; }}
    QListWidget::item:hover, QListView::item:hover {{ background-color: {t.surface_2}; }}
    QHeaderView::section {{
        background-color: {t.surface_2}; color: {t.text_muted}; padding: 6px 8px; border: none; border-bottom: 1px solid {t.border}; font-weight: 600;
    }}
    QTableView::item {{ padding: 4px 8px; }}
    QTableView::item:selected {{ background-color: {t.accent_soft}; color: {t.text}; }}

    /* ---------- misc ---------- */
    QProgressBar {{ background-color: {t.surface_2}; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
    QProgressBar::chunk {{ background-color: {t.accent}; border-radius: 4px; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{ background: transparent; padding: 8px 14px; color: {t.text_muted}; border-bottom: 2px solid transparent; font-weight: 600; }}
    QTabBar::tab:selected {{ color: {t.text}; border-bottom: 2px solid {t.accent}; }}
    QSplitter::handle {{ background: {t.border}; }}
    QStatusBar {{ background-color: {t.bg_alt}; border-top: 1px solid {t.border}; color: {t.text_muted}; }}
    QMessageBox {{ background-color: {t.surface}; }}
    QMessageBox QLabel {{ color: {t.text}; }}
    QGroupBox {{ border: 1px solid {t.border}; border-radius: {t.radius_sm}px; margin-top: 12px; padding: 12px 8px 8px 8px; font-weight: 600; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {t.text_muted}; }}
    """


def apply_theme(app: QApplication, dark: bool, accent: str, density: str = "comfortable") -> Tokens:
    global _current
    _current = build_tokens(dark, accent, density)
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(_current.bg))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_current.text))
    pal.setColor(QPalette.ColorRole.Base, QColor(_current.surface))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_current.surface_2))
    pal.setColor(QPalette.ColorRole.Text, QColor(_current.text))
    pal.setColor(QPalette.ColorRole.Button, QColor(_current.surface_2))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_current.text))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_current.accent))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(_current.accent_fg))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(_current.surface_3))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(_current.text))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_current.text_faint))
    app.setPalette(pal)
    f = QFont(preferred_font(), _current.font_size)
    app.setFont(f)
    app.setStyleSheet(build_qss(_current))
    return _current


def with_accent(t: Tokens, accent: str) -> Tokens:
    return replace(t, accent=accent)
