"""Lifecycle owner for the metric workers.

:class:`CollectorService` is the single point of contact between the UI and
the worker threads in :mod:`healthsh.infra.threads`. The Dashboard subscribes
to :pyattr:`metrics_ready` and never touches the worker directly.

For Sprint 1 only the fast metrics worker (1 s) is wired. The slow worker
(3 s, Docker + journald) will hang off the same service in Sprint 3 (#17).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from healthsh.infra.threads.metrics_worker import DEFAULT_INTERVAL_S, MetricsWorker

_LOG = logging.getLogger(__name__)

# Max seconds to wait for the worker to finish when stopping the service.
_STOP_WAIT_MS: int = 2000


class CollectorService(QObject):
    """Own + start + stop the metrics worker; re-emit its signal."""

    metrics_ready = Signal(object)  # MetricsSnapshot

    def __init__(self, *, interval_s: float = DEFAULT_INTERVAL_S, parent=None) -> None:
        super().__init__(parent)
        self._worker = MetricsWorker(interval_s=interval_s, parent=self)
        self._worker.metrics_ready.connect(self._on_metrics_ready)

    # --------------------------------------------------------------- control

    def start(self) -> None:
        """Start the metrics worker if it is not already running."""
        if self._worker.isRunning():
            return
        self._worker.start()

    def stop(self) -> None:
        """Request a cooperative stop and wait up to :data:`_STOP_WAIT_MS` ms.

        Logs a warning if the wait times out — never calls ``terminate``.
        """
        if not self._worker.isRunning():
            return
        self._worker.request_stop()
        if not self._worker.wait(_STOP_WAIT_MS):
            _LOG.warning(
                "metrics worker did not stop within %d ms; leaving it to exit",
                _STOP_WAIT_MS,
            )

    def is_running(self) -> bool:
        """Return whether the worker thread is currently executing."""
        return self._worker.isRunning()

    # ----------------------------------------------------------------- conf

    def set_interval(self, interval_s: float) -> None:
        """Update the worker tick interval (used by Settings later)."""
        self._worker.set_interval(interval_s)

    def interval_s(self) -> float:
        """Return the current worker tick interval in seconds."""
        return self._worker.interval_s()

    # ---------------------------------------------------------------- relay

    def _on_metrics_ready(self, snapshot: object) -> None:
        """Re-emit the worker signal to the public service signal."""
        self.metrics_ready.emit(snapshot)
