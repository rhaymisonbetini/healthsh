"""``ToolCallChip(QFrame)`` — pill that visualises a single :class:`ToolCallEvent`.

Renders an emoji icon + the tool's chip label (built by the tool's
summariser). Used inside :class:`ChatBubble` to show users what the agent
consulted before answering.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from healthsh.domain.agent import ToolCallEvent
from healthsh.ui.theme.palette import ACCENT_BLUE, BG_CARD, BORDER_DEFAULT, RADIUS_PILL

# Default emoji per tool name.
_TOOL_ICONS: dict[str, str] = {
    "get_metrics": "📊",
    "get_logs": "📄",
    "get_containers": "🐳",
    "get_processes": "🧠",
}


def icon_for_tool(name: str) -> str:
    """Return the chip icon for a tool name (falls back to a sparkle)."""
    return _TOOL_ICONS.get(name, "✨")


class ToolCallChip(QFrame):
    """One tool-call chip — icon + summary label, pill-shaped."""

    def __init__(self, event: ToolCallEvent, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._event: ToolCallEvent = event
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"ToolCallChip {{ background-color: {BG_CARD}; "
            f"border: 1px solid {BORDER_DEFAULT}; "
            f"border-radius: {RADIUS_PILL}px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 10, 3)
        layout.setSpacing(6)

        icon_label = QLabel(icon_for_tool(event.name))
        layout.addWidget(icon_label)

        text_label = QLabel(event.result_summary or event.name)
        text_label.setStyleSheet(
            f"color: {ACCENT_BLUE}; "
            "font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 11px;"
        )
        layout.addWidget(text_label)

    def tool_event(self) -> ToolCallEvent:
        """Return the underlying :class:`ToolCallEvent`.

        Not named ``event`` because that collides with :meth:`QObject.event`.
        """
        return self._event
