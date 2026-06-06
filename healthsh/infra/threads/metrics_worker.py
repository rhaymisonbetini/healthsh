"""Fast metrics worker — collects CPU / RAM / disk / GPU on a 1 s cadence.

The worker runs in its own :class:`QThread` and emits
:pyattr:`MetricsWorker.metrics_ready` with a :class:`MetricsSnapshot` on every
tick. Each collector is wrapped in its own ``try`` so a transient failure in
one subsystem yields a ``None`` field rather than killing the worker.

Stopping is cooperative: :meth:`request_stop` sets a
:class:`threading.Event` that :meth:`run` polls via ``wait(timeout)`` — this
makes the loop interruptible without resorting to ``QThread.terminate``.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from PySide6.QtCore import QThread, Signal

from healthsh.domain.metrics import (
    CpuMetric,
    DiskMetric,
    GpuMetric,
    MemMetric,
    MetricsSnapshot,
    SystemMetric,
)
from healthsh.infra.collectors.cpu_collector import collect_cpu
from healthsh.infra.collectors.disk_collector import collect_disk
from healthsh.infra.collectors.gpu.detect import collect_gpu
from healthsh.infra.collectors.mem_collector import collect_mem
from healthsh.infra.collectors.system_collector import collect_system

_LOG = logging.getLogger(__name__)

# Default cadence (seconds). Settings (#28) will be allowed to override at
# runtime via :meth:`set_interval`.
DEFAULT_INTERVAL_S: float = 1.0


def _safe_call(name: str, fn):
    """Invoke ``fn`` and return its result, logging + swallowing exceptions."""
    try:
        return fn()
    except Exception:  # noqa: BLE001 — never let a collector kill the worker
        _LOG.debug("collector %s raised; emitting None this tick", name, exc_info=True)
        return None


class MetricsWorker(QThread):
    """1 Hz QThread emitting :class:`MetricsSnapshot` on each tick."""

    metrics_ready = Signal(object)  # MetricsSnapshot

    def __init__(self, *, interval_s: float = DEFAULT_INTERVAL_S, parent=None) -> None:
        super().__init__(parent)
        if interval_s <= 0:
            raise ValueError(f"interval_s must be positive, got {interval_s!r}")
        self._interval_s: float = float(interval_s)
        self._stop_event: threading.Event = threading.Event()

    # ------------------------------------------------------------------ API

    def start(self, *args, **kwargs) -> None:  # type: ignore[override]
        """Clear the stop event then start the underlying QThread.

        Clearing happens on the calling thread *before* ``QThread.start`` so a
        ``request_stop`` racing in immediately after ``start`` is not erased
        by the run-loop's own initialisation.
        """
        self._stop_event.clear()
        super().start(*args, **kwargs)

    def request_stop(self) -> None:
        """Signal the run loop to exit at its next wake. Safe to call from any thread."""
        self._stop_event.set()

    def set_interval(self, interval_s: float) -> None:
        """Update the tick interval (seconds). Takes effect on the next sleep."""
        if interval_s <= 0:
            raise ValueError(f"interval_s must be positive, got {interval_s!r}")
        self._interval_s = float(interval_s)

    def interval_s(self) -> float:
        """Return the currently-configured tick interval in seconds."""
        return self._interval_s

    # --------------------------------------------------------------- runtime

    def run(self) -> None:  # noqa: D401 — Qt callback name
        """Worker entry point — emits a snapshot every ``interval_s`` until stopped.

        The stop event is cleared by :meth:`start`, so do **not** clear it here:
        a race between ``request_stop`` and the actual ``run`` entry on the
        worker thread would otherwise swallow the stop request.
        """
        while not self._stop_event.is_set():
            snapshot = self._collect_once()
            self.metrics_ready.emit(snapshot)
            # ``wait`` returns True if the event was set during the wait — that
            # is the cooperative-cancel signal; either way we re-check the
            # condition at the top of the loop.
            self._stop_event.wait(self._interval_s)

    def _collect_once(self) -> MetricsSnapshot:
        """Run every collector with isolation and pack a :class:`MetricsSnapshot`."""
        cpu: CpuMetric | None = _safe_call("cpu", collect_cpu)
        mem: MemMetric | None = _safe_call("mem", collect_mem)
        disk: DiskMetric | None = _safe_call("disk", collect_disk)
        gpu: GpuMetric | None = _safe_call("gpu", collect_gpu)
        system: SystemMetric | None = _safe_call("system", collect_system)
        return MetricsSnapshot(
            cpu=cpu,
            mem=mem,
            disk=disk,
            gpu=gpu,
            ts=datetime.now(tz=UTC),
            system=system,
        )
