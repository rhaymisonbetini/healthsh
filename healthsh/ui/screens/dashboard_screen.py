"""Dashboard placeholder screen.

The real implementation lands in a later sprint — see the body description.
For sprint 0 this only provides the chrome target the sidebar routes to.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

# Header subtitle exposed via ``header_subtitle()`` so MainWindow can pick it up.
_SUBTITLE: str = "system health · coming in sprint 1"


class DashboardScreen(QWidget):
    """Dashboard screen — placeholder until the real composition ships."""

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        heading = QLabel("Dashboard")
        heading.setProperty("role", "kpi")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)

        description = QLabel(
            "Live gauges, the 60s sparkline, the AI banner and the "
            "container/top-mem grid will land in issue #10."
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
