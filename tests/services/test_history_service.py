"""HistoryService tests — snapshot persistence, lifecycle, vacuum."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal

from healthsh.domain.metrics import CpuMetric, DiskMetric, GpuMetric, MemMetric, MetricsSnapshot
from healthsh.domain.process import ProcessInfo
from healthsh.infra.db.sqlite_store import MetricsStore
from healthsh.services.history_service import HistoryService


class _FakeCollector(QObject):
    """Tiny QObject just exposing the signal HistoryService subscribes to."""

    metrics_ready = Signal(object)


@pytest.fixture()
def store(tmp_path: Path) -> MetricsStore:
    s = MetricsStore(path=tmp_path / "history.db")
    yield s
    s.close()


def _snapshot(
    *,
    ts: datetime,
    cpu: float = 50.0,
    mem_pct: float = 40.0,
    mem_used: int = 4 * 1024**3,
    disk_pct: float = 30.0,
    disk_used: int = 100 * 1024**3,
    procs: tuple[ProcessInfo, ...] = (),
) -> MetricsSnapshot:
    return MetricsSnapshot(
        cpu=CpuMetric(
            overall_pct=cpu,
            per_core_pct=(cpu,) * 4,
            physical_cores=4,
            logical_cores=4,
            freq_mhz=3000.0,
        ),
        mem=MemMetric(total_b=16 * 1024**3, used_b=mem_used, percent=mem_pct),
        disk=DiskMetric(
            mountpoint="/",
            total_b=200 * 1024**3,
            used_b=disk_used,
            percent=disk_pct,
        ),
        gpu=None,
        ts=ts,
        processes_full=procs,
    )


def test_insert_snapshot_persists_each_metric(store: MetricsStore) -> None:
    service = HistoryService(store=store)
    ts = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    inserted = service.insert_snapshot(_snapshot(ts=ts))
    # cpu_pct + mem_pct + mem_used_b + disk_pct + disk_used_b = 5 rows
    assert inserted == 5


def test_insert_snapshot_with_gpu(store: MetricsStore) -> None:
    service = HistoryService(store=store)
    ts = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    snap = _snapshot(ts=ts)
    gpu_snap = MetricsSnapshot(
        cpu=snap.cpu,
        mem=snap.mem,
        disk=snap.disk,
        gpu=GpuMetric(
            vendor="amd",
            name="Radeon",
            util_pct=42.0,
            mem_used_b=2 * 1024**3,
            mem_total_b=8 * 1024**3,
            temp_c=55.0,
        ),
        ts=ts,
    )
    inserted = service.insert_snapshot(gpu_snap)
    # + gpu_pct + gpu_temp_c
    assert inserted == 7


def test_processes_full_is_persisted(store: MetricsStore) -> None:
    service = HistoryService(store=store)
    ts = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    procs = (
        ProcessInfo(pid=10, name="postgres", user="u", cpu_pct=1.0, mem_b=4 * 1024**3),
        ProcessInfo(pid=11, name="chrome", user="u", cpu_pct=2.0, mem_b=800 * 1024**2),
    )
    service.insert_snapshot(_snapshot(ts=ts, procs=procs))
    rows = service.query_process(
        "postgres",
        since=ts - timedelta(seconds=1),
        until=ts + timedelta(seconds=1),
    )
    assert len(rows) == 1
    assert rows[0][1] == 4 * 1024**3


def test_collector_signal_drives_persistence(store: MetricsStore, qtbot) -> None:  # noqa: ARG001
    collector = _FakeCollector()
    service = HistoryService(store=store, collector_service=collector)  # type: ignore[arg-type]
    service.start()
    ts = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    collector.metrics_ready.emit(_snapshot(ts=ts))
    rows = service.query(
        "cpu_pct", since=ts - timedelta(seconds=1), until=ts + timedelta(seconds=1)
    )
    assert rows and rows[0][1] == 50.0
    service.stop()


def test_double_start_is_idempotent(store: MetricsStore, qtbot) -> None:  # noqa: ARG001
    service = HistoryService(store=store)
    service.start()
    service.start()
    assert service.is_started() is True
    service.stop()
    assert service.is_started() is False
    service.stop()  # idempotent


def test_vacuum_now_removes_rows_outside_retention(store: MetricsStore) -> None:
    service = HistoryService(store=store, retain_days=1)
    now = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    service.insert_snapshot(_snapshot(ts=now - timedelta(days=10)))
    service.insert_snapshot(_snapshot(ts=now))
    # Stub the store's vacuum to use the pinned `now` for determinism.
    service._store.vacuum_old(retain_days=1, now=now)  # type: ignore[attr-defined]
    # Only the fresh snapshot's rows should remain.
    assert service._store.count_rows("metric_samples") == 5  # type: ignore[attr-defined]


def test_query_aggregate_buckets_consecutive_snapshots(store: MetricsStore) -> None:
    service = HistoryService(store=store)
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    for offset in range(10):
        service.insert_snapshot(_snapshot(ts=base + timedelta(seconds=offset), cpu=float(offset)))
    rows = service.query_aggregate(
        "cpu_pct",
        since=base,
        until=base + timedelta(seconds=10),
        bucket_s=5,
    )
    values = [round(v, 2) for _ts, v in rows]
    assert values == [2.0, 7.0]
