"""AIScreen tests — bubble flow, chip rendering, backend label, suggestions."""

from __future__ import annotations

from typing import Any

from healthsh.services.ai_service import AIService, MockBackend, _BackendTurn, _ToolCallDirective
from healthsh.ui.screens.ai_screen import AIScreen
from healthsh.ui.widgets.chat_bubble import ChatBubble
from healthsh.ui.widgets.tool_call_chip import ToolCallChip


def _wait_idle(qtbot, screen: AIScreen) -> None:
    qtbot.waitUntil(lambda: screen._send_button.isEnabled(), timeout=2000)  # type: ignore[attr-defined]


def test_empty_state_until_first_send(qtbot) -> None:
    screen = AIScreen()
    qtbot.addWidget(screen)
    assert screen.stack().currentIndex() == 0


def test_send_user_then_assistant_bubbles(qtbot) -> None:
    backend = MockBackend(script=[_BackendTurn(text="CPU is fine.")])
    service = AIService(backend=backend)
    screen = AIScreen(ai_service=service)
    qtbot.addWidget(screen)
    screen.send("hi")
    _wait_idle(qtbot, screen)
    bubbles = screen.bubbles()
    assert [b.role() for b in bubbles] == ["user", "assistant"]
    assert bubbles[0].text() == "hi"
    assert "CPU is fine" in bubbles[1].text()


def test_tool_call_event_renders_chip_in_assistant_bubble(qtbot) -> None:
    backend = MockBackend(
        script=[
            _BackendTurn(tool_calls=[_ToolCallDirective(name="get_metrics", arguments={})]),
            _BackendTurn(text="CPU averaged 18%."),
        ]
    )
    service = AIService(backend=backend)
    service.registry().register(
        # Register a minimal handler so dispatch succeeds.
        __import__("healthsh.services.ai_service", fromlist=["Tool"]).Tool(  # type: ignore[attr-defined]
            name="get_metrics",
            description="",
            parameters={"type": "object", "properties": {}},
            handler=lambda **_kwargs: {"metric": "cpu_pct", "samples": []},
            summarise=lambda _r: "metrics chip",
        )
    )
    screen = AIScreen(ai_service=service)
    qtbot.addWidget(screen)
    screen.send("why slow?")
    _wait_idle(qtbot, screen)
    assistant: ChatBubble = screen.bubbles()[-1]
    chips = [assistant.chip_row().itemAt(i).widget() for i in range(assistant.chip_row().count())]
    assert any(isinstance(w, ToolCallChip) for w in chips)


def test_failed_ask_shows_inline_error_bubble(qtbot, monkeypatch) -> None:
    backend = MockBackend(script=[_BackendTurn(text="never reached")])
    service = AIService(backend=backend)

    def _boom(_prompt: str) -> Any:
        raise RuntimeError("agent down")

    monkeypatch.setattr(service, "ask", _boom)
    screen = AIScreen(ai_service=service)
    qtbot.addWidget(screen)
    screen.send("hello")
    _wait_idle(qtbot, screen)
    assistant = screen.bubbles()[-1]
    assert "agent failed" in assistant.text()


def test_suggestion_chip_populates_input(qtbot) -> None:
    screen = AIScreen()
    qtbot.addWidget(screen)
    screen._on_suggestion("Why is it slow?")  # type: ignore[attr-defined]
    assert screen._input.text() == "Why is it slow?"  # type: ignore[attr-defined]


def test_send_without_service_is_noop(qtbot) -> None:
    screen = AIScreen()
    qtbot.addWidget(screen)
    screen.send("ignored")
    # Stack should still be on the empty state.
    assert screen.stack().currentIndex() == 0
    assert screen.bubbles() == []


def test_set_ai_service_swaps_at_runtime(qtbot) -> None:
    screen = AIScreen()
    qtbot.addWidget(screen)
    backend = MockBackend(script=[_BackendTurn(text="ok")])
    service = AIService(backend=backend)
    screen.set_ai_service(service)
    screen.send("hello")
    _wait_idle(qtbot, screen)
    assert screen.bubbles()[-1].text() == "ok"


def test_subtitle_reports_backend(qtbot) -> None:
    backend = MockBackend(script=[_BackendTurn(text="ok")])
    service = AIService(backend=backend)
    screen = AIScreen(ai_service=service)
    qtbot.addWidget(screen)
    assert screen.header_subtitle() == "assistant · mock"
