"""AI insight banner — amber-bordered card with a sparkles icon and copy.

Sprint 1 shipped the visual contract; Sprint 5 wires real
:class:`healthsh.domain.insight.Insight` content via :meth:`AIBanner.set_insight`.

Body text supports a tiny markup convention: anything between matching
backticks (`` `like-this` ``) is rendered as a blue, mono-spaced entity.
The escape rule is intentionally dumb (no nesting) — matches how the
analysis engine constructs its messages.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from healthsh.domain.insight import Insight
from healthsh.ui.icons import get_icon_pixmap
from healthsh.ui.theme.palette import (
    ACCENT_AMBER,
    ACCENT_BLUE,
    ACCENT_RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
)

_ICON_SIZE: int = 18

# Default copy shown until a real insight arrives.
PLACEHOLDER_PREFIX: str = "Analysis:"
PLACEHOLDER_BODY: str = (
    "AI insights will appear here once Sprint 5 is complete. "
    "For now this is a static banner that reserves the visual contract."
)

# Calm fallback when no insight applies for the current screen.
HEALTHY_PREFIX: str = "All looks healthy."
HEALTHY_BODY: str = ""

# Backtick capture — non-greedy so adjacent entities don't merge.
_ENTITY_PATTERN: re.Pattern[str] = re.compile(r"`([^`]+)`")


def _severity_color(severity: str) -> str:
    """Return the prefix colour for an :class:`Insight` severity."""
    if severity == "critical":
        return ACCENT_RED
    if severity == "warning":
        return ACCENT_AMBER
    return ACCENT_BLUE


def _render_body_with_entities(body: str) -> str:
    """Wrap backtick-delimited entities in a blue mono `<code>` span."""

    def _wrap(match: re.Match[str]) -> str:
        entity = match.group(1)
        return (
            f'<span style="color: {ACCENT_BLUE}; '
            "font-family: 'JetBrains Mono', 'Fira Code', monospace;\">"
            f"{entity}</span>"
        )

    return _ENTITY_PATTERN.sub(_wrap, body)


class AIBanner(QFrame):
    """Amber-bordered insight banner used on multiple screens."""

    def __init__(
        self,
        *,
        prefix: str = PLACEHOLDER_PREFIX,
        body: str = PLACEHOLDER_BODY,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("role", "ai-banner")
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        icon = QLabel()
        icon.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        icon.setPixmap(get_icon_pixmap("sparkles", ACCENT_AMBER, _ICON_SIZE))
        outer.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)

        self._prefix_label = QLabel()
        self._prefix_label.setProperty("role", "amber")
        # Bold prefix per spec (weight 500).
        self._prefix_label.setStyleSheet(f"font-weight: 500; color: {ACCENT_AMBER};")
        outer.addWidget(self._prefix_label, alignment=Qt.AlignmentFlag.AlignTop)

        self._body_label = QLabel()
        self._body_label.setProperty("role", "primary")
        self._body_label.setWordWrap(True)
        self._body_label.setTextFormat(Qt.TextFormat.RichText)
        self._body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self._body_label, stretch=1)

        self._current_insight: Insight | None = None
        self.set_text(prefix, body)
        # Silence unused-import linter while keeping the reference around for
        # readers (TEXT_PRIMARY is the body color when the QSS role fails).
        _ = (TEXT_PRIMARY, TEXT_MUTED)

    def set_text(self, prefix: str, body: str) -> None:
        """Replace the visible banner text. ``body`` accepts backtick entities."""
        self._prefix_label.setText(prefix)
        self._prefix_label.setStyleSheet(f"font-weight: 500; color: {ACCENT_AMBER};")
        self._body_label.setText(_render_body_with_entities(body))

    def set_insight(self, insight: Insight | None) -> None:
        """Replace the banner content from an :class:`Insight` (or healthy fallback)."""
        self._current_insight = insight
        if insight is None:
            self._prefix_label.setText(HEALTHY_PREFIX)
            self._prefix_label.setStyleSheet(f"font-weight: 500; color: {TEXT_MUTED};")
            self._body_label.setText(HEALTHY_BODY)
            return
        self._prefix_label.setText(f"{insight.title} ·")
        self._prefix_label.setStyleSheet(
            f"font-weight: 500; color: {_severity_color(insight.severity)};"
        )
        self._body_label.setText(_render_body_with_entities(insight.message))

    def current_insight(self) -> Insight | None:
        """Return the insight currently displayed (or ``None`` for healthy)."""
        return self._current_insight

    def prefix(self) -> str:
        """Return the current prefix text."""
        return self._prefix_label.text()

    def body(self) -> str:
        """Return the current body text (rich-text rendered)."""
        return self._body_label.text()
