"""Docker screen — composed cards view + per-status empty state + AI banner.

Swaps between *cards mode* and a calm informational *empty-state* mode based
on the latest :class:`DockerStatus` from the slow worker. In cards mode the
screen reconciles the container set in place (no rebuild per tick) so hover
states and scrolling survive 3 s refreshes. The AI banner sits at the bottom
with a placeholder copy that #26 will replace with real :class:`Insight`s.

Action dispatch (start / stop / restart) happens off the UI thread via
:class:`QThreadPool` — Docker calls block, and we never let them block paint.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from healthsh.domain.container import ContainerInfo, ContainerStats, DockerStatus
from healthsh.services.collector_service import CollectorService
from healthsh.ui.widgets.ai_banner import AIBanner
from healthsh.ui.widgets.container_card import ContainerCard
from healthsh.ui.widgets.docker_empty_state import DockerEmptyState

# AI banner placeholder for Sprint 3 — replaced by #26 in Sprint 5.
_DOCKER_AI_PLACEHOLDER_PREFIX: str = "Analysis:"
_DOCKER_AI_PLACEHOLDER_BODY: str = (
    "AI insights for Docker will appear here once Sprint 5 wires the agent "
    "base. Example: `postgres-dev` is using 9× the RAM of the other "
    "containers and trending up — would you like me to investigate its logs?"
)


def _running_first(items: list[ContainerInfo]) -> list[ContainerInfo]:
    """Sort: running containers first (by name), stopped containers second."""
    running = sorted([i for i in items if i.is_running], key=lambda i: i.name)
    stopped = sorted([i for i in items if not i.is_running], key=lambda i: i.name)
    return running + stopped


class _ActionRunnable(QRunnable):
    """Run a Docker action (start/stop/restart) on a thread-pool worker."""

    def __init__(self, fn, *args, on_done=None, on_error=None) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._on_done = on_done
        self._on_error = on_error

    def run(self) -> None:
        try:
            self._fn(*self._args)
        except Exception as exc:  # noqa: BLE001 — surface to UI via callback
            if self._on_error is not None:
                self._on_error(exc)
            return
        if self._on_done is not None:
            self._on_done()


class _ActionSignals(QObject):
    """QSignal bus for async Docker action callbacks."""

    finished = Signal()
    failed = Signal(str)


class DockerScreen(QWidget):
    """Top-level Docker composition with reconciliation + empty states."""

    def __init__(
        self,
        *,
        collector_service: CollectorService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._collector_service: CollectorService | None = collector_service
        self._cards: dict[str, ContainerCard] = {}
        self._latest_status: DockerStatus | None = None
        self._pool = QThreadPool.globalInstance()
        self._signals = _ActionSignals()
        self._subtitle_text: str = "containers"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        # Two-view stack: cards mode (index 0) + empty-state mode (index 1).
        self._stack = QStackedWidget()
        outer.addWidget(self._stack, stretch=1)

        # ---- Cards view.
        self._cards_view = QWidget()
        cards_layout = QVBoxLayout(self._cards_view)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(10)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll_content = QWidget()
        self._cards_layout = QVBoxLayout(self._scroll_content)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(10)
        self._cards_layout.addStretch(1)
        self._scroll.setWidget(self._scroll_content)
        cards_layout.addWidget(self._scroll, stretch=1)

        # Empty-list-when-ok hint.
        self._empty_list_label = QLabel("No containers yet — try `docker run --rm -it alpine sh`.")
        self._empty_list_label.setProperty("role", "muted")
        self._empty_list_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cards_layout.addWidget(self._empty_list_label)
        self._empty_list_label.hide()

        # AI banner (only visible in cards mode).
        self._ai_banner = AIBanner(
            prefix=_DOCKER_AI_PLACEHOLDER_PREFIX,
            body=_DOCKER_AI_PLACEHOLDER_BODY,
        )
        cards_layout.addWidget(self._ai_banner)

        self._stack.addWidget(self._cards_view)

        # ---- Empty-state view.
        self._empty_state = DockerEmptyState()
        self._empty_state.recheck_requested.connect(self._on_recheck_requested)
        self._stack.addWidget(self._empty_state)

        # Wire the collector service when injected.
        if collector_service is not None:
            collector_service.docker_ready.connect(self.on_docker)

    # ------------------------------------------------------------------ API

    def header_subtitle(self) -> str:
        """Return the muted subtitle (recomputed per docker_ready emission)."""
        return self._subtitle_text

    def on_docker(
        self,
        status: DockerStatus,
        pairs: list[tuple[ContainerInfo, ContainerStats | None]],
    ) -> None:
        """Slot for ``CollectorService.docker_ready``.

        Drives both the visual mode swap (cards vs. empty-state) and the
        in-place card reconciliation. Idempotent — calling with the same
        snapshot twice is a no-op visually.
        """
        self._latest_status = status
        self._subtitle_text = self._compute_subtitle(status, pairs)
        if status.is_ok:
            self._stack.setCurrentIndex(0)
            self._reconcile_cards(pairs)
            self._empty_list_label.setVisible(not pairs)
            self._ai_banner.setVisible(True)
        else:
            self._stack.setCurrentIndex(1)
            self._empty_state.set_status(status)
            self._empty_list_label.hide()
            self._ai_banner.setVisible(False)

    def status(self) -> DockerStatus | None:
        """Return the most recently rendered :class:`DockerStatus` (tests)."""
        return self._latest_status

    def cards(self) -> dict[str, ContainerCard]:
        """Return the live ``{id: card}`` map (tests)."""
        return dict(self._cards)

    def empty_state(self) -> DockerEmptyState:
        """Return the empty-state widget (tests)."""
        return self._empty_state

    def stack(self) -> QStackedWidget:
        """Return the inner stacked widget (tests)."""
        return self._stack

    def set_insight(self, insight) -> None:
        """Replace the AI banner content with a live :class:`Insight`."""
        self._ai_banner.set_insight(insight)

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _compute_subtitle(
        status: DockerStatus,
        pairs: list[tuple[ContainerInfo, ContainerStats | None]],
    ) -> str:
        if status.kind == "ok":
            running = sum(1 for info, _ in pairs if info.is_running)
            stopped = sum(1 for info, _ in pairs if not info.is_running)
            return f"{running} running · {stopped} stopped"
        if status.kind == "not_installed":
            return "not installed"
        if status.kind == "daemon_down":
            return "daemon stopped"
        if status.kind == "permission_denied":
            return "socket not accessible"
        return "unavailable"

    def _reconcile_cards(
        self,
        pairs: list[tuple[ContainerInfo, ContainerStats | None]],
    ) -> None:
        """Update / insert / remove cards to match ``pairs`` in place."""
        incoming = {info.id: (info, stats) for info, stats in pairs}

        # Remove cards whose containers vanished.
        for cid in list(self._cards.keys()):
            if cid not in incoming:
                card = self._cards.pop(cid)
                self._cards_layout.removeWidget(card)
                card.setParent(None)
                card.deleteLater()

        # Add or update cards.
        for info, stats in pairs:
            if info.id in self._cards:
                self._cards[info.id].update_state(info, stats)
            else:
                card = ContainerCard(info=info, stats=stats)
                card.action_requested.connect(self._on_action_requested)
                if self._collector_service is not None:
                    collector = self._collector_service.docker_collector()
                    card.set_logs_provider(lambda cid, c=collector: c.tail_logs(cid))
                self._cards[info.id] = card

        # Re-layout into running-first order without removing widgets we keep.
        layout = self._cards_layout
        # Take every widget out (the stretch is at the end).
        widgets: list[QWidget] = []
        while layout.count() > 1:
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widgets.append(widget)
        # Re-insert in the desired order.
        order = [info.id for info in _running_first([i for i, _ in pairs])]
        ordered_cards = [self._cards[cid] for cid in order if cid in self._cards]
        # Any leftovers (defensive) go after — but in normal flow there are none.
        for card in ordered_cards:
            layout.insertWidget(layout.count() - 1, card)
        # Make sure the stretch stays last.
        # Free unowned widgets (defensive — should be empty in normal flow).
        for w in widgets:
            if w not in ordered_cards:
                w.setParent(None)
                w.deleteLater()

    # ------------------------------------------------------------ slot wires

    def _on_recheck_requested(self) -> None:
        if self._collector_service is None:
            return
        self._collector_service.docker_recheck()

    def _on_action_requested(self, container_id: str, action: str) -> None:
        if self._collector_service is None:
            return
        collector = self._collector_service.docker_collector()
        method_map = {
            "start": collector.start,
            "stop": collector.stop,
            "restart": collector.restart,
            "pause": getattr(collector, "stop", lambda _id: None),  # pause maps to stop for now
        }
        fn = method_map.get(action)
        if fn is None:
            return
        runnable = _ActionRunnable(
            fn,
            container_id,
            on_done=lambda: None,
            on_error=lambda exc: self._signals.failed.emit(str(exc)),
        )
        self._pool.start(runnable)


def docker_ai_placeholder() -> tuple[str, str]:
    """Return the placeholder prefix/body the Docker AI banner ships with."""
    return _DOCKER_AI_PLACEHOLDER_PREFIX, _DOCKER_AI_PLACEHOLDER_BODY
