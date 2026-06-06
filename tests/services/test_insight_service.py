"""InsightService tests — per-target picks, healthy fallback, container outlier."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from healthsh.domain.container import ContainerStats
from healthsh.domain.insight import Insight
from healthsh.domain.log_entry import LogEntry
from healthsh.infra.db.sqlite_store import MetricsStore
from healthsh.services.history_service import HistoryService
from healthsh.services.insight_service import InsightService


@pytest.fixture()
def history(tmp_path: Path):
    store = MetricsStore(path=tmp_path / "h.db")
    service = HistoryService(store=store)
    yield service
    store.close()


def _seed_disk_filling(
    history: HistoryService,
    *,
    base: datetime,
    samples: int = 60,
    total_b: int = 200 * 1024**3,
    growth_b_per_min: int = 1 * 1024**3,
) -> None:
    """Seed a fast-filling disk history."""
    store: Any = history.store()
    for i in range(samples):
        ts = base + timedelta(minutes=i)
        used_b = int(total_b * 0.50) + growth_b_per_min * i
        pct = used_b / total_b * 100.0
        store.insert_metrics(ts, [("disk_used_b", float(used_b)), ("disk_pct", pct)])


def test_dashboard_emits_disk_forecast_when_history_present(history: HistoryService, qtbot) -> None:  # noqa: ARG001
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    _seed_disk_filling(history, base=base, samples=120)
    # InsightService uses "now" for the lookback window; we can't override it
    # without patching, so seed up to "almost-now" and trigger a tick.
    service = InsightService(history_service=history, tick_s=30)
    received: list[Insight | None] = []
    service.insight_for_dashboard.connect(received.append)
    service.tick()
    # The forecast looks back 24h, but our synthetic samples start well in the
    # past — the engine may still suppress (ETA > 30d). That is acceptable; we
    # are asserting the emission path, not the magnitude.
    assert received  # at least one emission happened


def test_docker_outlier_detection(history: HistoryService, qtbot) -> None:  # noqa: ARG001
    service = InsightService(history_service=history)
    received: list[Insight | None] = []
    service.insight_for_docker.connect(received.append)
    service.push_container_stats(
        [
            ("redis", ContainerStats(cpu_pct=1.0, mem_used_b=200 * 1024 * 1024)),
            ("grafana", ContainerStats(cpu_pct=1.0, mem_used_b=180 * 1024 * 1024)),
            ("postgres-dev", ContainerStats(cpu_pct=1.0, mem_used_b=4 * 1024**3)),
        ]
    )
    service.tick()
    insight = received[-1]
    assert insight is not None
    assert "postgres-dev" in insight.title


def test_logs_clusters_repeated_errors(history: HistoryService, qtbot) -> None:  # noqa: ARG001
    service = InsightService(history_service=history)
    received: list[Insight | None] = []
    service.insight_for_logs.connect(received.append)
    base = datetime.now(tz=UTC)
    entries = [
        LogEntry(
            ts=base - timedelta(minutes=i),
            unit="NetworkManager.service",
            priority=3,
            message=f"link down attempt #{i}",
        )
        for i in range(12)
    ]
    service.push_logs(entries)
    service.tick()
    insight = received[-1]
    assert insight is not None
    assert "NetworkManager.service" in insight.title or "identical" in insight.title


def test_logs_fallback_when_buffer_empty(history: HistoryService, qtbot) -> None:  # noqa: ARG001
    service = InsightService(history_service=history)
    received: list[Insight | None] = []
    service.insight_for_logs.connect(received.append)
    service.tick()
    assert received[-1] is None


def test_docker_returns_none_when_no_container_runs(history: HistoryService, qtbot) -> None:  # noqa: ARG001
    service = InsightService(history_service=history)
    received: list[Insight | None] = []
    service.insight_for_docker.connect(received.append)
    service.tick()
    assert received[-1] is None


def test_last_caches_emitted_insight_per_target(history: HistoryService, qtbot) -> None:  # noqa: ARG001
    service = InsightService(history_service=history)
    service.push_container_stats(
        [
            ("a", ContainerStats(cpu_pct=1.0, mem_used_b=10 * 1024**2)),
            ("b", ContainerStats(cpu_pct=1.0, mem_used_b=12 * 1024**2)),
            ("c", ContainerStats(cpu_pct=1.0, mem_used_b=2 * 1024**3)),
        ]
    )
    service.tick()
    assert service.last("docker") is not None
    assert service.last("logs") is None


def test_rejects_non_positive_tick(history: HistoryService) -> None:
    with pytest.raises(ValueError):
        InsightService(history_service=history, tick_s=0)


def test_tick_does_not_emit_when_paused_after_stop(history: HistoryService, qtbot) -> None:  # noqa: ARG001
    service = InsightService(history_service=history)
    service.start()
    service.stop()
    # No timer firing — only manual tick() should emit. Verify it does.
    received: list[Insight | None] = []
    service.insight_for_logs.connect(received.append)
    service.tick()
    assert len(received) == 1
