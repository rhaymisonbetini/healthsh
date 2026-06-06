"""``InsightService`` — periodic deterministic insight generation per screen.

The service runs every :data:`DEFAULT_TICK_S` seconds (30 s by default — the
*banner* doesn't need to flicker at 1 Hz), asks :class:`AnalysisEngine` for
current insights, picks the most-relevant one for each target screen and
emits :pyattr:`insight_for` so screens can update their banners.

Screens never call the analysers themselves — they subscribe to the per-target
signal and treat the payload as opaque data.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal

from healthsh.core.analysis import AnalysisEngine
from healthsh.domain.container import ContainerStats
from healthsh.domain.insight import Insight, InsightTarget
from healthsh.domain.log_entry import LogEntry
from healthsh.services.history_service import HistoryService

_LOG = logging.getLogger(__name__)

# Default tick cadence (seconds).
DEFAULT_TICK_S: int = 30

# Disk-history window the forecast looks back over.
_DISK_HISTORY_HOURS: int = 24

# Process-memory window the leak detector looks back over.
_LEAK_HISTORY_MINUTES: int = 30


class InsightService(QObject):
    """Periodic insight generator with per-target Qt signals."""

    # Payload is an :class:`Insight` or ``None`` ("All looks healthy").
    insight_for_dashboard = Signal(object)
    insight_for_docker = Signal(object)
    insight_for_logs = Signal(object)

    def __init__(
        self,
        *,
        history_service: HistoryService,
        engine: AnalysisEngine | None = None,
        tick_s: int = DEFAULT_TICK_S,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if tick_s <= 0:
            raise ValueError(f"tick_s must be positive, got {tick_s!r}")
        self._history: HistoryService = history_service
        self._engine: AnalysisEngine = engine or AnalysisEngine()
        self._tick_s: int = int(tick_s)
        self._log_buffer: list[LogEntry] = []
        self._container_stats: dict[str, ContainerStats | None] = {}
        # Caches of the last value emitted per target — used by replay()
        # when a screen subscribes mid-run.
        self._last_for: dict[InsightTarget, Insight | None] = {
            "dashboard": None,
            "docker": None,
            "logs": None,
        }
        self._timer = QTimer(self)
        self._timer.setInterval(self._tick_s * 1000)
        self._timer.timeout.connect(self.tick)

    # ------------------------------------------------------------------ API

    def start(self) -> None:
        """Begin ticking. First tick fires immediately so banners populate fast."""
        if self._timer.isActive():
            return
        self._timer.start()
        self.tick()

    def stop(self) -> None:
        """Stop ticking; cached values stay until the next start."""
        self._timer.stop()

    def tick_s(self) -> int:
        """Return the tick interval (seconds)."""
        return self._tick_s

    def push_logs(self, entries: Iterable[LogEntry]) -> None:
        """Buffer the latest log batch (called by the Logs screen / collector)."""
        for entry in entries:
            self._log_buffer.append(entry)
        # Keep the buffer bounded — we only need the last clustering window.
        cutoff = datetime.now(tz=UTC) - timedelta(minutes=60 * 4)
        self._log_buffer = [e for e in self._log_buffer if e.ts >= cutoff]

    def push_container_stats(
        self,
        pairs: Iterable[tuple[str, ContainerStats | None]],
    ) -> None:
        """Buffer the latest ``(container_name, stats)`` pairs for outlier detection."""
        for name, stats in pairs:
            if name:
                self._container_stats[name] = stats

    def last(self, target: InsightTarget) -> Insight | None:
        """Return the most-recent insight emitted for ``target``."""
        return self._last_for[target]

    def tick(self) -> None:
        """Run analysers and emit per-target signals (idempotent)."""
        try:
            dashboard = self._insight_for_dashboard()
            docker = self._insight_for_docker()
            logs = self._insight_for_logs()
        except Exception:  # noqa: BLE001 — never let analysis kill the timer
            _LOG.exception("insight tick failed")
            return
        self._last_for["dashboard"] = dashboard
        self._last_for["docker"] = docker
        self._last_for["logs"] = logs
        self.insight_for_dashboard.emit(dashboard)
        self.insight_for_docker.emit(docker)
        self.insight_for_logs.emit(logs)

    # --------------------------------------------------------------- helpers

    def _insight_for_dashboard(self) -> Insight | None:
        candidates: list[Insight] = []
        forecast = self._disk_forecast()
        if forecast is not None:
            candidates.append(forecast)
        leaks = self._leak_insights()
        candidates.extend(leaks)
        return _pick_most_severe(candidates)

    def _insight_for_docker(self) -> Insight | None:
        # Outlier container = the one whose mem_used is at least 3× the median.
        running_pairs = [
            (name, stats)
            for name, stats in self._container_stats.items()
            if stats is not None and stats.mem_used_b > 0
        ]
        if len(running_pairs) < 2:
            return None
        sorted_pairs = sorted(running_pairs, key=lambda kv: kv[1].mem_used_b)
        median = sorted_pairs[len(sorted_pairs) // 2][1].mem_used_b
        top_name, top_stats = sorted_pairs[-1]
        if median <= 0 or top_stats.mem_used_b < median * 3:
            return None
        title = f"{top_name} is consuming far more RAM than the others"
        message = (
            f"`{top_name}` is using {top_stats.mem_used_b / (1024**3):.1f} GiB — "
            f"~{int(top_stats.mem_used_b / median)}× the median container."
        )
        return Insight(
            severity="warning",
            title=title,
            message=message,
            source="container_outlier",
            entities=(top_name,),
        )

    def _insight_for_logs(self) -> Insight | None:
        if not self._log_buffer:
            return None
        clusters = self._engine.cluster_log_errors(self._log_buffer)
        return _pick_most_severe(clusters)

    def _disk_forecast(self) -> Insight | None:
        now = datetime.now(tz=UTC)
        since = now - timedelta(hours=_DISK_HISTORY_HOURS)
        rows = self._history.query("disk_used_b", since=since, until=now)
        if not rows:
            return None
        # We don't have disk_total_b in history; ask the history service for it.
        disk_total_b = self._latest_disk_total_b() or 0
        if disk_total_b <= 0:
            return None
        return self._engine.forecast_disk_full(
            rows,
            disk_total_b=disk_total_b,
            mountpoint="/",
            now=now,
        )

    def _latest_disk_total_b(self) -> int | None:
        """Read the most-recent ``disk_used_b`` and ``disk_pct`` to derive total.

        ``total ≈ used / (pct / 100)``. Slight rounding error is fine — we only
        use it as the denominator for the forecast.
        """
        now = datetime.now(tz=UTC)
        since = now - timedelta(minutes=10)
        used_rows = self._history.query("disk_used_b", since=since, until=now)
        pct_rows = self._history.query("disk_pct", since=since, until=now)
        if not used_rows or not pct_rows:
            return None
        used_b = used_rows[-1][1]
        pct = pct_rows[-1][1]
        if pct <= 0.0:
            return None
        return int(used_b / (pct / 100.0))

    def _leak_insights(self) -> list[Insight]:
        now = datetime.now(tz=UTC)
        since = now - timedelta(minutes=_LEAK_HISTORY_MINUTES)
        # Walk the unique process names in the recent history.
        names = self._recent_process_names(since, now)
        if not names:
            return []
        per_process: dict[str, list[tuple[datetime, int]]] = {}
        for name in names:
            rows = self._history.query_process(name, since=since, until=now)
            if len(rows) >= 2:
                per_process[name] = list(rows)
        return self._engine.detect_memory_leaks(per_process, now=now)

    def _recent_process_names(self, since: datetime, until: datetime) -> list[str]:
        # The store has no dedicated "list names" query; this is a one-call
        # scan over the recent window which is small enough.
        with self._history.store()._lock:  # type: ignore[attr-defined]
            cur = self._history.store()._conn.execute(  # type: ignore[attr-defined]
                "SELECT DISTINCT name FROM process_samples WHERE ts >= ? AND ts <= ?",
                (int(since.timestamp()), int(until.timestamp())),
            )
            rows = cur.fetchall()
        return [row[0] for row in rows if row[0]]


def _pick_most_severe(insights: Iterable[Insight]) -> Insight | None:
    """Return the most-severe insight (critical > warning > info), or None."""
    rank = {"critical": 0, "warning": 1, "info": 2}
    best: Insight | None = None
    best_rank = 99
    for insight in insights:
        r = rank.get(insight.severity, 99)
        if r < best_rank:
            best = insight
            best_rank = r
    return best
