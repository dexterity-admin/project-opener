"""Design tokens and the generated Qt stylesheet (4.0 "Drafted Glass", the Dexterity brand).

The rules live in docs/DESIGN.md.  Everything visual derives from ``Tokens`` so
a theme change (dark/light/density) is one call: ``apply_theme(app, ...)``.
Widgets that need colours at paint time read them from ``current()``.

Old token names are kept (bg, surface_2, text_muted, accent_soft, ...) so every
widget keeps working.  4.0 adds the brand roles: ``teal`` (graphics, rules, progress),
``teal_deep``, ``action`` (amber: the one thing to press per screen), ``mist`` and ``grid``.
The colours are the brand's and fixed: the ``accent`` argument is accepted for old callers
and ignored (the 3.x accent picker is retired).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from project_opener import constants as C

log = logging.getLogger(__name__)

FONT_FAMILY = "Instrument Sans"         # body, nav, rows (brand body face)
DISPLAY_FAMILY = "Archivo"              # page titles, the hero, stat numerals (light weights)
MONO_FAMILY = "JetBrains Mono"          # section labels, annotations, counts
NOTE_FAMILY = "Cormorant Garamond"      # a person's own note (italic); never UI text
DEFAULT_ACCENT = "#1C7680"              # brand teal-ink: text, links, fills that carry white text

# The brand fixes the colour; kept as a list for old callers and tools/check_contrast.py.
ACCENTS: list[tuple[str, str]] = [(DEFAULT_ACCENT, "Dexterity teal")]

# Brand palette (the office brand kit, Dexterity-Brand\tokens\dexterity.css, --dx-*).
TEAL = "#2A8C98"
TEAL_DEEP = "#1E6066"
INK = "#132B2E"
AMBER = "#F7AF44"
AMBER_INK = "#9A5B00"


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
    # 4.0 brand roles (docs/DESIGN.md "Colour")
    teal: str                 # graphics: rules, progress, ticks, the line of flow (never body text)
    teal_deep: str
    action: str               # amber: the one thing to press per screen
    action_hover: str
    action_fg: str            # ink on amber
    action_ink: str           # amber as text
    mist: str                 # the one ground glow
    grid: str                 # isometric hairlines, #AARRGGBB
    # shape (drawn, not bubbly)
    radius: int = 8           # cards
    radius_sm: int = 6        # inputs, menus
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
    del accent                       # the brand fixes the colour (docs/DESIGN.md "Colour")
    pad = 18 if density == "comfortable" else 12
    if dark:
        # Ink-teal, not navy and not neutral grey.  Hairlines are white at 11 % / 20 %, flattened onto
        # the surface so QSS (which has no alpha blending over the ground) draws the same line.
        surface = "#152B2F"
        acc = "#4FB3BE"
        return Tokens(
            name="dark", dark=True,
            bg="#0F2124", bg_alt="#0F2124", surface=surface, surface_2="#1C363A", surface_3="#24434A",
            border=_mix(surface, "#FFFFFF", 0.11), border_strong=_mix(surface, "#FFFFFF", 0.20),
            text="#EAF4F5", text_muted="#B5C9CB", text_faint="#8FA7AA",
            accent=acc, accent_hover=_mix(acc, "#FFFFFF", 0.12), accent_soft=_mix(acc, surface, 0.78),
            accent_fg="#0F2124",
            success="#3FC07A", warning="#F5B73B", danger="#F07070", info="#6FB1FF",
            pill_ok_bg="#172A1D", pill_ok_ink="#3FC07A", pill_warn_bg="#2E2410", pill_warn_ink="#F5B73B",
            pill_bad_bg="#2C1A1A", pill_bad_ink="#F07070", pill_info_bg="#14243A", pill_info_ink="#6FB1FF",
            pill_neutral_bg="#1C363A", pill_neutral_ink="#B5C9CB",
            field_mint="#16343A", field_sky="#13212E", field_blush="#2C1C20", field_ink="#EAF4F5",
            shadow="rgba(0,0,0,0.45)",
            teal="#3FA3AF", teal_deep=TEAL_DEEP, action=AMBER, action_hover=_mix(AMBER, "#FFFFFF", 0.12),
            action_fg=INK, action_ink=AMBER, mist="#1C363A", grid="#0AFFFFFF",
            pad=pad,
        )
    surface = "#FFFFFF"
    return Tokens(
        name="light", dark=False,
        bg="#F6FAFA", bg_alt="#F6FAFA", surface=surface, surface_2="#E8F2F3", surface_3="#D6E8EA",
        # brand hairlines (deep teal at 16 % / 30 %) flattened onto white
        border=_mix(surface, TEAL_DEEP, 0.16), border_strong=_mix(surface, TEAL_DEEP, 0.30),
        text=INK, text_muted="#4C6366", text_faint="#5A7073",
        accent=DEFAULT_ACCENT, accent_hover=_mix(DEFAULT_ACCENT, "#000000", 0.14),
        accent_soft=_mix(DEFAULT_ACCENT, "#FFFFFF", 0.86), accent_fg="#FFFFFF",
        success="#1F7A4D", warning="#92400E", danger="#B42318", info="#175CD3",
        pill_ok_bg="#DCFAE5", pill_ok_ink="#04250E", pill_warn_bg="#FFF4D6", pill_warn_ink="#7A3E00",
        pill_bad_bg="#FEE4E2", pill_bad_ink="#7A1C14", pill_info_bg="#E0ECFF", pill_info_ink="#0B3A8C",
        pill_neutral_bg="#E8F2F3", pill_neutral_ink="#314548",
        field_mint="#E3F1F2", field_sky="#DCEBF7", field_blush="#FCE4E6", field_ink=INK,
        shadow="rgba(19,43,46,0.12)",
        teal=TEAL, teal_deep=TEAL_DEEP, action=AMBER, action_hover=_mix(AMBER, "#000000", 0.08),
        action_fg=INK, action_ink=AMBER_INK, mist="#E3F1F2", grid="#0D1E6066",
        pad=pad,
    )


_current: Tokens = build_tokens(False)
_fonts_loaded = False


def caret_image(color: str) -> str:
    """Path (forward slashes, for QSS ``url()``) of a 12 px chevron in ``color``.

    QSS cannot draw a glyph, so the combo-box arrow is a tiny SVG written once
    per colour into the user's temp folder.
    """
    import tempfile
    folder = Path(tempfile.gettempdir()) / "project-opener-ui"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"caret-{color.lstrip('#').lower()}.svg"
    if not path.exists():
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
            f'<path d="M2.5 4.5 L6 8 L9.5 4.5" fill="none" stroke="{color}" stroke-width="1.5" '
            'stroke-linecap="round" stroke-linejoin="round"/></svg>', encoding="utf-8")
    return path.as_posix()


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
    """Register the bundled fonts (Instrument Sans, Archivo, JetBrains Mono, Cormorant Garamond italic,
    and Onest for 3.x callers) once per process."""
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
    """Archivo (page titles, the hero, numerals); the body face where it is missing."""
    load_fonts()
    return DISPLAY_FAMILY if DISPLAY_FAMILY in set(QFontDatabase.families()) else preferred_font()


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
    caret = caret_image(t.text_muted)
    caret_faint = caret_image(t.text_faint)
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
    QLabel#field_label {{ color: {t.text}; font-weight: 500; }}
    QLabel#error {{ color: {t.danger}; }}
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
    QLineEdit[invalid="true"], QComboBox[invalid="true"], QPlainTextEdit[invalid="true"], QListWidget[invalid="true"],
    QLineEdit[invalid="true"]:focus, QComboBox[invalid="true"]:focus, QPlainTextEdit[invalid="true"]:focus, QListWidget[invalid="true"]:focus {{ border: 2px solid {t.danger}; padding: 6px 10px; }}
    QLineEdit#search {{ padding-left: 34px; border-radius: {pill}px; }}
    QLineEdit#search:focus {{ padding-left: 33px; }}
    QComboBox {{ padding-right: 28px; }}
    QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; border: none; width: 28px; }}
    QComboBox::down-arrow {{ image: url("{caret}"); width: 12px; height: 12px; }}
    QComboBox::down-arrow:disabled {{ image: url("{caret_faint}"); }}
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
    QPushButton#danger:hover {{ background-color: {t.pill_bad_bg}; border-color: {t.pill_bad_bg}; color: {t.pill_bad_ink}; }}
    QPushButton#danger:focus {{ border: 2px solid {t.danger}; }}
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
