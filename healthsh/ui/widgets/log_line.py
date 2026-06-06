"""``LogLine(QWidget)`` — one journald entry rendered as a row.

Layout (left → right): timestamp (muted mono) · 3 px vertical severity bar in
the severity colour · unit (blue mono) · message (primary sans, elided when it
overflows).

The widget is immutable: parents recycle them when filters change. A cached
mono :class:`QFont` is shared across all instances so we never re-probe the
font database per line.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget

from healthsh.core.log_severity import SeverityCategory, priority_to_category
from healthsh.domain.log_entry import LogEntry
from healthsh.ui.theme.palette import (
    ACCENT_AMBER,
    ACCENT_BLUE,
    ACCENT_RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
)

# Severity colour token per category. Owned here (UI layer) so ``core`` stays
# Qt-free.
_CATEGORY_COLOR: dict[SeverityCategory, str] = {
    "err": ACCENT_RED,
    "warn": ACCENT_AMBER,
    "info": ACCENT_BLUE,
    "debug": TEXT_MUTED,
}

# Mono font candidates, in priority order.
_MONO_CANDIDATES: tuple[str, ...] = (
    "JetBrains Mono",
    "Fira Code",
    "Cascadia Mono",
    "DejaVu Sans Mono",
)

# Per-line geometry.
_SEVERITY_BAR_WIDTH: int = 3
_SEVERITY_BAR_HEIGHT: int = 16
_PADDING_H: int = 12
_PADDING_V: int = 6
_MESSAGE_MIN_WIDTH: int = 200


def category_color(category: SeverityCategory) -> str:
    """Return the ``#rrggbb`` hex token for a severity category."""
    return _CATEGORY_COLOR[category]


@lru_cache(maxsize=1)
def mono_font() -> QFont:
    """Return the cached mono :class:`QFont` used by the Logs UI.

    Walks :data:`_MONO_CANDIDATES` and picks the first family installed on the
    system; falls back to Qt's :func:`QFontDatabase.systemFont` of the fixed
    style hint when nothing matches.
    """
    available = set(QFontDatabase.families())
    for family in _MONO_CANDIDATES:
        if family in available:
            font = QFont(family)
            font.setStyleHint(QFont.StyleHint.Monospace)
            font.setPixelSize(12)
            return font
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPixelSize(12)
    return font


def _severity_bar(color_hex: str) -> QFrame:
    """Tiny coloured rectangle marking the entry's severity category."""
    bar = QFrame()
    bar.setObjectName("log-severity-bar")
    bar.setFixedSize(_SEVERITY_BAR_WIDTH, _SEVERITY_BAR_HEIGHT)
    bar.setStyleSheet(f"#log-severity-bar {{ background-color: {color_hex}; border-radius: 1px; }}")
    return bar


class LogLine(QWidget):
    """Read-only row rendering a single :class:`LogEntry`."""

    def __init__(self, entry: LogEntry, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entry: LogEntry = entry
        self._category: SeverityCategory = priority_to_category(entry.priority)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(_PADDING_H, _PADDING_V, _PADDING_H, _PADDING_V)
        layout.setSpacing(8)

        # Timestamp.
        ts_label = QLabel(entry.ts.strftime("%H:%M:%S"))
        ts_label.setFont(mono_font())
        ts_label.setStyleSheet(f"color: {TEXT_MUTED};")
        layout.addWidget(ts_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Severity bar.
        layout.addWidget(
            _severity_bar(_CATEGORY_COLOR[self._category]),
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )

        # Unit.
        unit_label = QLabel(entry.unit or "—")
        unit_label.setFont(mono_font())
        unit_label.setStyleSheet(f"color: {ACCENT_BLUE};")
        layout.addWidget(unit_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Message (elided when long).
        self._message_label = QLabel()
        self._message_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        self._message_label.setMinimumWidth(_MESSAGE_MIN_WIDTH)
        self._message_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._message_label.setText(self._elided_message(_MESSAGE_MIN_WIDTH))
        layout.addWidget(self._message_label, stretch=1, alignment=Qt.AlignmentFlag.AlignVCenter)

    # ------------------------------------------------------------------ API

    def entry(self) -> LogEntry:
        """Return the underlying :class:`LogEntry`."""
        return self._entry

    def category(self) -> SeverityCategory:
        """Return the severity category resolved from the entry's priority."""
        return self._category

    def category_color_hex(self) -> str:
        """Return the colour hex this line's severity bar paints with."""
        return _CATEGORY_COLOR[self._category]

    # --------------------------------------------------------------- helpers

    def _elided_message(self, width: int) -> str:
        metrics = QFontMetrics(self._message_label.font())
        return metrics.elidedText(self._entry.message, Qt.TextElideMode.ElideRight, max(width, 80))

    def resizeEvent(self, event) -> None:  # noqa: D401 — Qt callback name
        super().resizeEvent(event)
        # Re-elide using the current label width so the row fits without
        # introducing a horizontal scrollbar.
        available = max(self._message_label.width(), _MESSAGE_MIN_WIDTH)
        self._message_label.setText(self._elided_message(available))
