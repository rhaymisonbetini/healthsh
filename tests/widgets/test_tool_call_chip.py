"""ToolCallChip and BackendSelector smoke tests."""

from __future__ import annotations

from datetime import UTC, datetime

from healthsh.domain.agent import ToolCallEvent
from healthsh.ui.widgets.backend_selector import BackendSelector
from healthsh.ui.widgets.tool_call_chip import ToolCallChip, icon_for_tool


def _event(name: str = "get_metrics", summary: str = "metrics chip") -> ToolCallEvent:
    return ToolCallEvent(
        name=name,
        arguments={},
        result_summary=summary,
        ts=datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC),
    )


def test_icon_lookup_known_tools() -> None:
    assert icon_for_tool("get_metrics") == "📊"
    assert icon_for_tool("get_logs") == "📄"
    assert icon_for_tool("get_containers") == "🐳"
    assert icon_for_tool("get_processes") == "🧠"


def test_icon_lookup_unknown_tool_falls_back() -> None:
    assert icon_for_tool("not-a-tool") == "✨"


def test_chip_carries_event(qtbot) -> None:
    chip = ToolCallChip(_event())
    qtbot.addWidget(chip)
    assert chip.tool_event().name == "get_metrics"


def test_backend_selector_emits_on_change(qtbot) -> None:
    selector = BackendSelector(current="ollama")
    qtbot.addWidget(selector)
    received: list[str] = []
    selector.backend_changed.connect(received.append)
    selector.set_backend("anthropic")
    assert received == ["anthropic"]


def test_backend_selector_rejects_unknown_backend(qtbot) -> None:
    selector = BackendSelector()
    qtbot.addWidget(selector)
    import pytest

    with pytest.raises(ValueError):
        selector.set_backend("gpt-2")
