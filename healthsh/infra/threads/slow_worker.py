"""Slow worker — Docker (and later journald) on a 3 s cadence.

The worker shares the cooperative-stop pattern of the fast metrics worker:
:meth:`request_stop` flips a flag and wakes the run loop so we never call
``QThread.terminate``. :meth:`request_recheck` uses the same wake mechanism
to force the *next* tick to fire immediately instead of after the full
interval — used by the Docker screen's "Re-check now" button.

Per-tick work is best-effort: a single failure inside the Docker collector
flips the typed :class:`DockerStatus` and is emitted as such — no exception
ever leaves the worker and kills the thread.
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QThread, Signal

from healthsh.domain.container import ContainerInfo, ContainerStats, DockerStatus
from healthsh.infra.collectors.docker_collector import DockerCollector

_LOG = logging.getLogger(__name__)

# Default cadence (seconds). Slow worker ticks every 3 s per the roadmap.
DEFAULT_INTERVAL_S: float = 3.0


class SlowWorker(QThread):
    """3 Hz QThread emitting ``docker_ready`` on each tick."""

    # (DockerStatus, list[tuple[ContainerInfo, ContainerStats | None]])
    docker_ready = Signal(object, object)

    def __init__(
        self,
        *,
        docker_collector: DockerCollector | None = None,
        interval_s: float = DEFAULT_INTERVAL_S,
        parent=None,
    ) -> None:
        super().__init__(parent)
        if interval_s <= 0:
            raise ValueError(f"interval_s must be positive, got {interval_s!r}")
        self._interval_s: float = float(interval_s)
        # Single wake event — both stop and recheck wake the loop. The flags
        # below tell the loop *why* it woke up.
        self._wake: threading.Event = threading.Event()
        self._stop_requested: bool = False
        self._recheck_requested: bool = False
        self._docker: DockerCollector = docker_collector or DockerCollector()

    # ------------------------------------------------------------------ API

    def start(self, *args, **kwargs) -> None:  # type: ignore[override]
        """Reset the wake state then start the underlying QThread.

        Reset happens on the calling thread *before* ``QThread.start`` so a
        stop request racing in immediately after start is not erased by the
        run-loop's own initialisation.
        """
        self._stop_requested = False
        self._recheck_requested = False
        self._wake.clear()
        super().start(*args, **kwargs)

    def request_stop(self) -> None:
        """Signal the run loop to exit at its next wake. Safe from any thread."""
        self._stop_requested = True
        self._wake.set()

    def request_recheck(self) -> None:
        """Force the next iteration to re-probe Docker without waiting a tick."""
        self._recheck_requested = True
        self._wake.set()

    def docker_collector(self) -> DockerCollector:
        """Expose the docker collector (used by the service for actions)."""
        return self._docker

    def set_interval(self, interval_s: float) -> None:
        """Update the tick interval (takes effect on the next sleep)."""
        if interval_s <= 0:
            raise ValueError(f"interval_s must be positive, got {interval_s!r}")
        self._interval_s = float(interval_s)

    def interval_s(self) -> float:
        """Return the currently-configured tick interval (seconds)."""
        return self._interval_s

    # --------------------------------------------------------------- runtime

    def run(self) -> None:  # noqa: D401 — Qt callback name
        """Emit a Docker snapshot every ``interval_s`` until stopped."""
        while not self._stop_requested:
            self._emit_once()
            if self._stop_requested:
                return
            # Block until either the interval elapses or someone wakes us.
            self._wake.wait(self._interval_s)
            self._wake.clear()
            if self._recheck_requested:
                # A recheck request fast-forwards to the next emission.
                self._recheck_requested = False

    def _emit_once(self) -> None:
        try:
            status, infos = self._docker.list_containers()
            pairs: list[tuple[ContainerInfo, ContainerStats | None]] = (
                self._docker.stats_pairs(infos) if status.is_ok else [(i, None) for i in infos]
            )
        except Exception as exc:  # noqa: BLE001 — never let the worker crash
            _LOG.exception("docker tick failed; emitting unknown status")
            status = DockerStatus(kind="unknown", detail=str(exc))
            pairs = []
        self.docker_ready.emit(status, pairs)
