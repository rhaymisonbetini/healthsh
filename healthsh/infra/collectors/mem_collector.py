"""Memory metrics collector via psutil."""

from __future__ import annotations

import psutil

from healthsh.domain.metrics import MemMetric


def collect_mem() -> MemMetric:
    """Return a :class:`MemMetric` snapshot of virtual memory usage."""
    info = psutil.virtual_memory()
    return MemMetric(
        total_b=int(info.total),
        used_b=int(info.used),
        percent=float(info.percent),
    )
