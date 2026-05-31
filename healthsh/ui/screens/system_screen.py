"""System placeholder screen.

The real implementation lands in a later sprint — see the body description.
For sprint 0 this only provides the chrome target the sidebar routes to.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

# Header subtitle exposed via ``header_subtitle()`` so MainWindow can pick it up.
_SUBTITLE: str = "processes and sensors · coming in sprint 2"


class SystemScreen(QWidget):
    """System screen — placeholder until the real composition ships."""

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        heading = QLabel("System")
        heading.setProperty("role", "kpi")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)

        description = QLabel(
            "Per-core bars, temperature/swap/load cards and the sortable "
            "process table land in issue #16."
        )
        description.setProperty("role", "muted")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)

        layout.addStretch(1)
        layout.addWidget(heading, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(description, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(2)

    def header_subtitle(self) -> str:
        """Return the muted subtitle to display in the application header."""
        return _SUBTITLE
