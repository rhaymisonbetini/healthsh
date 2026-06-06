"""Lifecycle owner for the metric workers.

:class:`CollectorService` is the single point of contact between the UI and
the worker threads in :mod:`healthsh.infra.threads`. The Dashboard subscribes
to :pyattr:`metrics_ready` and never touches the worker directly; the Docker
screen subscribes to :pyattr:`docker_ready` for the typed
:class:`DockerStatus` + container list pair.

Sprint 1 wired the fast metrics worker (1 s); Sprint 3 wires the slow worker
(3 s) for Docker. The journald worker share will hang off the same service in
Sprint 4 (#20).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from healthsh.infra.collectors.docker_collector import DockerCollector
from healthsh.infra.collectors.journald_collector import JournaldCollector
from healthsh.infra.threads.metrics_worker import DEFAULT_INTERVAL_S, MetricsWorker
from healthsh.infra.threads.slow_worker import DEFAULT_INTERVAL_S as SLOW_INTERVAL_S
from healthsh.infra.threads.slow_worker import SlowWorker

_LOG = logging.getLogger(__name__)

# Max seconds to wait for a worker to finish when stopping the service.
_STOP_WAIT_MS: int = 2000


class CollectorService(QObject):
    """Own + start + stop the metric workers; re-emit their signals."""

    metrics_ready = Signal(object)  # MetricsSnapshot
    docker_ready = Signal(
        object, object
    )  # DockerStatus, list[(ContainerInfo, ContainerStats|None)]
    journal_ready = Signal(object)  # list[LogEntry]

    def __init__(
        self,
        *,
        interval_s: float = DEFAULT_INTERVAL_S,
        slow_interval_s: float = SLOW_INTERVAL_S,
        docker_collector: DockerCollector | None = None,
        journald_collector: JournaldCollector | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._worker = MetricsWorker(interval_s=interval_s, parent=self)
        self._worker.metrics_ready.connect(self._on_metrics_ready)

        self._slow_worker = SlowWorker(
            docker_collector=docker_collector,
            journald_collector=journald_collector,
            interval_s=slow_interval_s,
            parent=self,
        )
        self._slow_worker.docker_ready.connect(self._on_docker_ready)
        self._slow_worker.journal_ready.connect(self._on_journal_ready)

    # --------------------------------------------------------------- control

    def start(self) -> None:
        """Start both workers if they are not already running."""
        if not self._worker.isRunning():
            self._worker.start()
        if not self._slow_worker.isRunning():
            self._slow_worker.start()

    def stop(self) -> None:
        """Request a cooperative stop on both workers and wait up to 2 s each."""
        self._stop_worker(self._worker, "metrics")
        self._stop_worker(self._slow_worker, "slow")

    @staticmethod
    def _stop_worker(worker, label: str) -> None:
        if not worker.isRunning():
            return
        worker.request_stop()
        if not worker.wait(_STOP_WAIT_MS):
            _LOG.warning(
                "%s worker did not stop within %d ms; leaving it to exit",
                label,
                _STOP_WAIT_MS,
            )

    def is_running(self) -> bool:
        """Return whether the metrics worker thread is currently executing."""
        return self._worker.isRunning()

    def is_slow_running(self) -> bool:
        """Return whether the slow worker thread is currently executing."""
        return self._slow_worker.isRunning()

    # ----------------------------------------------------------------- conf

    def set_interval(self, interval_s: float) -> None:
        """Update the metrics worker tick interval (used by Settings later)."""
        self._worker.set_interval(interval_s)

    def interval_s(self) -> float:
        """Return the current metrics worker tick interval in seconds."""
        return self._worker.interval_s()

    def set_slow_interval(self, interval_s: float) -> None:
        """Update the slow worker tick interval."""
        self._slow_worker.set_interval(interval_s)

    def slow_interval_s(self) -> float:
        """Return the current slow worker tick interval."""
        return self._slow_worker.interval_s()

    # ----------------------------------------------------------------- docker

    def docker_collector(self) -> DockerCollector:
        """Expose the Docker collector (used by the screen for container actions)."""
        return self._slow_worker.docker_collector()

    def docker_recheck(self) -> None:
        """Force the slow worker to re-probe Docker on its next iteration."""
        self._slow_worker.request_recheck()

    def journald_collector(self) -> JournaldCollector:
        """Expose the journald collector (used by tests / the analysis layer)."""
        return self._slow_worker.journald_collector()

    # ---------------------------------------------------------------- relay

    def _on_metrics_ready(self, snapshot: object) -> None:
        """Re-emit the worker signal to the public service signal."""
        self.metrics_ready.emit(snapshot)

    def _on_docker_ready(self, status: object, pairs: object) -> None:
        """Re-emit the Docker snapshot from the slow worker."""
        self.docker_ready.emit(status, pairs)

    def _on_journal_ready(self, entries: object) -> None:
        """Re-emit the journald batch from the slow worker."""
        self.journal_ready.emit(entries)
