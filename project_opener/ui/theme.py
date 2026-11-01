"""Design tokens and the generated Qt stylesheet ("Aurora, disciplined").

The rules live in docs/DESIGN.md.  Everything visual derives from ``Tokens`` so
a theme change (dark/light/accent/density) is one call: ``apply_theme(app, ...)``.
Widgets that need colours at paint time read them from ``current()``.

Old token names are kept (bg, surface_2, text_muted, accent_soft, ...) so every
widget keeps working; new roles (pill_*, field_*, radius_card, control_h) were
added for the 3.1 design.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from project_opener import constants as C

log = logging.getLogger(__name__)

FONT_FAMILY = "Onest"
DEFAULT_ACCENT = "#0E7C5B"

# Ten flat accents, each ≥ 4.5:1 with white text (checked with tools/check_contrast.py).
ACCENTS: list[tuple[str, str]] = [
    ("#0E7C5B", "Aurora green"), ("#0F766E", "Teal"), ("#1D5FB8", "Blue"), ("#4F46A3", "Iris"),
    ("#A3285B", "Berry"), ("#B4452E", "Terracotta"), ("#8A5A00", "Amber"), ("#3B6A1F", "Olive"),
    ("#5C5F66", "Graphite"), ("#1A201D", "Ink"),
]


@dataclass(frozen=True)
class Tokens:
    name: str
    dark: bool
    # ground and surfaces
    bg: str
    bg_alt: str
    surface: str
    surface_2: str
    surface_3: str
    border: str
    border_strong: str
    # text
    text: str
    text_muted: str
    text_faint: str
    # the one accent
    accent: str
    accent_hover: str
    accent_soft: str
    accent_fg: str
    # status (text / icon colours, all ≥ 4.5:1 on surface)
    success: str
    warning: str
    danger: str
    info: str
    # status pills: pale tint + dark ink of the same hue
    pill_ok_bg: str
    pill_ok_ink: str
    pill_warn_bg: str
    pill_warn_ink: str
    pill_bad_bg: str
    pill_bad_ink: str
    pill_info_bg: str
    pill_info_ink: str
    pill_neutral_bg: str
    pill_neutral_ink: str
    # flat colour fields (the aurora)
    field_mint: str
    field_sky: str
    field_blush: str
    field_ink: str
    shadow: str
    # shape
    radius: int = 16          # cards
    radius_sm: int = 10       # inputs, menus
    control_h: int = 34       # buttons / inputs height; pills use control_h / 2
    pad: int = 20             # card padding
    gap: int = 16
    font_size: int = 10       # pt (13.3 px)


def _mix(a: str, b: str, t: float) -> str:
    ca, cb = QColor(a), QColor(b)
    r = ca.red() + (cb.red() - ca.red()) * t
    g = ca.green() + (cb.green() - ca.green()) * t
    bl = ca.blue() + (cb.blue() - ca.blue()) * t
    return QColor(int(r), int(g), int(bl)).name()


def alpha(hex_color: str, a: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{a:.3f})"


def _lin(v: int) -> float:
    s = v / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    """Relative luminance (WCAG)."""
    c = QColor(hex_color)
    return 0.2126 * _lin(c.red()) + 0.7152 * _lin(c.green()) + 0.0722 * _lin(c.blue())


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def readable_on(hex_color: str) -> str:
    """White or ink, whichever reads better on the colour."""
    return "#FFFFFF" if contrast(hex_color, "#FFFFFF") >= contrast(hex_color, "#141A17") else "#141A17"


def tint(hex_color: str, amount: float, dark: bool) -> str:
    """A pale (light theme) or deep (dark theme) tint of a colour for identity fills."""
    return _mix(hex_color, "#0F1211" if dark else "#FFFFFF", 1 - amount)


def build_tokens(dark: bool, accent: str = DEFAULT_ACCENT, density: str = "comfortable") -> Tokens:
    accent = accent if QColor(accent).isValid() else DEFAULT_ACCENT
    pad = 20 if density == "comfortable" else 14
    if dark:
        acc = _mix(accent, "#FFFFFF", 0.35) if contrast(accent, "#171B19") < 4.5 else accent
        return Tokens(
            name="dark", dark=True,
            bg="#0F1211", bg_alt="#0F1211", surface="#171B19", surface_2="#202623", surface_3="#2A312D",
            border="#262D29", border_strong="#3A443E",
            text="#ECF0ED", text_muted="#A8B3AD", text_faint="#8A958E",
            accent=acc, accent_hover=_mix(acc, "#FFFFFF", 0.12), accent_soft=_mix(acc, "#171B19", 0.78),
            accent_fg=readable_on(acc),
            success="#3FC07A", warning="#F5B73B", danger="#F07070", info="#6FB1FF",
            pill_ok_bg="#172A1D", pill_ok_ink="#3FC07A", pill_warn_bg="#2E2410", pill_warn_ink="#F5B73B",
            pill_bad_bg="#2C1A1A", pill_bad_ink="#F07070", pill_info_bg="#14243A", pill_info_ink="#6FB1FF",
            pill_neutral_bg="#202623", pill_neutral_ink="#A8B3AD",
            field_mint="#132A21", field_sky="#13212E", field_blush="#2C1C20", field_ink="#ECF0ED",
            shadow="rgba(0,0,0,0.45)", pad=pad,
        )
    return Tokens(
        name="light", dark=False,
        bg="#F5F8F6", bg_alt="#F5F8F6", surface="#FFFFFF", surface_2="#EEF3F0", surface_3="#E4EBE7",
        border="#E3E9E5", border_strong="#C9D3CD",
        text="#141A17", text_muted="#5B6660", text_faint="#66706A",
        accent=accent, accent_hover=_mix(accent, "#000000", 0.14), accent_soft=_mix(accent, "#FFFFFF", 0.84),
        accent_fg=readable_on(accent),
        success="#1F7A4D", warning="#92400E", danger="#B42318", info="#175CD3",
        pill_ok_bg="#DCFAE5", pill_ok_ink="#04250E", pill_warn_bg="#FFF4D6", pill_warn_ink="#7A3E00",
        pill_bad_bg="#FEE4E2", pill_bad_ink="#7A1C14", pill_info_bg="#E0ECFF", pill_info_ink="#0B3A8C",
        pill_neutral_bg="#EEF3F0", pill_neutral_ink="#3A443E",
        field_mint="#DDF3EA", field_sky="#DCEBF7", field_blush="#FCE4E6", field_ink="#141A17",
        shadow="rgba(16,24,20,0.12)", pad=pad,
    )


_current: Tokens = build_tokens(False)
_fonts_loaded = False


def current() -> Tokens:
    return _current


def pill_colors(t: Tokens, level: str) -> tuple[str, str]:
    """(background, ink) for a status pill: ok | warn | bad | info | neutral."""
    return {
        "ok": (t.pill_ok_bg, t.pill_ok_ink), "success": (t.pill_ok_bg, t.pill_ok_ink),
        "warn": (t.pill_warn_bg, t.pill_warn_ink), "warning": (t.pill_warn_bg, t.pill_warn_ink),
        "bad": (t.pill_bad_bg, t.pill_bad_ink), "danger": (t.pill_bad_bg, t.pill_bad_ink), "error": (t.pill_bad_bg, t.pill_bad_ink),
        "info": (t.pill_info_bg, t.pill_info_ink),
    }.get(level, (t.pill_neutral_bg, t.pill_neutral_ink))


# ------------------------------------------------------------------- fonts
def load_fonts() -> None:
    """Register the bundled Onest variable font once per process."""
    global _fonts_loaded
    if _fonts_loaded:
        return
    _fonts_loaded = True
    folder = C.resource_path("fonts")
    if not folder.exists():
        return
    for f in sorted(folder.glob("*.ttf")):
        fid = QFontDatabase.addApplicationFont(str(f))
        if fid < 0:
            log.warning("font not loaded: %s", f.name)


def preferred_font() -> str:
    load_fonts()
    families = set(QFontDatabase.families())
    for name in (FONT_FAMILY, "Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", "Arial"):
        if name in families:
            return name
    return QApplication.font().family()


def display_font() -> str:
    """One family in the app (Operate mode); kept for callers."""
    return preferred_font()


def ui_font(size_pt: float | None = None, weight: int = 400, tabular: bool = False) -> QFont:
    """A QFont in the UI family with optional tabular figures (for numbers that line up)."""
    f = QFont(preferred_font(), int(size_pt or _current.font_size))
    f.setWeight(QFont.Weight(weight))
    if tabular:
        try:
            f.setFeature(QFont.Tag("tnum"), 1)
        except Exception:  # noqa: BLE001 - older Qt
            pass
    return f


# -------------------------------------------------------------------- qss
def build_qss(t: Tokens) -> str:
    font = preferred_font()
    fs = t.font_size
    pill = t.control_h // 2
    return f"""
    * {{ outline: none; }}
    QWidget {{
        background-color: {t.bg};
        color: {t.text};
        font-family: "{font}";
        font-size: {fs}pt;
        selection-background-color: {t.accent_soft};
        selection-color: {t.text};
    }}
    QMainWindow, QDialog {{ background-color: {t.bg}; }}
    QToolTip {{
        background-color: {t.text}; color: {t.bg}; border: none;
        padding: 6px 9px; border-radius: 8px;
    }}
    QLabel {{ background: transparent; }}
    QLabel#h1 {{ font-size: {fs + 8}pt; font-weight: 600; letter-spacing: -0.3px; }}
    QLabel#h2 {{ font-size: {fs + 4}pt; font-weight: 600; }}
    QLabel#h3 {{ font-size: {fs + 1}pt; font-weight: 600; }}
    QLabel#section {{ font-size: {fs + 2}pt; font-weight: 600; }}
    QLabel#kpi {{ font-size: {fs + 8}pt; font-weight: 400; }}
    QLabel#muted {{ color: {t.text_muted}; }}
    QLabel#faint {{ color: {t.text_faint}; font-size: {fs - 1}pt; }}
    QLabel#eyebrow {{ color: {t.text_muted}; font-size: {fs - 1}pt; font-weight: 500; }}
    QLabel#kicker {{ color: {t.text_muted}; font-size: {fs - 1}pt; font-weight: 500; }}

    /* ---------- surfaces ---------- */
    QFrame#card, QFrame#panel {{
        background-color: {t.surface}; border: 1px solid {t.border}; border-radius: {t.radius}px;
    }}
    QFrame#panel2 {{ background-color: {t.surface_2}; border: none; border-radius: {t.radius_sm}px; }}
    QFrame#sidebar {{ background-color: {t.bg_alt}; border: none; }}
    QFrame#hline {{ background-color: {t.border}; max-height: 1px; min-height: 1px; border: none; }}
    QFrame#banner {{ background-color: {t.pill_info_bg}; border: none; border-radius: {t.radius_sm}px; }}
    QFrame#banner_warn {{ background-color: {t.pill_warn_bg}; border: none; border-radius: {t.radius_sm}px; }}
    QFrame#banner_danger {{ background-color: {t.pill_bad_bg}; border: none; border-radius: {t.radius_sm}px; }}
    QFrame#field_mint {{ background-color: {t.field_mint}; border: none; border-radius: {t.radius}px; }}
    QFrame#field_sky {{ background-color: {t.field_sky}; border: none; border-radius: {t.radius}px; }}
    QFrame#field_blush {{ background-color: {t.field_blush}; border: none; border-radius: {t.radius}px; }}

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
        background-color: {t.surface}; border: 1px solid {t.border_strong}; border-radius: {t.radius_sm}px;
        padding: 7px 11px; color: {t.text}; selection-background-color: {t.accent_soft};
    }}
    QLineEdit, QSpinBox, QComboBox {{ min-height: {t.control_h - 16}px; }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 2px solid {t.accent}; padding: 6px 10px; }}
    QLineEdit:disabled, QTextEdit:disabled {{ color: {t.text_faint}; background-color: {t.surface_2}; }}
    QLineEdit#search {{ padding-left: 34px; border-radius: {pill}px; }}
    QLineEdit#search:focus {{ padding-left: 33px; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox::down-arrow {{ image: none; }}
    QComboBox QAbstractItemView {{
        background-color: {t.surface}; border: 1px solid {t.border}; border-radius: {t.radius_sm}px;
        selection-background-color: {t.surface_2}; selection-color: {t.text}; padding: 4px; outline: 0;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
    QCheckBox {{ spacing: 8px; background: transparent; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {t.border_strong}; border-radius: 5px; background: {t.surface}; }}
    QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}
    QRadioButton {{ spacing: 8px; background: transparent; }}
    QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {t.border_strong}; border-radius: 7px; background: {t.surface}; }}
    QRadioButton::indicator:checked {{ background: {t.accent}; border: 3px solid {t.surface}; }}

    /* ---------- buttons (pills) ---------- */
    QPushButton {{
        background-color: {t.surface}; border: 1px solid {t.border_strong}; border-radius: {pill}px;
        padding: 0 16px; min-height: {t.control_h - 2}px; max-height: {t.control_h - 2}px; color: {t.text}; font-weight: 500;
    }}
    QPushButton:hover {{ background-color: {t.surface_2}; }}
    QPushButton:pressed {{ background-color: {t.surface_3}; }}
    QPushButton:focus {{ border: 2px solid {t.accent}; padding: 0 15px; }}
    QPushButton:disabled {{ color: {t.text_faint}; background-color: {t.surface_2}; border-color: {t.border}; }}
    QPushButton#primary {{ background-color: {t.accent}; color: {t.accent_fg}; border: 1px solid {t.accent}; font-weight: 600; }}
    QPushButton#primary:hover {{ background-color: {t.accent_hover}; border-color: {t.accent_hover}; }}
    QPushButton#primary:focus {{ border: 2px solid {t.text}; }}
    QPushButton#primary:disabled {{ background-color: {t.surface_3}; color: {t.text_faint}; border-color: {t.surface_3}; }}
    QPushButton#danger {{ background-color: {t.surface}; color: {t.danger}; border: 1px solid {t.border_strong}; }}
    QPushButton#danger:hover {{ background-color: {t.pill_bad_bg}; border-color: {t.pill_bad_bg}; }}
    QPushButton#ghost {{ background: transparent; border: 1px solid transparent; color: {t.text_muted}; }}
    QPushButton#ghost:hover {{ background-color: {t.surface_2}; color: {t.text}; }}
    QPushButton#icon {{ background: transparent; border: 1px solid transparent; padding: 0; min-width: 30px; min-height: 30px; max-height: 30px; border-radius: 15px; }}
    QPushButton#icon:hover {{ background-color: {t.surface_2}; }}
    QPushButton#icon:checked {{ background-color: {t.accent_soft}; }}
    QPushButton#chip {{ background-color: {t.surface}; border: 1px solid {t.border_strong}; border-radius: 13px; padding: 0 11px; min-height: 24px; max-height: 24px; font-weight: 500; color: {t.text_muted}; }}
    QPushButton#chip:hover {{ color: {t.text}; background-color: {t.surface_2}; }}
    QPushButton#chip:checked {{ background-color: {t.accent_soft}; border-color: {t.accent_soft}; color: {t.text}; }}
    QPushButton#nav {{
        background: transparent; border: 1px solid transparent; border-radius: {pill}px; text-align: left;
        padding: 0 12px; min-height: {t.control_h}px; max-height: {t.control_h}px; color: {t.text_muted}; font-weight: 500;
    }}
    QPushButton#nav:hover {{ background-color: {t.surface_2}; color: {t.text}; }}
    QPushButton#nav:checked {{ background-color: {t.surface_2}; color: {t.text}; font-weight: 600; }}
    QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 5px; }}
    QToolButton:hover {{ background-color: {t.surface_2}; }}
    QToolButton::menu-indicator {{ image: none; }}

    /* ---------- menus (float: shadow allowed) ---------- */
    QMenu {{
        background-color: {t.surface}; border: 1px solid {t.border}; border-radius: {t.radius_sm}px; padding: 6px;
    }}
    QMenu::item {{ padding: 7px 28px 7px 12px; border-radius: 7px; }}
    QMenu::item:selected {{ background-color: {t.surface_2}; }}
    QMenu::separator {{ height: 1px; background: {t.border}; margin: 6px 8px; }}
    QMenu::icon {{ padding-left: 8px; }}

    /* ---------- lists / tables ---------- */
    QListWidget, QListView, QTreeView, QTableView, QTableWidget {{
        background-color: {t.surface}; border: 1px solid {t.border}; border-radius: {t.radius_sm}px; padding: 4px;
        alternate-background-color: {t.surface};
    }}
    QListWidget::item, QListView::item {{ padding: 6px 8px; border-radius: 7px; }}
    QListWidget::item:selected, QListView::item:selected {{ background-color: {t.surface_2}; color: {t.text}; }}
    QListWidget::item:hover, QListView::item:hover {{ background-color: {t.surface_2}; }}
    QHeaderView::section {{
        background-color: {t.surface}; color: {t.text_muted}; padding: 6px 8px; border: none; border-bottom: 1px solid {t.border}; font-weight: 400; font-size: {fs - 1}pt;
    }}
    QTableView::item {{ padding: 4px 8px; border-bottom: 1px solid {t.border}; }}
    QTableView::item:selected {{ background-color: {t.surface_2}; color: {t.text}; }}

    /* ---------- misc ---------- */
    QProgressBar {{ background-color: {t.surface_2}; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
    QProgressBar::chunk {{ background-color: {t.accent}; border-radius: 4px; }}
    QTabWidget::pane {{ border: none; border-top: 1px solid {t.border}; }}
    QTabBar::tab {{ background: transparent; padding: 8px 14px; color: {t.text_muted}; border-bottom: 2px solid transparent; font-weight: 500; }}
    QTabBar::tab:selected {{ color: {t.text}; border-bottom: 2px solid {t.text}; }}
    QTabBar::tab:hover {{ color: {t.text}; }}
    QSplitter::handle {{ background: {t.border}; }}
    QMessageBox {{ background-color: {t.surface}; }}
    QMessageBox QLabel {{ color: {t.text}; }}
    QGroupBox {{ border: 1px solid {t.border}; border-radius: {t.radius_sm}px; margin-top: 12px; padding: 12px 8px 8px 8px; font-weight: 600; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {t.text_muted}; }}
    """


def apply_theme(app: QApplication, dark: bool, accent: str, density: str = "comfortable") -> Tokens:
    global _current
    load_fonts()
    _current = build_tokens(dark, accent, density)
    t = _current
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(t.bg))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(t.text))
    pal.setColor(QPalette.ColorRole.Base, QColor(t.surface))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(t.surface_2))
    pal.setColor(QPalette.ColorRole.Text, QColor(t.text))
    pal.setColor(QPalette.ColorRole.Button, QColor(t.surface))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(t.text))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(t.accent_soft))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(t.text))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(t.text))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(t.bg))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(t.text_faint))
    app.setPalette(pal)
    app.setFont(ui_font(t.font_size))
    app.setStyleSheet(build_qss(t))
    return t


def with_accent(t: Tokens, accent: str) -> Tokens:
    return replace(t, accent=accent)
