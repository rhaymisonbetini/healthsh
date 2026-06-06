"""Persists metric snapshots to SQLite; provides time-range queries.

:class:`HistoryService` subscribes to :pyattr:`CollectorService.metrics_ready`
and writes every snapshot it sees into :class:`MetricsStore`. A daily
:class:`QTimer` runs the retention vacuum so the database stays bounded
without manual intervention.

The service is intentionally thin: queries on the database go straight
through to :class:`MetricsStore`. The analysis engine (#24) and AI tools
(#25) consume those queries directly via :meth:`HistoryService.store`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer

from healthsh.domain.metrics import MetricsSnapshot
from healthsh.infra.db.sqlite_store import MetricsStore
from healthsh.services.collector_service import CollectorService

_LOG = logging.getLogger(__name__)

# Default retention window (days).
DEFAULT_RETAIN_DAYS: int = 7

# Vacuum cadence — 24 hours.
_VACUUM_INTERVAL_MS: int = 24 * 60 * 60 * 1000


def _rows_for_snapshot(snapshot: MetricsSnapshot) -> list[tuple[str, float]]:
    """Translate a :class:`MetricsSnapshot` into a list of metric/value rows."""
    rows: list[tuple[str, float]] = []
    if snapshot.cpu is not None:
        rows.append(("cpu_pct", float(snapshot.cpu.overall_pct)))
    if snapshot.mem is not None:
        rows.append(("mem_pct", float(snapshot.mem.percent)))
        rows.append(("mem_used_b", float(snapshot.mem.used_b)))
    if snapshot.disk is not None:
        rows.append(("disk_pct", float(snapshot.disk.percent)))
        rows.append(("disk_used_b", float(snapshot.disk.used_b)))
    if snapshot.gpu is not None:
        if snapshot.gpu.util_pct is not None:
            rows.append(("gpu_pct", float(snapshot.gpu.util_pct)))
        if snapshot.gpu.temp_c is not None:
            rows.append(("gpu_temp_c", float(snapshot.gpu.temp_c)))
    return rows


class HistoryService(QObject):
    """Persists metric snapshots and exposes the underlying store for queries."""

    def __init__(
        self,
        *,
        collector_service: CollectorService | None = None,
        store: MetricsStore | None = None,
        db_path: Path | None = None,
        retain_days: int = DEFAULT_RETAIN_DAYS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store: MetricsStore = store or MetricsStore(path=db_path)
        self._collector_service: CollectorService | None = collector_service
        self._retain_days: int = retain_days
        self._started: bool = False

        self._vacuum_timer = QTimer(self)
        self._vacuum_timer.setInterval(_VACUUM_INTERVAL_MS)
        self._vacuum_timer.timeout.connect(self._run_vacuum)

    # --------------------------------------------------------------- control

    def start(self) -> None:
        """Connect to the collector signal + schedule the retention vacuum."""
        if self._started:
            return
        if self._collector_service is not None:
            self._collector_service.metrics_ready.connect(self._on_metrics_ready)
        self._vacuum_timer.start()
        self._started = True

    def stop(self) -> None:
        """Disconnect from the collector and stop the vacuum timer."""
        if not self._started:
            return
        if self._collector_service is not None:
            try:
                self._collector_service.metrics_ready.disconnect(self._on_metrics_ready)
            except (TypeError, RuntimeError):
                # disconnect raises when the signal was never connected — safe to ignore.
                _LOG.debug("metrics_ready disconnect was a no-op")
        self._vacuum_timer.stop()
        self._started = False

    def is_started(self) -> bool:
        """Return whether the service is currently subscribed to snapshots."""
        return self._started

    # ----------------------------------------------------------------- store

    def store(self) -> MetricsStore:
        """Expose the underlying :class:`MetricsStore` for analysis queries."""
        return self._store

    def insert_snapshot(self, snapshot: MetricsSnapshot) -> int:
        """Persist a single snapshot. Returns the row count inserted."""
        rows = _rows_for_snapshot(snapshot)
        inserted = self._store.insert_metrics(snapshot.ts, rows)
        if snapshot.processes_full:
            self._store.insert_processes(
                snapshot.ts,
                (
                    (proc.pid, proc.name, proc.mem_b)
                    for proc in snapshot.processes_full
                    if proc.name
                ),
            )
        return inserted

    def query(
        self,
        metric: str,
        *,
        since: datetime,
        until: datetime,
    ) -> list[tuple[datetime, float]]:
        """Proxy to :meth:`MetricsStore.query`."""
        return self._store.query(metric, since=since, until=until)

    def query_aggregate(
        self,
        metric: str,
        *,
        since: datetime,
        until: datetime,
        bucket_s: int,
    ) -> list[tuple[datetime, float]]:
        """Proxy to :meth:`MetricsStore.query_aggregate`."""
        return self._store.query_aggregate(metric, since=since, until=until, bucket_s=bucket_s)

    def query_process(
        self,
        name: str,
        *,
        since: datetime,
        until: datetime,
    ) -> list[tuple[datetime, int]]:
        """Proxy to :meth:`MetricsStore.query_process`."""
        return self._store.query_process(name, since=since, until=until)

    def vacuum_now(self) -> int:
        """Run retention vacuum immediately. Returns the row count removed."""
        return self._run_vacuum()

    # ---------------------------------------------------------------- slots

    def _on_metrics_ready(self, snapshot: MetricsSnapshot) -> None:
        try:
            self.insert_snapshot(snapshot)
        except Exception:  # noqa: BLE001 — never let an insert kill the worker
            _LOG.exception("failed to persist snapshot")

    def _run_vacuum(self) -> int:
        try:
            return self._store.vacuum_old(retain_days=self._retain_days)
        except Exception:  # noqa: BLE001
            _LOG.exception("vacuum failed")
            return 0

    # -------------------------------------------------------------- helpers

    def known_metrics(self) -> Iterable[str]:
        """Expose the canonical metric names (used by the AI tools and tests)."""
        from healthsh.infra.db.sqlite_store import KNOWN_METRICS

        return tuple(KNOWN_METRICS)
