"""``ChatBubble(QFrame)`` — user / assistant bubble used by the AI chat screen.

Two variants:
- ``role="user"``: right-aligned, ``bg.card``.
- ``role="assistant"``: left-aligned, ``bg.card``, may stack tool-call chips
  on top of the message text.

The widget is mutable on the assistant side so a single bubble can absorb
streamed text deltas (``append_text``) and prepend chips
(``prepend_chip``) as :class:`AIService` emits events during the agent loop.
"""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from healthsh.ui.theme.palette import (
    BG_CARD,
    BG_CARD_INACTIVE,
    BORDER_DEFAULT,
    RADIUS_CARD,
    TEXT_PRIMARY,
)

BubbleRole = Literal["user", "assistant"]

# Maximum bubble width as a fraction of the parent scroll area.
_MAX_BUBBLE_WIDTH: int = 640


class ChatBubble(QFrame):
    """Rounded card holding a role-coloured chat turn."""

    def __init__(self, *, role: BubbleRole, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._role: BubbleRole = role
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMaximumWidth(_MAX_BUBBLE_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        background = BG_CARD if role == "user" else BG_CARD_INACTIVE
        self.setStyleSheet(
            f"ChatBubble {{ background-color: {background}; "
            f"border: 1px solid {BORDER_DEFAULT}; border-radius: {RADIUS_CARD}px; }}"
        )

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(14, 10, 14, 10)
        self._outer.setSpacing(8)

        # Chips area (only used by assistant bubbles).
        self._chip_row = QHBoxLayout()
        self._chip_row.setContentsMargins(0, 0, 0, 0)
        self._chip_row.setSpacing(6)
        self._outer.addLayout(self._chip_row)

        # Text label.
        self._text_label = QLabel("")
        self._text_label.setProperty("role", "primary")
        self._text_label.setWordWrap(True)
        self._text_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        self._text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._outer.addWidget(self._text_label)

    # ------------------------------------------------------------------ API

    def role(self) -> BubbleRole:
        """Return ``"user"`` or ``"assistant"``."""
        return self._role

    def text(self) -> str:
        """Return the bubble's current message text."""
        return self._text_label.text()

    def set_text(self, text: str) -> None:
        """Replace the message text."""
        self._text_label.setText(text)

    def append_text(self, delta: str) -> None:
        """Append a streamed delta to the existing message."""
        if delta:
            self._text_label.setText(self._text_label.text() + delta)

    def prepend_chip(self, chip: QWidget) -> None:
        """Add a tool-call chip to the row above the message."""
        self._chip_row.addWidget(chip)

    def chip_row(self) -> QHBoxLayout:
        """Return the chip row layout (used by tests + the AI screen)."""
        return self._chip_row
