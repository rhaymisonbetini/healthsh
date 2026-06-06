"""AI / Diagnosis chat screen — bubbles + tool-call chips + backend selector.

Composes :class:`ChatBubble`s in a scrolling vertical layout. Each assistant
turn owns one bubble that absorbs every ``text`` event during the loop and
prepends a :class:`ToolCallChip` for each ``tool_call`` event. Suggestion
chips populate the input on click; sending fires the AI service in a
``QThreadPool`` runnable so the UI never blocks on a model call.

Persistence is deliberately out of scope for v1 — the conversation lives in
memory only.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from healthsh.domain.agent import ToolCallEvent
from healthsh.services.ai_service import AIService
from healthsh.ui.theme.palette import ACCENT_BLUE, TEXT_MUTED, TEXT_PRIMARY
from healthsh.ui.widgets.backend_selector import BackendSelector
from healthsh.ui.widgets.chat_bubble import ChatBubble
from healthsh.ui.widgets.tool_call_chip import ToolCallChip

_LOG = logging.getLogger(__name__)

# Header subtitle prefix; the backend name is appended at runtime.
_SUBTITLE_PREFIX: str = "assistant · "

# Quick-suggestion chips shown in the empty state and above the input.
SUGGESTION_CHIPS: tuple[str, ...] = (
    "Why is it slow?",
    "Will the disk fill up?",
    "Any container in trouble?",
)

# Maximum number of user/assistant turns kept in the visible bubbles. Older
# bubbles fade out from the layout to keep the UI snappy.
_MAX_VISIBLE_TURNS: int = 40


# ---------------------------------------------------------------------------
# Async ask wiring (off-UI-thread).
# ---------------------------------------------------------------------------


class _AskRunnable(QRunnable):
    """Calls ``AIService.ask`` on a thread-pool worker."""

    def __init__(self, ai_service: AIService, prompt: str, signals: _AskSignals) -> None:
        super().__init__()
        self._service = ai_service
        self._prompt = prompt
        self._signals = signals

    def run(self) -> None:
        try:
            response = self._service.ask(self._prompt)
        except Exception as exc:  # noqa: BLE001 — surface to UI via signal
            _LOG.exception("AIService.ask raised")
            self._signals.failed.emit(str(exc))
            return
        self._signals.finished.emit(response.text or "")


class _AskSignals(QObject):
    finished = Signal(str)
    failed = Signal(str)


# ---------------------------------------------------------------------------
# Screen.
# ---------------------------------------------------------------------------


class AIScreen(QWidget):
    """Composed AI / Diagnosis chat screen."""

    def __init__(
        self,
        *,
        ai_service: AIService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ai_service: AIService | None = ai_service
        self._current_assistant_bubble: ChatBubble | None = None
        self._pool = QThreadPool.globalInstance()
        self._signals = _AskSignals()
        self._signals.failed.connect(self._on_ask_failed)
        self._signals.finished.connect(self._on_ask_finished)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # Backend selector row.
        backend_row = QHBoxLayout()
        backend_row.setContentsMargins(0, 0, 0, 0)
        backend_row.setSpacing(8)
        backend_row.addStretch(1)
        self._backend_selector = BackendSelector(current=self._current_backend_name())
        self._backend_selector.backend_changed.connect(self._on_backend_changed)
        backend_row.addWidget(self._backend_selector)
        outer.addLayout(backend_row)

        # QStackedWidget swap: empty state (index 0) vs. conversation (index 1).
        self._stack = QStackedWidget()
        outer.addWidget(self._stack, stretch=1)

        # Empty state.
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.setSpacing(12)
        empty_layout.addStretch(1)
        prompt_label = QLabel("Ask anything about your system.")
        prompt_label.setProperty("role", "kpi")
        prompt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(prompt_label)
        empty_layout.addWidget(
            self._build_suggestion_row(), alignment=Qt.AlignmentFlag.AlignHCenter
        )
        empty_layout.addStretch(2)
        self._stack.addWidget(empty)

        # Conversation view.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._conv_content = QWidget()
        self._conv_layout = QVBoxLayout(self._conv_content)
        self._conv_layout.setContentsMargins(0, 0, 0, 0)
        self._conv_layout.setSpacing(10)
        self._conv_layout.addStretch(1)
        self._scroll.setWidget(self._conv_content)
        self._stack.addWidget(self._scroll)

        # Input row.
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(6)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask Healthsh…")
        self._input.returnPressed.connect(self._on_send_clicked)
        input_row.addWidget(self._input, stretch=1)
        self._send_button = QPushButton("Send")
        self._send_button.setProperty("role", "primary")
        self._send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_button.clicked.connect(self._on_send_clicked)
        input_row.addWidget(self._send_button)
        outer.addLayout(input_row)

        if ai_service is not None:
            ai_service.event.connect(self._on_service_event)

        # Silence unused-token warning.
        _ = (TEXT_MUTED, TEXT_PRIMARY)

    # ------------------------------------------------------------------ API

    def header_subtitle(self) -> str:
        """Return the muted subtitle (mirrors the active backend)."""
        return f"{_SUBTITLE_PREFIX}{self._current_backend_name()}"

    def bubbles(self) -> list[ChatBubble]:
        """Return every mounted :class:`ChatBubble` (tests use this)."""
        out: list[ChatBubble] = []
        for i in range(self._conv_layout.count()):
            widget = self._conv_layout.itemAt(i).widget()
            if isinstance(widget, ChatBubble):
                out.append(widget)
        return out

    def stack(self) -> QStackedWidget:
        """Return the empty-state ↔ conversation stack (tests)."""
        return self._stack

    def send(self, prompt: str) -> None:
        """Public seam used by tests + the keyboard shortcut."""
        self._submit_prompt(prompt)

    def set_ai_service(self, ai_service: AIService) -> None:
        """Wire an :class:`AIService` after construction."""
        if self._ai_service is not None:
            try:
                self._ai_service.event.disconnect(self._on_service_event)
            except (TypeError, RuntimeError):
                _LOG.debug("event disconnect was a no-op")
        self._ai_service = ai_service
        ai_service.event.connect(self._on_service_event)
        # Only sync the selector when the backend name is one the dropdown
        # supports (the mock backend used in tests is intentionally not listed).
        from healthsh.ui.widgets.backend_selector import SUPPORTED_BACKENDS

        name = self._current_backend_name()
        if name in SUPPORTED_BACKENDS:
            self._backend_selector.set_backend(name)

    # --------------------------------------------------------------- helpers

    def _build_suggestion_row(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for prompt in SUGGESTION_CHIPS:
            chip = QPushButton(prompt)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {ACCENT_BLUE}; "
                f"border: 1px solid {ACCENT_BLUE}; border-radius: 999px; "
                "padding: 4px 12px; }"
            )
            chip.clicked.connect(lambda _checked=False, text=prompt: self._on_suggestion(text))
            layout.addWidget(chip)
        return container

    def _on_suggestion(self, text: str) -> None:
        self._input.setText(text)
        self._input.setFocus()

    def _on_send_clicked(self) -> None:
        prompt = self._input.text().strip()
        if not prompt:
            return
        self._input.clear()
        self._submit_prompt(prompt)

    def _submit_prompt(self, prompt: str) -> None:
        if self._ai_service is None:
            _LOG.debug("submit ignored: no AIService attached")
            return
        # Flip into conversation view on the first message.
        if self._stack.currentIndex() == 0:
            self._stack.setCurrentIndex(1)
        self._append_bubble(ChatBubble(role="user")).set_text(prompt)
        # New assistant bubble — events flow into it.
        self._current_assistant_bubble = self._append_bubble(ChatBubble(role="assistant"))
        self._send_button.setEnabled(False)
        runnable = _AskRunnable(self._ai_service, prompt, self._signals)
        self._pool.start(runnable)

    def _append_bubble(self, bubble: ChatBubble) -> ChatBubble:
        # Insert before the trailing stretch.
        self._conv_layout.insertWidget(self._conv_layout.count() - 1, bubble)
        # Trim old bubbles past the cap (2 widgets per turn — user + assistant).
        while self._conv_layout.count() - 1 > _MAX_VISIBLE_TURNS * 2:
            item = self._conv_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        return bubble

    def _on_service_event(self, payload: dict[str, Any]) -> None:
        if not payload or self._current_assistant_bubble is None:
            return
        kind = payload.get("kind")
        if kind == "text":
            self._current_assistant_bubble.append_text(str(payload.get("text", "")))
        elif kind == "tool_call":
            event = payload.get("event")
            if isinstance(event, ToolCallEvent):
                self._current_assistant_bubble.prepend_chip(ToolCallChip(event))

    def _on_ask_finished(self, text: str) -> None:
        if (
            self._current_assistant_bubble is not None
            and not self._current_assistant_bubble.text()
            and text
        ):
            # Fallback when the service emitted no streaming text events.
            self._current_assistant_bubble.set_text(text)
        self._current_assistant_bubble = None
        self._send_button.setEnabled(True)

    def _on_ask_failed(self, error: str) -> None:
        bubble = self._current_assistant_bubble
        if bubble is not None and not bubble.text():
            bubble.set_text(f"(agent failed: {error})")
        self._current_assistant_bubble = None
        self._send_button.setEnabled(True)

    def _on_backend_changed(self, _name: str) -> None:
        # Backend swap is wired by app.py — the selector just emits.
        pass

    def _current_backend_name(self) -> str:
        if self._ai_service is None:
            return "ollama"
        return self._ai_service.current_backend()
