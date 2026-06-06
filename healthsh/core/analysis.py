"""Deterministic analysers — disk-fill forecast, leak detection, log clustering.

The engine consumes historised metric/log data and produces typed
:class:`Insight` objects. Nothing here calls an LLM: it is pure numerics and
regex. The LLM agent in #25 can use these insights as ground truth or call
them as tools.

The three analysers are:

- :func:`forecast_disk_full` — least-squares linear regression over disk
  usage history → ETA-to-full. ``numpy.polyfit`` is the workhorse.
- :func:`detect_memory_leaks` — per-process memory series with a
  monotonic-growth-plus-slope rule.
- :func:`cluster_log_errors` — collapse log messages to signatures, group by
  ``(unit, signature)``, return any cluster above the count threshold.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import numpy as np

from healthsh.core.thresholds import Thresholds
from healthsh.domain.insight import Insight
from healthsh.domain.log_entry import LogEntry

_LOG = logging.getLogger(__name__)

_BYTES_PER_GIB: int = 1024 * 1024 * 1024
_SECONDS_PER_DAY: int = 86_400
_BYTES_PER_MIB: int = 1024 * 1024

# Patterns used by the log signature normaliser. Order matters: paths first
# (so the trailing number on /var/log/x.log.5 is consumed by PATH not NUM).
_SIGNATURE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
        ),
        "<UUID>",
    ),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    (re.compile(r"\b[0-9a-fA-F]{12,}\b"), "<HEX>"),
    (re.compile(r"\b\d+\.\d+\.\d+\.\d+(?::\d+)?\b"), "<IP>"),
    # Path: starts with '/', followed by any combination of path chars. No
    # leading word boundary — paths are preceded by whitespace or punctuation,
    # both of which are word boundaries that would shift the match into the
    # middle of the path (e.g. /var → 'r/' boundary).
    (re.compile(r"/[A-Za-z0-9_\-./]+"), "<PATH>"),
    (re.compile(r"\b\d+\b"), "<NUM>"),
    (re.compile(r"\s+"), " "),
)


def _signature_for(message: str) -> str:
    """Collapse a log message to its repetition-equivalence signature."""
    text = message
    for pattern, replacement in _SIGNATURE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text.strip()


def _format_eta(seconds: float) -> str:
    """Format a positive-seconds ETA as a compact human string."""
    if seconds < 3600:
        minutes = max(int(seconds // 60), 1)
        return f"{minutes} min"
    if seconds < _SECONDS_PER_DAY:
        hours = int(seconds // 3600)
        return f"{hours}h" if hours > 1 else "1h"
    days = int(seconds // _SECONDS_PER_DAY)
    return f"{days} day{'s' if days != 1 else ''}"


def forecast_disk_full(
    history: Iterable[tuple[datetime, float]],
    *,
    disk_total_b: int,
    mountpoint: str = "/",
    thresholds: Thresholds | None = None,
    now: datetime | None = None,
) -> Insight | None:
    """Predict when the disk will be 100 % full from recent usage history.

    Args:
        history: ``(ts, used_bytes)`` pairs, any order. Returned as-is from
            :meth:`HistoryService.query("disk_used_b", ...)`.
        disk_total_b: Total disk size in bytes (the denominator of "full").
        mountpoint: Mountpoint the history was sampled at (used in the title).
        thresholds: Override the default analysis thresholds.
        now: Override the wall clock — useful for deterministic tests.

    Returns:
        An :class:`Insight` when a forecast is actionable, ``None`` otherwise
        (insufficient samples, disk shrinking, ETA beyond suppression window).
    """
    if disk_total_b <= 0:
        return None
    cfg = thresholds or Thresholds()
    points = sorted(history, key=lambda pair: pair[0])
    if len(points) < cfg.disk_forecast_min_samples:
        return None
    # Build x in seconds since the first sample (improves numpy stability).
    base_ts = points[0][0].timestamp()
    x = np.array([(ts.timestamp() - base_ts) for ts, _v in points], dtype=float)
    y = np.array([v for _ts, v in points], dtype=float)
    try:
        slope, _intercept = np.polyfit(x, y, 1)
    except (np.linalg.LinAlgError, ValueError):
        return None
    slope_bytes_per_sec = float(slope)
    if slope_bytes_per_sec <= 0:
        return None
    current_used_b = float(points[-1][1])
    remaining_b = max(disk_total_b - current_used_b, 0.0)
    if remaining_b == 0.0:
        return Insight(
            severity="critical",
            title=f"Disk on {mountpoint} is full",
            message=f"`{mountpoint}` is at 100% — clear space immediately.",
            source="disk_forecast",
            entities=(mountpoint,),
            ts=now or datetime.now(tz=UTC),
        )
    eta_seconds = remaining_b / slope_bytes_per_sec
    if eta_seconds > cfg.disk_forecast_suppress_beyond_days * _SECONDS_PER_DAY:
        return None
    eta_days = eta_seconds / _SECONDS_PER_DAY
    severity = "info"
    if eta_seconds <= cfg.disk_forecast_critical_hours * 3600:
        severity = "critical"
    elif eta_days <= cfg.disk_forecast_warning_days:
        severity = "warning"
    current_pct = current_used_b / disk_total_b * 100.0
    bytes_per_day = slope_bytes_per_sec * _SECONDS_PER_DAY
    rate_gib_per_day = bytes_per_day / _BYTES_PER_GIB
    title = f"Disk will fill in ~{_format_eta(eta_seconds)}"
    message = (
        f"`{mountpoint}` is at {current_pct:.0f}% and trending at +{rate_gib_per_day:.1f} GiB/day."
    )
    return Insight(
        severity=severity,  # type: ignore[arg-type]
        title=title,
        message=message,
        source="disk_forecast",
        entities=(mountpoint,),
        ts=now or datetime.now(tz=UTC),
    )


def detect_memory_leaks(
    samples_per_process: dict[str, list[tuple[datetime, int]]],
    *,
    thresholds: Thresholds | None = None,
    now: datetime | None = None,
) -> list[Insight]:
    """Detect monotonically-growing process memory series.

    Args:
        samples_per_process: ``name → [(ts, mem_b), ...]`` over the last
            window. The analyser requires at least ``leak_min_window_minutes``
            of coverage.
        thresholds: Optional override.
        now: Wall-clock override for tests.

    Returns:
        One :class:`Insight` per process that triggers all three rules
        (monotonic non-decrease + slope ≥ floor + growth ≥ floor).
    """
    cfg = thresholds or Thresholds()
    out: list[Insight] = []
    now_dt = now or datetime.now(tz=UTC)
    window = timedelta(minutes=cfg.leak_min_window_minutes)
    for name, points in samples_per_process.items():
        if len(points) < 2:
            continue
        sorted_points = sorted(points, key=lambda pair: pair[0])
        latest_ts = sorted_points[-1][0]
        earliest_ts = sorted_points[0][0]
        if latest_ts - earliest_ts < window:
            continue
        # Monotonic non-decreasing: every step ≥ 0 within a tiny tolerance.
        deltas = [
            sorted_points[i + 1][1] - sorted_points[i][1] for i in range(len(sorted_points) - 1)
        ]
        if any(delta < -1 * _BYTES_PER_MIB for delta in deltas):
            # Allow tiny dips; a real drop >1 MiB disqualifies the window.
            continue
        growth_b = float(sorted_points[-1][1]) - float(sorted_points[0][1])
        elapsed_minutes = (latest_ts - earliest_ts).total_seconds() / 60.0
        if elapsed_minutes <= 0:
            continue
        slope_mb_per_min = (growth_b / _BYTES_PER_MIB) / elapsed_minutes
        if slope_mb_per_min < cfg.leak_min_slope_mb_per_min:
            continue
        if growth_b / _BYTES_PER_MIB < cfg.leak_min_growth_mb:
            continue
        title = f"{name} may be leaking RAM"
        message = (
            f"`{name}` grew +{growth_b / _BYTES_PER_MIB:.0f} MB over the last "
            f"{int(elapsed_minutes)} min (+{slope_mb_per_min:.1f} MB/min). "
            "Inspect its logs?"
        )
        out.append(
            Insight(
                severity="warning",
                title=title,
                message=message,
                source="leak_detector",
                entities=(name,),
                ts=now_dt,
            )
        )
    return out


def cluster_log_errors(
    entries: Iterable[LogEntry],
    *,
    thresholds: Thresholds | None = None,
    now: datetime | None = None,
) -> list[Insight]:
    """Group repeated log entries by ``(unit, signature)`` and report large clusters.

    Only entries within the last ``log_cluster_window_minutes`` minutes are
    considered. Lower priority numbers (errors) are inspected first; the
    analyser ignores debug/info chatter to avoid false positives.
    """
    cfg = thresholds or Thresholds()
    now_dt = now or datetime.now(tz=UTC)
    window_cutoff = now_dt - timedelta(minutes=cfg.log_cluster_window_minutes)
    clusters: dict[tuple[str, str], list[LogEntry]] = defaultdict(list)
    for entry in entries:
        if entry.priority > 4:
            # Only emergency..warning are clustered (priorities 0–4).
            continue
        if entry.ts < window_cutoff:
            continue
        key = (entry.unit or "", _signature_for(entry.message))
        clusters[key].append(entry)

    insights: list[Insight] = []
    for (unit, _signature), members in clusters.items():
        if len(members) < cfg.log_cluster_min_count:
            continue
        sample = members[0].message
        window_minutes = cfg.log_cluster_window_minutes
        title = f"{len(members)} identical {unit or 'log'} entries in {window_minutes // 60 or 1}h"
        message = (
            f"`{unit or 'unknown'}` reported {len(members)} similar entries. "
            f"First occurrence: {sample}"
        )
        insights.append(
            Insight(
                severity="warning",
                title=title,
                message=message,
                source="log_cluster",
                entities=(unit,) if unit else (),
                ts=now_dt,
            )
        )
    # Most severe first — by count, descending.
    insights.sort(key=lambda i: i.message, reverse=False)
    insights.sort(key=lambda i: i.title, reverse=True)
    return insights


class AnalysisEngine:
    """Stateless façade that composes the three analysers.

    Convenience wrapper used by :class:`InsightService` in #26 — keeps the
    UI from knowing which analysers exist.
    """

    def __init__(self, *, thresholds: Thresholds | None = None) -> None:
        self._thresholds: Thresholds = thresholds or Thresholds()

    def thresholds(self) -> Thresholds:
        """Return the active threshold configuration."""
        return self._thresholds

    def forecast_disk_full(
        self,
        history: Iterable[tuple[datetime, float]],
        *,
        disk_total_b: int,
        mountpoint: str = "/",
        now: datetime | None = None,
    ) -> Insight | None:
        """Proxy to :func:`forecast_disk_full` with the engine's thresholds."""
        return forecast_disk_full(
            history,
            disk_total_b=disk_total_b,
            mountpoint=mountpoint,
            thresholds=self._thresholds,
            now=now,
        )

    def detect_memory_leaks(
        self,
        samples_per_process: dict[str, list[tuple[datetime, int]]],
        *,
        now: datetime | None = None,
    ) -> list[Insight]:
        """Proxy to :func:`detect_memory_leaks` with the engine's thresholds."""
        return detect_memory_leaks(samples_per_process, thresholds=self._thresholds, now=now)

    def cluster_log_errors(
        self,
        entries: Iterable[LogEntry],
        *,
        now: datetime | None = None,
    ) -> list[Insight]:
        """Proxy to :func:`cluster_log_errors` with the engine's thresholds."""
        return cluster_log_errors(entries, thresholds=self._thresholds, now=now)
