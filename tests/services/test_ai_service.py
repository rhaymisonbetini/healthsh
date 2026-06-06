"""AIService tests — agent loop, tool dispatch, hot backend swap, history."""

from __future__ import annotations

from typing import Any

import pytest

from healthsh.domain.agent import AgentResponse, ToolCallEvent
from healthsh.services.ai_service import (
    AIService,
    MockBackend,
    Tool,
    ToolRegistry,
    _BackendTurn,
    _ToolCallDirective,
)


def _registry_with_get_metrics(result: Any = None) -> ToolRegistry:
    registry = ToolRegistry()

    def _handler(**_kwargs: Any) -> dict:
        return result or {"metric": "cpu_pct", "samples": [{"ts": "x", "value": 1.0}]}

    registry.register(
        Tool(
            name="get_metrics",
            description="",
            parameters={"type": "object", "properties": {}},
            handler=_handler,
            summarise=lambda _r: "metrics chip",
        )
    )
    return registry


def test_one_round_text_only(qtbot) -> None:  # noqa: ARG001
    backend = MockBackend(script=[_BackendTurn(text="CPU is 12%")])
    service = AIService(backend=backend, registry=ToolRegistry())
    response = service.ask("What's my CPU?")
    assert isinstance(response, AgentResponse)
    assert response.text == "CPU is 12%"
    assert response.tool_calls == ()
    assert response.backend == "mock"


def test_tool_call_round_then_final_text(qtbot) -> None:
    backend = MockBackend(
        script=[
            _BackendTurn(tool_calls=[_ToolCallDirective(name="get_metrics", arguments={})]),
            _BackendTurn(text="CPU averaged 12% in the window."),
        ]
    )
    registry = _registry_with_get_metrics()
    service = AIService(backend=backend, registry=registry)
    events: list[dict[str, Any]] = []
    service.event.connect(events.append)
    response = service.ask("What's my CPU?")
    assert response.text == "CPU averaged 12% in the window."
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "get_metrics"
    assert response.tool_calls[0].result_summary == "metrics chip"
    # Streaming events: one tool_call, one text.
    kinds = [e["kind"] for e in events]
    assert kinds == ["tool_call", "text"]


def test_tool_failure_does_not_abort_loop(qtbot) -> None:  # noqa: ARG001
    backend = MockBackend(
        script=[
            _BackendTurn(tool_calls=[_ToolCallDirective(name="boom", arguments={})]),
            _BackendTurn(text="Could not gather the data."),
        ]
    )
    registry = ToolRegistry()

    def _boom(**_kwargs: Any) -> None:
        raise RuntimeError("simulated failure")

    registry.register(
        Tool(
            name="boom",
            description="",
            parameters={"type": "object", "properties": {}},
            handler=_boom,
        )
    )
    service = AIService(backend=backend, registry=registry)
    response = service.ask("anything")
    assert response.text == "Could not gather the data."
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].result_summary.startswith("boom failed")


def test_max_tool_rounds_caps_loop(qtbot) -> None:  # noqa: ARG001
    # Backend keeps requesting the same tool — the cap must bail out cleanly.
    backend = MockBackend(
        script=[_BackendTurn(tool_calls=[_ToolCallDirective(name="get_metrics", arguments={})])]
        * 20
    )
    registry = _registry_with_get_metrics()
    service = AIService(backend=backend, registry=registry)
    response = service.ask("loop forever")
    # MAX_TOOL_ROUNDS = 6 (see ai_service constant)
    assert len(response.tool_calls) == 6
    assert response.text == ""


def test_set_backend_at_runtime(qtbot) -> None:  # noqa: ARG001
    backend_a = MockBackend(script=[_BackendTurn(text="A")])
    backend_b = MockBackend(script=[_BackendTurn(text="B")])
    service = AIService(backend=backend_a)
    assert service.ask("hi").text == "A"
    service.set_backend(backend_b)
    assert service.ask("hi").text == "B"


def test_history_is_maintained_across_calls(qtbot) -> None:  # noqa: ARG001
    backend = MockBackend(
        script=[
            _BackendTurn(text="First answer"),
            _BackendTurn(text="Second answer"),
        ]
    )
    service = AIService(backend=backend)
    service.ask("Q1")
    service.ask("Q2")
    roles = [m["role"] for m in service.history()]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_reset_clears_history(qtbot) -> None:  # noqa: ARG001
    backend = MockBackend(script=[_BackendTurn(text="ok")])
    service = AIService(backend=backend)
    service.ask("Q1")
    service.reset()
    assert service.history() == []


def test_tool_registry_dispatch_unknown_raises() -> None:
    registry = ToolRegistry()
    with pytest.raises(KeyError):
        registry.dispatch("nope", {})


def test_tool_registry_definitions_round_trip() -> None:
    registry = _registry_with_get_metrics()
    defs = registry.definitions()
    assert len(defs) == 1
    assert defs[0]["name"] == "get_metrics"


def test_event_signal_payload_shape(qtbot) -> None:
    backend = MockBackend(script=[_BackendTurn(text="ok")])
    service = AIService(backend=backend)
    received: list[dict[str, Any]] = []
    service.event.connect(received.append)
    service.ask("hello")
    assert received == [{"kind": "text", "text": "ok"}]


def test_tool_call_event_carries_arguments(qtbot) -> None:  # noqa: ARG001
    backend = MockBackend(
        script=[
            _BackendTurn(
                tool_calls=[
                    _ToolCallDirective(
                        name="get_metrics",
                        arguments={"metric": "cpu_pct", "since": "x", "until": "y"},
                    )
                ]
            ),
            _BackendTurn(text="done"),
        ]
    )
    registry = _registry_with_get_metrics()
    service = AIService(backend=backend, registry=registry)
    response = service.ask("anything")
    event: ToolCallEvent = response.tool_calls[0]
    assert event.arguments == {"metric": "cpu_pct", "since": "x", "until": "y"}
