"""Global QSS stylesheet and ``apply_theme`` bootstrap for the healthsh UI.

This module composes the application-wide Qt stylesheet (``STYLE_QSS``) by
interpolating tokens from :mod:`healthsh.ui.theme.palette` and exposes
:func:`apply_theme` which wires the stylesheet, base font and Fusion style onto
a :class:`PySide6.QtWidgets.QApplication` instance.

The QSS is intentionally flat and dark, mirroring the normative design tokens
in HEALTHSH_ROADMAP.md §4. Components opt into roles via the Qt dynamic
property ``role`` (for example ``frame.setProperty("role", "card")``).
"""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from healthsh.ui.theme.palette import (
    ACCENT_AMBER,
    ACCENT_BLUE,
    ACCENT_GREEN,
    ACCENT_PURPLE,
    ACCENT_RED,
    BG_AI_BANNER,
    BG_CARD,
    BG_CARD_INACTIVE,
    BG_CHROME,
    BG_WINDOW,
    BORDER_AI,
    BORDER_DEFAULT,
    BORDER_ROW,
    FONT_FAMILY_PREFERENCE,
    RADIUS_BAR,
    RADIUS_CARD,
    RADIUS_CARD_SMALL,
    RADIUS_PILL,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TRACK,
    WEIGHT_REGULAR,
)

# Base body font size in pixels. Matches the QSS ``font-size: 12px`` rule so
# the QFont set on QApplication and the cascading QSS rule agree.
_BASE_FONT_SIZE_PX: int = 12


STYLE_QSS: str = f"""
/* ---------- Window / base ---------- */
QMainWindow,
QWidget {{
    background-color: {BG_WINDOW};
    color: {TEXT_PRIMARY};
    font-size: 12px;
}}

QWidget:disabled {{
    color: {TEXT_MUTED};
}}

/* ---------- Chrome (header / sidebar) ---------- */
QFrame[role="chrome"] {{
    background-color: {BG_CHROME};
    border: none;
}}

QFrame[role="header"] {{
    background-color: {BG_CHROME};
    border: none;
    border-bottom: 1px solid {BORDER_DEFAULT};
    padding: 12px 16px;
}}

QFrame[role="sidebar"] {{
    background-color: {BG_CHROME};
    border: none;
    border-right: 1px solid {BORDER_DEFAULT};
    padding: 16px 12px;
}}

/* ---------- Cards ---------- */
QFrame[role="card"] {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_CARD}px;
    padding: 12px 14px;
}}

QFrame[role="card-small"] {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_CARD_SMALL}px;
    padding: 10px 12px;
}}

QFrame[role="card-inactive"] {{
    background-color: {BG_CARD_INACTIVE};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_CARD}px;
    padding: 12px 14px;
    color: {TEXT_MUTED};
}}

QFrame[role="card-inactive"] QLabel {{
    color: {TEXT_MUTED};
}}

QFrame[role="ai-banner"] {{
    background-color: {BG_AI_BANNER};
    border: 1px solid {BORDER_AI};
    border-radius: {RADIUS_CARD}px;
    padding: 12px 14px;
}}

/* ---------- Row separators ---------- */
QFrame[role="row"] {{
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {BORDER_ROW};
}}

/* ---------- Labels by role ---------- */
QLabel {{
    background: transparent;
    color: {TEXT_PRIMARY};
}}

QLabel[role="primary"] {{ color: {TEXT_PRIMARY}; }}
QLabel[role="muted"]   {{ color: {TEXT_MUTED}; }}
QLabel[role="amber"]   {{ color: {ACCENT_AMBER}; }}
QLabel[role="blue"]    {{ color: {ACCENT_BLUE}; }}
QLabel[role="purple"]  {{ color: {ACCENT_PURPLE}; }}
QLabel[role="green"]   {{ color: {ACCENT_GREEN}; }}
QLabel[role="red"]     {{ color: {ACCENT_RED}; }}

QLabel[role="section-title"] {{
    color: {TEXT_PRIMARY};
    font-size: 13px;
    font-weight: 500;
}}

QLabel[role="kpi"] {{
    color: {TEXT_PRIMARY};
    font-size: 18px;
    font-weight: 500;
}}

QLabel[role="hint"] {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}

QLabel[role="mono"] {{
    font-family: "JetBrains Mono", "Fira Code", "Cascadia Mono", monospace;
}}

/* ---------- Pills / badges ---------- */
QLabel[role="pill"] {{
    background-color: {TRACK};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_PILL}px;
    padding: 2px 8px;
    font-size: 11px;
}}

QLabel[role="pill-amber"] {{
    background-color: {TRACK};
    color: {ACCENT_AMBER};
    border: 1px solid {BORDER_AI};
    border-radius: {RADIUS_PILL}px;
    padding: 2px 8px;
    font-size: 11px;
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_CARD_SMALL}px;
    padding: 6px 12px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {BG_AI_BANNER};
    border: 1px solid {ACCENT_BLUE};
}}

QPushButton:pressed {{
    background-color: {BG_CARD_INACTIVE};
}}

QPushButton:disabled {{
    color: {TEXT_MUTED};
    border: 1px solid {BORDER_ROW};
}}

QPushButton[role="primary"] {{
    background-color: {ACCENT_BLUE};
    color: {BG_WINDOW};
    border: 1px solid {ACCENT_BLUE};
}}

QPushButton[role="primary"]:hover {{
    background-color: {ACCENT_PURPLE};
    border: 1px solid {ACCENT_PURPLE};
}}

QPushButton[role="ghost"] {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {TEXT_MUTED};
}}

QPushButton[role="ghost"]:hover {{
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
}}

/* ---------- Inputs ---------- */
QLineEdit,
QPlainTextEdit,
QTextEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_CARD_SMALL}px;
    padding: 6px 10px;
    selection-background-color: {ACCENT_BLUE};
    selection-color: {BG_WINDOW};
}}

QLineEdit:focus,
QPlainTextEdit:focus,
QTextEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDoubleSpinBox:focus {{
    border: 1px solid {ACCENT_BLUE};
}}

QComboBox::drop-down {{
    border: none;
    width: 18px;
}}

QComboBox QAbstractItemView {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    selection-background-color: {ACCENT_BLUE};
    selection-color: {BG_WINDOW};
    outline: 0;
}}

/* ---------- Progress bar ---------- */
QProgressBar {{
    background-color: {TRACK};
    border: none;
    border-radius: {RADIUS_BAR}px;
    text-align: center;
    color: {TEXT_PRIMARY};
    min-height: 6px;
    max-height: 6px;
}}

QProgressBar::chunk {{
    background-color: {ACCENT_BLUE};
    border-radius: {RADIUS_BAR}px;
}}

/* ---------- Tabs ---------- */
QTabWidget::pane {{
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_CARD}px;
    background-color: {BG_CARD};
}}

QTabBar::tab {{
    background-color: transparent;
    color: {TEXT_MUTED};
    padding: 6px 12px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 4px;
}}

QTabBar::tab:selected {{
    color: {TEXT_PRIMARY};
    border-bottom: 2px solid {ACCENT_BLUE};
}}

QTabBar::tab:hover {{
    color: {TEXT_PRIMARY};
}}

/* ---------- Lists / trees / tables ---------- */
QListView,
QTreeView,
QTableView {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_CARD}px;
    gridline-color: {BORDER_ROW};
    selection-background-color: {BG_AI_BANNER};
    selection-color: {TEXT_PRIMARY};
    outline: 0;
}}

QHeaderView::section {{
    background-color: {BG_CHROME};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER_DEFAULT};
    padding: 6px 10px;
    font-weight: 500;
}}

/* ---------- Scroll bars ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {TRACK};
    border-radius: 5px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background: {BORDER_DEFAULT};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    background: none;
    height: 0;
    border: none;
}}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {TRACK};
    border-radius: 5px;
    min-width: 24px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {BORDER_DEFAULT};
}}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    background: none;
    width: 0;
    border: none;
}}

QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* ---------- Tooltip ---------- */
QToolTip {{
    background-color: {BG_CHROME};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 6px;
    padding: 4px 8px;
}}

/* ---------- Menus ---------- */
QMenu {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_CARD_SMALL}px;
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 14px;
    border-radius: 6px;
}}

QMenu::item:selected {{
    background-color: {BG_AI_BANNER};
    color: {TEXT_PRIMARY};
}}

QMenu::separator {{
    height: 1px;
    background: {BORDER_DEFAULT};
    margin: 4px 6px;
}}

/* ---------- Splitter ---------- */
QSplitter::handle {{
    background-color: {BORDER_DEFAULT};
}}

QSplitter::handle:horizontal {{
    width: 1px;
}}

QSplitter::handle:vertical {{
    height: 1px;
}}
"""


def _pick_first_available_family(families: tuple[str, ...]) -> str | None:
    """Return the first font family from ``families`` known to the system.

    Walks the candidate list in order and returns the first entry that
    :class:`PySide6.QtGui.QFontDatabase` reports as installed. Returns
    ``None`` if none are available, in which case callers fall back to the
    Qt platform default.
    """
    available = set(QFontDatabase.families())
    for family in families:
        if family in available:
            return family
    return None


def apply_theme(app: QApplication) -> None:
    """Install the healthsh dark theme on ``app``.

    Sets the application font (sans family by preference, 12 px, regular
    weight), applies :data:`STYLE_QSS`, and switches to the ``Fusion`` style
    for predictable cross-distro rendering.

    Idempotent: calling it more than once just re-applies the same state.
    Call once at application boot, immediately after the :class:`QApplication`
    is constructed.
    """
    family = _pick_first_available_family(FONT_FAMILY_PREFERENCE)
    font = QFont()
    if family is not None:
        font.setFamily(family)
    # Use pixel sizing so the QFont matches the QSS ``font-size: 12px`` rule
    # exactly. Point sizing would render ~16 px at the standard 96-dpi mapping.
    font.setPixelSize(_BASE_FONT_SIZE_PX)
    font.setWeight(QFont.Weight(WEIGHT_REGULAR))
    app.setFont(font)

    app.setStyleSheet(STYLE_QSS)
    app.setStyle("Fusion")
