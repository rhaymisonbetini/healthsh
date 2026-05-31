"""Smoke tests for CPU / mem / disk collectors on a real machine."""

from __future__ import annotations

import psutil

from healthsh.domain.metrics import CpuMetric, DiskMetric, MemMetric
from healthsh.infra.collectors.cpu_collector import collect_cpu
from healthsh.infra.collectors.disk_collector import collect_disk
from healthsh.infra.collectors.mem_collector import collect_mem


def test_collect_cpu_returns_typed_metric() -> None:
    metric = collect_cpu()
    assert isinstance(metric, CpuMetric)
    assert 0.0 <= metric.overall_pct <= 100.0 * (psutil.cpu_count(logical=True) or 1)
    assert isinstance(metric.per_core_pct, tuple)
    expected_cores = psutil.cpu_count(logical=True) or 0
    assert len(metric.per_core_pct) == expected_cores
    assert metric.logical_cores == expected_cores


def test_collect_mem_returns_typed_metric() -> None:
    metric = collect_mem()
    assert isinstance(metric, MemMetric)
    assert metric.total_b > 0
    assert 0 <= metric.used_b <= metric.total_b
    assert 0.0 <= metric.percent <= 100.0


def test_collect_disk_root_partition() -> None:
    metric = collect_disk("/")
    assert isinstance(metric, DiskMetric)
    assert metric.mountpoint == "/"
    assert metric.total_b > 0
    assert 0 <= metric.used_b <= metric.total_b
    assert 0.0 <= metric.percent <= 100.0
