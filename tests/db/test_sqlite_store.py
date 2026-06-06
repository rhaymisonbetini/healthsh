"""MetricsStore tests — schema lifecycle, queries, retention vacuum, threading."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from healthsh.infra.db.sqlite_store import MetricsStore, default_db_path


@pytest.fixture()
def store(tmp_path: Path) -> MetricsStore:
    s = MetricsStore(path=tmp_path / "history.db")
    yield s
    s.close()


def test_default_db_path_honors_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert default_db_path() == tmp_path / "xdg" / "healthsh" / "healthsh.db"


def test_default_db_path_falls_back_to_local_share(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    expected = Path.home() / ".local" / "share" / "healthsh" / "healthsh.db"
    assert default_db_path() == expected


def test_insert_metrics_and_query_round_trip(store: MetricsStore) -> None:
    ts = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    count = store.insert_metrics(ts, [("cpu_pct", 42.0), ("mem_pct", 73.5)])
    assert count == 2
    rows = store.query("cpu_pct", since=ts - timedelta(seconds=1), until=ts + timedelta(seconds=1))
    assert len(rows) == 1
    assert rows[0][1] == 42.0


def test_insert_skips_none_and_nan_values(store: MetricsStore) -> None:
    ts = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    count = store.insert_metrics(
        ts,
        [("cpu_pct", 10.0), ("mem_pct", None), ("disk_pct", float("nan"))],  # type: ignore[list-item]
    )
    assert count == 1


def test_query_rejects_inverted_window(store: MetricsStore) -> None:
    now = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        store.query("cpu_pct", since=now + timedelta(seconds=1), until=now)


def test_query_aggregate_downsamples_by_bucket(store: MetricsStore) -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    for offset in range(0, 10):
        store.insert_metrics(base + timedelta(seconds=offset), [("cpu_pct", float(offset))])
    rows = store.query_aggregate(
        "cpu_pct",
        since=base,
        until=base + timedelta(seconds=10),
        bucket_s=5,
    )
    # Two buckets: 0–4 → avg 2; 5–9 → avg 7.
    values = [round(v, 2) for _ts, v in rows]
    assert values == [2.0, 7.0]


def test_query_aggregate_rejects_non_positive_bucket(store: MetricsStore) -> None:
    ts = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        store.query_aggregate("cpu_pct", since=ts, until=ts, bucket_s=0)


def test_insert_and_query_process_samples(store: MetricsStore) -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    for offset in range(3):
        store.insert_processes(
            base + timedelta(seconds=offset),
            [(123, "postgres", (offset + 1) * 1024 * 1024)],
        )
    rows = store.query_process("postgres", since=base, until=base + timedelta(seconds=10))
    assert [v for _ts, v in rows] == [1 * 1024 * 1024, 2 * 1024 * 1024, 3 * 1024 * 1024]


def test_vacuum_old_removes_aged_rows_only(store: MetricsStore) -> None:
    now = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    old_ts = now - timedelta(days=10)
    fresh_ts = now - timedelta(days=2)
    store.insert_metrics(old_ts, [("cpu_pct", 1.0)])
    store.insert_metrics(fresh_ts, [("cpu_pct", 2.0)])
    removed = store.vacuum_old(retain_days=7, now=now)
    assert removed == 1
    assert store.count_rows("metric_samples") == 1


def test_vacuum_rejects_non_positive_retention(store: MetricsStore) -> None:
    with pytest.raises(ValueError):
        store.vacuum_old(retain_days=0)


def test_thread_safety_under_concurrent_writes(store: MetricsStore) -> None:
    """Three threads writing 100 inserts each should land all 300 rows."""
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)

    def _writer(thread_idx: int) -> None:
        for i in range(100):
            ts = base + timedelta(milliseconds=thread_idx * 100 + i)
            store.insert_metrics(ts, [("cpu_pct", float(i))])

    threads = [threading.Thread(target=_writer, args=(t,)) for t in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert store.count_rows("metric_samples") == 300


def test_close_is_idempotent(store: MetricsStore) -> None:
    store.close()
    store.close()  # must not raise
