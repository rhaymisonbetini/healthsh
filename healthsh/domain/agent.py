"""Agent value objects — :class:`ToolCallEvent` and :class:`AgentResponse`.

These are pure data so the UI in #27 can render assistant turns with the
tool-call chips that fired during the agent loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ToolCallEvent:
    """A single tool invocation captured during the agent loop.

    Attributes:
        name: Tool name (e.g. ``"get_metrics"``).
        arguments: JSON-friendly arguments the model passed to the tool.
        result_summary: Short human-readable summary of what the tool
            returned (e.g. ``"7 rows, 13:50–14:10"``). The raw result is not
            stored on the event — only a redacted hint suitable for a chip.
        ts: Wall-clock time of the call (UTC).
    """

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result_summary: str = ""
    ts: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass(frozen=True)
class AgentResponse:
    """The final assistant response returned by :meth:`AIService.ask`."""

    text: str
    tool_calls: tuple[ToolCallEvent, ...] = field(default_factory=tuple)
    backend: str = ""
    model: str = ""
