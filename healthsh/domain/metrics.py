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
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    # Forward-only reference so the snapshot annotation stays meaningful for
    # type-checkers without a runtime cross-import between domain modules
    # (the CLAUDE.md rule). The default value is an empty tuple so no caller
    # needs ProcessInfo to construct a snapshot.
    from healthsh.domain.process import ProcessInfo

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
class TempReading:
    """A single temperature sensor reading in Celsius.

    ``sensor`` is the friendly chip label psutil reports (``coretemp``,
    ``k10temp``, ``acpitz``, ``nvme``…); ``value_c`` is the most representative
    current reading for that chip (usually the package or composite value).
    """

    sensor: str
    value_c: float


@dataclass(frozen=True)
class SwapMetric:
    """Swap usage snapshot (bytes)."""

    total_b: int
    used_b: int


@dataclass(frozen=True)
class LoadAverage:
    """``os.getloadavg()`` triple kept as a typed value object."""

    one: float
    five: float
    fifteen: float


@dataclass(frozen=True)
class SystemMetric:
    """System-level snapshot consumed by the System / Processes screen.

    ``temps`` is an empty tuple on hardware (and most VMs) that exposes no
    sensors — callers should never treat absence as an error.

    Per-core CPU utilisation lives on :class:`CpuMetric` (already populated by
    :func:`healthsh.infra.collectors.cpu_collector.collect_cpu`); this entity
    only carries the *system-wide* extras (sensors, swap, load, uptime).
    """

    temps: tuple[TempReading, ...]
    swap: SwapMetric
    load: LoadAverage
    uptime_s: int


@dataclass(frozen=True)
class MetricsSnapshot:
    """All metrics gathered in a single tick of the metrics worker.

    Any individual field may be ``None`` when its collector failed transiently;
    the worker keeps running and emits whatever it could capture.

    ``processes_full`` is the unsorted list of every visible process, populated
    by the System / Processes screen wiring in #16 and otherwise an empty tuple
    so screens that do not need it pay no cost.
    """

    cpu: CpuMetric | None
    mem: MemMetric | None
    disk: DiskMetric | None
    gpu: GpuMetric | None
    ts: datetime
    system: SystemMetric | None = None
    processes_full: tuple[ProcessInfo, ...] = ()
