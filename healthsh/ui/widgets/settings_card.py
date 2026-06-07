"""``SettingsCard`` — a titled section card that stacks form rows.

Mirrors the design-system card (``role="card"`` → ``bg.card``, 10px radius,
1px ``border.default``, 12×14 padding from the QSS) with a 500-weight section
title followed by its rows. The Settings screen stacks five of these inside a
scroll area.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class SettingsCard(QFrame):
    """A single titled settings section."""

    def __init__(self, title: str, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 12)
        self._layout.setSpacing(2)

        self._title = QLabel(title)
        self._title.setProperty("role", "section-title")
        self._layout.addWidget(self._title)
        self._layout.addSpacing(6)

    def add_row(self, row: QWidget) -> None:
        """Append a form row (or any widget) to the section body."""
        self._layout.addWidget(row)

    def add_caption(self, text: str) -> QLabel:
        """Append a muted caption (used for the live threshold preview) and return it."""
        caption = QLabel(text)
        caption.setProperty("role", "hint")
        caption.setWordWrap(True)
        self._layout.addWidget(caption)
        return caption
