"""Tunable thresholds for the analysis engine.

Defaults live as module-level constants for direct import; :class:`Thresholds`
groups them so Settings (Sprint 6 / #28) can pass a single override object
without touching every analyser signature.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Disk fill forecast (#24 — disk-fill ETA insight).
# ---------------------------------------------------------------------------
DISK_FORECAST_WARNING_DAYS: float = 7.0
DISK_FORECAST_CRITICAL_HOURS: float = 24.0
DISK_FORECAST_SUPPRESS_BEYOND_DAYS: float = 30.0
DISK_USED_PCT_CRITICAL: float = 90.0
# Minimum number of samples required before we trust the linear fit.
DISK_FORECAST_MIN_SAMPLES: int = 30

# ---------------------------------------------------------------------------
# Memory-leak detection.
# ---------------------------------------------------------------------------
LEAK_MIN_WINDOW_MINUTES: int = 10
LEAK_MIN_SLOPE_MB_PER_MIN: float = 5.0
LEAK_MIN_GROWTH_MB: float = 50.0

# ---------------------------------------------------------------------------
# Log clustering.
# ---------------------------------------------------------------------------
LOG_CLUSTER_MIN_COUNT: int = 5
LOG_CLUSTER_WINDOW_MINUTES: int = 120


@dataclass
class Thresholds:
    """All configurable thresholds in one place.

    Defaults mirror the module-level constants so a freshly-constructed
    :class:`Thresholds` is the baseline analysis configuration. Settings
    persistence (Sprint 6) materialises overrides into this dataclass.
    """

    disk_forecast_warning_days: float = DISK_FORECAST_WARNING_DAYS
    disk_forecast_critical_hours: float = DISK_FORECAST_CRITICAL_HOURS
    disk_forecast_suppress_beyond_days: float = DISK_FORECAST_SUPPRESS_BEYOND_DAYS
    disk_used_pct_critical: float = DISK_USED_PCT_CRITICAL
    disk_forecast_min_samples: int = DISK_FORECAST_MIN_SAMPLES

    leak_min_window_minutes: int = LEAK_MIN_WINDOW_MINUTES
    leak_min_slope_mb_per_min: float = LEAK_MIN_SLOPE_MB_PER_MIN
    leak_min_growth_mb: float = LEAK_MIN_GROWTH_MB

    log_cluster_min_count: int = LOG_CLUSTER_MIN_COUNT
    log_cluster_window_minutes: int = LOG_CLUSTER_WINDOW_MINUTES
