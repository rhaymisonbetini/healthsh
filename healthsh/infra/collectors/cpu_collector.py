"""CPU metrics collector via psutil."""

from __future__ import annotations

import psutil

from healthsh.domain.metrics import CpuMetric


def collect_cpu() -> CpuMetric:
    """Return a :class:`CpuMetric` snapshot for the current instant.

    Uses non-blocking ``interval=None`` so the call is cheap. Per-core values
    require a prior call to seed deltas — in the metrics worker the per-core
    and aggregate samples share that history naturally.
    """
    overall = float(psutil.cpu_percent(interval=None))
    per_core = tuple(float(v) for v in psutil.cpu_percent(interval=None, percpu=True))

    physical = psutil.cpu_count(logical=False) or 0
    logical = psutil.cpu_count(logical=True) or 0

    freq = psutil.cpu_freq()
    freq_mhz: float | None = float(freq.current) if freq is not None else None

    return CpuMetric(
        overall_pct=overall,
        per_core_pct=per_core,
        physical_cores=physical,
        logical_cores=logical,
        freq_mhz=freq_mhz,
    )
