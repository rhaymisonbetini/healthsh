"""Metric value objects.

These are pure data — no I/O, no Qt, no psutil. Collectors in
:mod:`healthsh.infra.collectors` produce them and the UI and analysis layers
consume them.

All entities are ``frozen=True`` so they can be passed across threads and used
as cache keys safely.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

GpuVendor = Literal["nvidia", "amd", "intel"]


@dataclass(frozen=True)
class CpuMetric:
    """Aggregate CPU metric snapshot."""

    overall_pct: float
    per_core_pct: tuple[float, ...]
    physical_cores: int
    logical_cores: int
    freq_mhz: float | None


@dataclass(frozen=True)
class MemMetric:
    """Virtual memory snapshot."""

    total_b: int
    used_b: int
    percent: float


@dataclass(frozen=True)
class DiskMetric:
    """Disk usage snapshot for a single mountpoint."""

    mountpoint: str
    total_b: int
    used_b: int
    percent: float


@dataclass(frozen=True)
class GpuMetric:
    """GPU snapshot, vendor-agnostic.

    Fields the underlying hardware cannot report (for example, VRAM and
    temperature on Intel integrated GPUs) are ``None``. The UI must hide the
    GPU section entirely when :func:`healthsh.infra.collectors.gpu.detect.collect_gpu`
    returns ``None`` — never display "n/a" placeholders.
    """

    vendor: GpuVendor
    name: str
    util_pct: float | None
    mem_used_b: int | None
    mem_total_b: int | None
    temp_c: float | None


@dataclass(frozen=True)
class MetricsSnapshot:
    """All metrics gathered in a single tick of the metrics worker.

    Any individual field may be ``None`` when its collector failed transiently;
    the worker keeps running and emits whatever it could capture.
    """

    cpu: CpuMetric | None
    mem: MemMetric | None
    disk: DiskMetric | None
    gpu: GpuMetric | None
    ts: datetime
