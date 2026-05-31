"""AI insight banner — amber-bordered card with a sparkles icon and copy.

Sprint 1 ships this with a static placeholder. Sprint 5 (#26) swaps the
placeholder for live :class:`healthsh.domain.insight.Insight` content via
:meth:`AIBanner.set_text`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from healthsh.ui.icons import get_icon_pixmap
from healthsh.ui.theme.palette import ACCENT_AMBER, TEXT_PRIMARY

_ICON_SIZE: int = 18

# Default copy shown until issue #26 replaces it with a live Insight.
PLACEHOLDER_PREFIX: str = "Analysis:"
PLACEHOLDER_BODY: str = (
    "AI insights will appear here once Sprint 5 is complete. "
    "For now this is a static banner that reserves the visual contract."
)


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
        self._prefix_label.setStyleSheet("font-weight: 500;")
        outer.addWidget(self._prefix_label, alignment=Qt.AlignmentFlag.AlignTop)

        self._body_label = QLabel()
        self._body_label.setProperty("role", "primary")
        self._body_label.setWordWrap(True)
        self._body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self._body_label, stretch=1)

        self.set_text(prefix, body)
        # Silence unused-import linter while keeping the reference around for
        # readers (TEXT_PRIMARY is the body color when the QSS role fails).
        _ = TEXT_PRIMARY

    def set_text(self, prefix: str, body: str) -> None:
        """Replace the visible banner text."""
        self._prefix_label.setText(prefix)
        self._body_label.setText(body)

    def prefix(self) -> str:
        """Return the current prefix text."""
        return self._prefix_label.text()

    def body(self) -> str:
        """Return the current body text."""
        return self._body_label.text()
