"""Disk usage collector via psutil."""

from __future__ import annotations

import psutil

from healthsh.domain.metrics import DiskMetric


def collect_disk(mountpoint: str = "/") -> DiskMetric:
    """Return a :class:`DiskMetric` snapshot for ``mountpoint`` (default ``/``)."""
    info = psutil.disk_usage(mountpoint)
    return DiskMetric(
        mountpoint=mountpoint,
        total_b=int(info.total),
        used_b=int(info.used),
        percent=float(info.percent),
    )
