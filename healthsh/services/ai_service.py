"""Tool-calling AI agent service over Ollama / Anthropic / OpenAI backends.

This module implements the agent loop the roadmap calls "Blocksh's agent
base". See ``AGENT_BASE_LICENSE_AND_PROVENANCE.md`` next to this file for the
clean-room note.

High level
----------
- :class:`AIService` exposes :meth:`ask` (synchronous one-shot) and a Qt
  signal :pyattr:`event` for streaming text deltas + tool-call events that
  the chat UI in #27 renders as chips.
- :class:`Backend` is an abstract base; the concrete implementations
  (:class:`OllamaBackend`, :class:`AnthropicBackend`, :class:`OpenAIBackend`)
  translate the tool registry + chat history into the provider's wire format
  and surface tool calls back to the dispatcher. Tests use a
  :class:`MockBackend` that scripts a fixed conversation.
- Tools live in :mod:`healthsh.services.ai_tools` and are bound to a
  :class:`ToolRegistry` on the service at construction time.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from PySide6.QtCore import QObject, Signal

from healthsh.domain.agent import AgentResponse, ToolCallEvent
from healthsh.services import ai_tools

_LOG = logging.getLogger(__name__)

BackendName = Literal["ollama", "anthropic", "openai", "mock"]

# Maximum number of tool-call rounds inside a single ask() — guards against
# runaway agents.
MAX_TOOL_ROUNDS: int = 6


# ---------------------------------------------------------------------------
# Tool registry.
# ---------------------------------------------------------------------------


@dataclass
class Tool:
    """A registered tool: name + JSON-schema parameters + callable."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    summarise: Callable[[Any], str] | None = None


class ToolRegistry:
    """Maps tool names to bound handlers + definitions."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Add a tool — replacing any previous registration with the same name."""
        self._tools[tool.name] = tool

    def definitions(self) -> list[dict[str, Any]]:
        """Return the JSON-schema definitions for every registered tool."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in self._tools.values()
        ]

    def dispatch(self, name: str, arguments: dict[str, Any]) -> Any:
        """Invoke a tool by name with the model-supplied arguments."""
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name!r}")
        return self._tools[name].handler(**arguments)

    def summarise(self, name: str, result: Any) -> str:
        """Return the short chip label for ``result``, falling back to a generic."""
        tool = self._tools.get(name)
        if tool is not None and tool.summarise is not None:
            try:
                return tool.summarise(result)
            except Exception:  # noqa: BLE001
                _LOG.debug("summarise(%s) raised", name, exc_info=True)
        return name

    def names(self) -> list[str]:
        """Return the registered tool names (used by tests)."""
        return list(self._tools.keys())


# ---------------------------------------------------------------------------
# Backend abstraction.
# ---------------------------------------------------------------------------


@dataclass
class _ToolCallDirective:
    """One tool call requested by the model in a single turn."""

    name: str
    arguments: dict[str, Any]


@dataclass
class _BackendTurn:
    """The model's response to one turn: text + any tool calls it requested."""

    text: str = ""
    tool_calls: list[_ToolCallDirective] = field(default_factory=list)


class Backend(ABC):
    """Abstract LLM backend — translates chat history into the wire format."""

    name: BackendName

    @abstractmethod
    def run(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> _BackendTurn:
        """Run one round and return either text or tool-call requests."""


@dataclass
class MockBackend(Backend):
    """Scripted backend used by tests — yields the next turn from a list."""

    script: list[_BackendTurn]
    name: BackendName = "mock"
    _cursor: int = 0

    def run(
        self,
        messages: list[dict[str, Any]],  # noqa: ARG002
        tools: list[dict[str, Any]],  # noqa: ARG002
    ) -> _BackendTurn:
        if self._cursor >= len(self.script):
            return _BackendTurn(text="(end of script)")
        turn = self.script[self._cursor]
        self._cursor += 1
        return turn


@dataclass
class OllamaBackend(Backend):
    """Ollama HTTP backend — POST /api/chat with native tool support.

    Uses ``httpx`` lazily-imported so the dependency is optional at install
    time. The backend is intentionally minimal: one POST per round, no
    streaming for v1 (streaming polish lands in #27 once the UI can show
    text deltas live).
    """

    model: str = "llama3.1"
    endpoint: str = "http://localhost:11434"
    name: BackendName = "ollama"

    def run(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> _BackendTurn:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - install time
            raise RuntimeError("httpx is required for the Ollama backend") from exc
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "tools": [{"type": "function", "function": tool} for tool in tools],
        }
        response = httpx.post(
            f"{self.endpoint}/api/chat",
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
        body = response.json()
        message = body.get("message", {})
        text = str(message.get("content", "") or "")
        directives = [
            _ToolCallDirective(
                name=str(call["function"]["name"]),
                arguments=call["function"].get("arguments") or {},
            )
            for call in (message.get("tool_calls") or [])
        ]
        return _BackendTurn(text=text, tool_calls=directives)


@dataclass
class AnthropicBackend(Backend):
    """Anthropic Messages API backend — uses the official SDK lazily."""

    model: str = "claude-3-5-sonnet-latest"
    api_key: str | None = None
    name: BackendName = "anthropic"

    def run(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> _BackendTurn:
        try:
            from anthropic import Anthropic  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - install time
            raise RuntimeError("anthropic is required for the Anthropic backend") from exc
        client = Anthropic(api_key=self.api_key) if self.api_key else Anthropic()
        ant_tools = [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["parameters"],
            }
            for tool in tools
        ]
        # Anthropic expects the system prompt out-of-band.
        sys_messages = [m for m in messages if m["role"] == "system"]
        non_sys = [m for m in messages if m["role"] != "system"]
        response = client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=sys_messages[0]["content"] if sys_messages else "",
            tools=ant_tools,
            messages=non_sys,
        )
        text_parts: list[str] = []
        directives: list[_ToolCallDirective] = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(getattr(block, "text", ""))
            elif block_type == "tool_use":
                directives.append(
                    _ToolCallDirective(
                        name=getattr(block, "name", ""),
                        arguments=dict(getattr(block, "input", {}) or {}),
                    )
                )
        return _BackendTurn(text="".join(text_parts), tool_calls=directives)


@dataclass
class OpenAIBackend(Backend):
    """OpenAI Chat Completions backend — uses the official SDK lazily."""

    model: str = "gpt-4o-mini"
    api_key: str | None = None
    name: BackendName = "openai"

    def run(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> _BackendTurn:
        try:
            from openai import OpenAI  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - install time
            raise RuntimeError("openai is required for the OpenAI backend") from exc
        client = OpenAI(api_key=self.api_key) if self.api_key else OpenAI()
        oai_tools = [{"type": "function", "function": tool} for tool in tools]
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=oai_tools,
        )
        choice = response.choices[0]
        text = choice.message.content or ""
        directives = [
            _ToolCallDirective(
                name=call.function.name,
                arguments=json.loads(call.function.arguments or "{}"),
            )
            for call in (choice.message.tool_calls or [])
        ]
        return _BackendTurn(text=text, tool_calls=directives)


# ---------------------------------------------------------------------------
# Service.
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT: str = (
    "You are Healthsh's diagnostic assistant. You answer questions about the "
    "local machine using the provided tools. Always prefer reading metrics or "
    "logs over guessing. Keep responses short and reference exact values."
)


class AIService(QObject):
    """Orchestrates the agent loop and emits streaming events to the UI."""

    # Streaming events for the chat screen (#27). Payload schema:
    #   {"kind": "text", "text": "..."} → assistant text delta
    #   {"kind": "tool_call", "event": ToolCallEvent}  → chip
    event = Signal(object)

    def __init__(
        self,
        *,
        backend: Backend | None = None,
        registry: ToolRegistry | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend: Backend = backend or MockBackend(script=[_BackendTurn(text="hi")])
        self._registry: ToolRegistry = registry or ToolRegistry()
        self._history: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ API

    def set_backend(self, backend: Backend) -> None:
        """Hot-swap the backend (used by the chat screen's backend selector)."""
        self._backend = backend

    def current_backend(self) -> str:
        """Return the display name of the currently active backend."""
        return getattr(self._backend, "name", "mock")

    def registry(self) -> ToolRegistry:
        """Expose the underlying :class:`ToolRegistry`."""
        return self._registry

    def history(self) -> list[dict[str, Any]]:
        """Return the in-memory chat history (last N turns)."""
        return list(self._history)

    def reset(self) -> None:
        """Clear the chat history."""
        self._history.clear()

    def ask(self, prompt: str) -> AgentResponse:
        """Run the agent loop for a single user prompt.

        Returns once the model emits a text-only turn or :data:`MAX_TOOL_ROUNDS`
        rounds elapse. Tool calls are dispatched and their results fed back
        into the next turn. Streaming events are emitted as the loop runs.
        """
        self._history.append({"role": "user", "content": prompt})
        tool_calls: list[ToolCallEvent] = []
        text_parts: list[str] = []

        for _round in range(MAX_TOOL_ROUNDS):
            messages = self._build_messages()
            turn = self._backend.run(messages, self._registry.definitions())

            if turn.text:
                text_parts.append(turn.text)
                self._history.append({"role": "assistant", "content": turn.text})
                self.event.emit({"kind": "text", "text": turn.text})

            if not turn.tool_calls:
                break

            for directive in turn.tool_calls:
                event = self._dispatch_tool(directive)
                tool_calls.append(event)
                self.event.emit({"kind": "tool_call", "event": event})

        return AgentResponse(
            text="\n".join(t for t in text_parts if t).strip(),
            tool_calls=tuple(tool_calls),
            backend=self.current_backend(),
            model=getattr(self._backend, "model", ""),
        )

    # --------------------------------------------------------------- helpers

    def _build_messages(self) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        messages.extend(self._history)
        return messages

    def _dispatch_tool(self, directive: _ToolCallDirective) -> ToolCallEvent:
        try:
            result = self._registry.dispatch(directive.name, directive.arguments)
        except Exception as exc:  # noqa: BLE001 — surface to model + chip
            _LOG.debug("tool %s raised", directive.name, exc_info=True)
            self._history.append(
                {
                    "role": "tool",
                    "name": directive.name,
                    "content": json.dumps({"error": str(exc)}),
                }
            )
            return ToolCallEvent(
                name=directive.name,
                arguments=directive.arguments,
                result_summary=f"{directive.name} failed: {exc}",
            )
        try:
            payload = json.dumps(result, default=str)
        except (TypeError, ValueError):
            payload = json.dumps(str(result))
        self._history.append({"role": "tool", "name": directive.name, "content": payload})
        summary = self._registry.summarise(directive.name, result)
        return ToolCallEvent(
            name=directive.name,
            arguments=directive.arguments,
            result_summary=summary,
        )


def backend_from_settings(settings: Any) -> Backend:
    """Build the concrete :class:`Backend` selected by a settings snapshot.

    ``settings`` is duck-typed on the
    :class:`~healthsh.services.settings_service.Settings` field names so this
    module keeps no hard dependency on the settings layer. Empty API keys are
    passed as ``None`` so the SDKs fall back to their environment lookup.
    """
    name = getattr(settings, "ai_backend", "ollama")
    if name == "anthropic":
        return AnthropicBackend(api_key=getattr(settings, "ai_anthropic_api_key", "") or None)
    if name == "openai":
        return OpenAIBackend(api_key=getattr(settings, "ai_openai_api_key", "") or None)
    return OllamaBackend(endpoint=getattr(settings, "ai_ollama_endpoint", "http://localhost:11434"))


# ---------------------------------------------------------------------------
# Registry builder.
# ---------------------------------------------------------------------------


def build_default_registry(
    *,
    history_service: Any,
    docker_collector: Any,
    journald_collector: Any,
) -> ToolRegistry:
    """Construct a :class:`ToolRegistry` wired to the project services.

    The argument types are kept loose (Any) so this module does not pull the
    services as a hard dependency — useful in tests that swap them out.
    """
    registry = ToolRegistry()
    definitions = {tool["name"]: tool for tool in ai_tools.TOOL_DEFINITIONS}

    def _bind_metrics(**kwargs: Any) -> Any:
        return ai_tools.get_metrics(history_service, **kwargs)

    def _bind_logs(**kwargs: Any) -> Any:
        return ai_tools.get_logs(journald_collector, **kwargs)

    def _bind_containers(**_kwargs: Any) -> Any:
        return ai_tools.get_containers(docker_collector)

    def _bind_processes(**kwargs: Any) -> Any:
        return ai_tools.get_processes(**kwargs)

    registry.register(
        Tool(
            name="get_metrics",
            description=definitions["get_metrics"]["description"],
            parameters=definitions["get_metrics"]["parameters"],
            handler=_bind_metrics,
            summarise=ai_tools.summarise_metrics_result,
        )
    )
    registry.register(
        Tool(
            name="get_logs",
            description=definitions["get_logs"]["description"],
            parameters=definitions["get_logs"]["parameters"],
            handler=_bind_logs,
            summarise=ai_tools.summarise_logs_result,
        )
    )
    registry.register(
        Tool(
            name="get_containers",
            description=definitions["get_containers"]["description"],
            parameters=definitions["get_containers"]["parameters"],
            handler=_bind_containers,
            summarise=ai_tools.summarise_containers_result,
        )
    )
    registry.register(
        Tool(
            name="get_processes",
            description=definitions["get_processes"]["description"],
            parameters=definitions["get_processes"]["parameters"],
            handler=_bind_processes,
            summarise=ai_tools.summarise_processes_result,
        )
    )
    return registry
