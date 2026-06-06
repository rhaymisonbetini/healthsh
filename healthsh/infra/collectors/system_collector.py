"""System-level metric collector: temps + swap + load + uptime.

Per-core CPU utilisation already lives on :class:`CpuMetric` (populated by
:func:`healthsh.infra.collectors.cpu_collector.collect_cpu`); this aggregator
adds the cross-cutting system metrics consumed by the System / Processes
screen (#16).

The collector is best-effort: missing sensors yield empty temps, a missing
``os.getloadavg`` (Windows-only edge case) yields zeros — never an exception.
"""

from __future__ import annotations

import logging
import os
import time

import psutil

from healthsh.domain.metrics import LoadAverage, SwapMetric, SystemMetric, TempReading
from healthsh.infra.collectors.temp_collector import collect_temps

_LOG = logging.getLogger(__name__)


def _collect_swap() -> SwapMetric:
    """Return current swap usage (``total_b`` / ``used_b``).

    Falls back to zeros on systems without swap or when psutil rejects the call.
    """
    try:
        info = psutil.swap_memory()
    except Exception:  # noqa: BLE001 — swap is optional
        _LOG.debug("swap_memory raised; reporting zeros", exc_info=True)
        return SwapMetric(total_b=0, used_b=0)
    return SwapMetric(total_b=int(info.total), used_b=int(info.used))


def _collect_load() -> LoadAverage:
    """Return the (1, 5, 15)-minute load averages, or zeros if unavailable."""
    getloadavg = getattr(os, "getloadavg", None)
    if getloadavg is None:
        return LoadAverage(one=0.0, five=0.0, fifteen=0.0)
    try:
        one, five, fifteen = getloadavg()
    except OSError:
        _LOG.debug("os.getloadavg raised; reporting zeros", exc_info=True)
        return LoadAverage(one=0.0, five=0.0, fifteen=0.0)
    return LoadAverage(one=float(one), five=float(five), fifteen=float(fifteen))


def _collect_uptime() -> int:
    """Return seconds since boot, clamped at 0 (never negative)."""
    try:
        boot = psutil.boot_time()
    except Exception:  # noqa: BLE001 — fall back to "just booted"
        _LOG.debug("psutil.boot_time raised; reporting 0 uptime", exc_info=True)
        return 0
    delta = int(time.time() - float(boot))
    return max(delta, 0)


def _temps_as_readings(temps: dict[str, float]) -> tuple[TempReading, ...]:
    """Convert the collector's dict into the immutable domain tuple form."""
    return tuple(TempReading(sensor=name, value_c=value) for name, value in sorted(temps.items()))


def collect_system() -> SystemMetric:
    """Return a single :class:`SystemMetric` snapshot for the current instant.

    Aggregates :func:`collect_temps`, swap memory, load average and uptime.
    Per-core CPU utilisation is intentionally not duplicated here — it travels
    on the :class:`CpuMetric` field of :class:`MetricsSnapshot`.
    """
    return SystemMetric(
        temps=_temps_as_readings(collect_temps()),
        swap=_collect_swap(),
        load=_collect_load(),
        uptime_s=_collect_uptime(),
    )
