"""Domain entity invariants for the metric value objects."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from healthsh.domain.metrics import (
    CpuMetric,
    DiskMetric,
    GpuMetric,
    MemMetric,
    MetricsSnapshot,
)


def test_cpu_metric_is_frozen() -> None:
    m = CpuMetric(1.0, (1.0, 2.0), 4, 8, 3200.0)
    with pytest.raises(FrozenInstanceError):
        m.overall_pct = 99.0  # type: ignore[misc]


def test_mem_metric_is_frozen() -> None:
    m = MemMetric(1, 0, 0.0)
    with pytest.raises(FrozenInstanceError):
        m.percent = 100.0  # type: ignore[misc]


def test_disk_metric_is_frozen() -> None:
    m = DiskMetric("/", 1, 0, 0.0)
    with pytest.raises(FrozenInstanceError):
        m.mountpoint = "/var"  # type: ignore[misc]


def test_gpu_metric_is_frozen() -> None:
    m = GpuMetric("nvidia", "RTX 4070", None, None, None, None)
    with pytest.raises(FrozenInstanceError):
        m.name = "something else"  # type: ignore[misc]


def test_snapshot_is_frozen_and_allows_none_fields() -> None:
    snap = MetricsSnapshot(cpu=None, mem=None, disk=None, gpu=None, ts=datetime.now(tz=UTC))
    with pytest.raises(FrozenInstanceError):
        snap.cpu = CpuMetric(0.0, (), 0, 0, None)  # type: ignore[misc]
