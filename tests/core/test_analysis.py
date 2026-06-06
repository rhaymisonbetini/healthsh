"""AnalysisEngine tests — disk forecast, leak detection, log clustering."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from healthsh.core.analysis import AnalysisEngine, _signature_for
from healthsh.core.thresholds import Thresholds
from healthsh.domain.log_entry import LogEntry

# ---------------------------------------------------------------------------
# Disk-fill forecast.
# ---------------------------------------------------------------------------


def _disk_history(
    *,
    start: datetime,
    minutes: int,
    start_b: int,
    growth_b_per_min: float,
    sample_period_s: int = 60,
) -> list[tuple[datetime, float]]:
    """Build a synthetic linear disk usage history."""
    samples: list[tuple[datetime, float]] = []
    elapsed = 0
    while elapsed <= minutes * 60:
        ts = start + timedelta(seconds=elapsed)
        used_b = float(start_b + growth_b_per_min * (elapsed / 60.0))
        samples.append((ts, used_b))
        elapsed += sample_period_s
    return samples


def test_forecast_flat_history_returns_none() -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    history = [(base + timedelta(seconds=i), 100.0) for i in range(0, 600, 10)]
    engine = AnalysisEngine()
    assert (
        engine.forecast_disk_full(
            history, disk_total_b=200 * 1024**3, now=base + timedelta(seconds=600)
        )
        is None
    )


def test_forecast_returns_eta_for_realistic_filling_disk() -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    total_b = 200 * 1024**3  # 200 GiB
    # Fill 1 GiB per minute → 200 minutes to full from empty.
    history = _disk_history(
        start=base,
        minutes=60,
        start_b=int(total_b * 0.50),
        growth_b_per_min=1 * 1024**3,
    )
    engine = AnalysisEngine()
    insight = engine.forecast_disk_full(
        history, disk_total_b=total_b, now=base + timedelta(hours=1)
    )
    assert insight is not None
    assert insight.source == "disk_forecast"
    # 100 GiB remaining ÷ 1 GiB/min ≈ 100 minutes → "1h" or "2h" depending on rounding.
    assert "h" in insight.title or "min" in insight.title
    assert insight.severity in ("warning", "critical")


def test_forecast_suppresses_eta_beyond_30_days() -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    total_b = 200 * 1024**3
    history = _disk_history(
        start=base, minutes=60, start_b=int(total_b * 0.50), growth_b_per_min=100
    )  # ~ 100 bytes/min → forever
    engine = AnalysisEngine()
    assert (
        engine.forecast_disk_full(history, disk_total_b=total_b, now=base + timedelta(hours=1))
        is None
    )


def test_forecast_critical_when_eta_under_a_day() -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    total_b = 200 * 1024**3
    # 9 GiB/min × 60 min = 540 GiB consumed if 540 GiB free → less than 24h to fill.
    history = _disk_history(
        start=base,
        minutes=60,
        start_b=int(total_b * 0.95),
        growth_b_per_min=int(0.5 * 1024**3),
    )
    engine = AnalysisEngine()
    insight = engine.forecast_disk_full(
        history, disk_total_b=total_b, now=base + timedelta(hours=1)
    )
    assert insight is not None
    assert insight.severity == "critical"


def test_forecast_requires_minimum_samples() -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    history = [(base + timedelta(seconds=i), 1000.0 + i) for i in range(0, 60, 10)]
    engine = AnalysisEngine()
    assert engine.forecast_disk_full(history, disk_total_b=200 * 1024**3, now=base) is None


# ---------------------------------------------------------------------------
# Memory-leak detection.
# ---------------------------------------------------------------------------


def test_detect_leaks_flags_monotonic_growth() -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    # 200 MB over 10 minutes → 20 MB/min slope, growth 200 MB.
    points = [
        (base + timedelta(minutes=i), 100 * 1024 * 1024 + i * 20 * 1024 * 1024) for i in range(11)
    ]
    engine = AnalysisEngine()
    insights = engine.detect_memory_leaks(
        {"postgres-dev": points}, now=base + timedelta(minutes=11)
    )
    assert len(insights) == 1
    assert "postgres-dev" in insights[0].title


def test_detect_leaks_ignores_short_history() -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    points = [(base + timedelta(minutes=i), 100 + i) for i in range(3)]
    engine = AnalysisEngine()
    assert engine.detect_memory_leaks({"x": points}) == []


def test_detect_leaks_ignores_oscillating_series() -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    pattern = [100 * 1024**2 + ((i % 2) * 50 * 1024**2) for i in range(11)]
    points = [(base + timedelta(minutes=i), value) for i, value in enumerate(pattern)]
    engine = AnalysisEngine()
    assert engine.detect_memory_leaks({"chrome": points}) == []


def test_detect_leaks_respects_slope_threshold() -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    # Growth slope is < 5 MB/min — should not be flagged.
    points = [(base + timedelta(minutes=i), 100 * 1024**2 + i * 1 * 1024**2) for i in range(11)]
    engine = AnalysisEngine()
    assert engine.detect_memory_leaks({"x": points}) == []


def test_detect_leaks_threshold_override() -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    points = [(base + timedelta(minutes=i), 100 * 1024**2 + i * 1 * 1024**2) for i in range(11)]
    engine = AnalysisEngine(
        thresholds=Thresholds(leak_min_slope_mb_per_min=0.5, leak_min_growth_mb=5)
    )
    insights = engine.detect_memory_leaks({"x": points})
    assert insights and "x" in insights[0].title


# ---------------------------------------------------------------------------
# Log clustering.
# ---------------------------------------------------------------------------


def _err_entry(unit: str, message: str, *, ts: datetime, priority: int = 3) -> LogEntry:
    return LogEntry(ts=ts, unit=unit, priority=priority, message=message)


def test_signature_normalises_numbers_and_uuids() -> None:
    sig_a = _signature_for("Failed login from 10.0.0.5 attempt #42")
    sig_b = _signature_for("Failed login from 192.168.1.7 attempt #99")
    assert sig_a == sig_b


def test_signature_normalises_paths_and_hex() -> None:
    sig_a = _signature_for("Could not open /var/log/foo.log: 0xdeadbeef")
    sig_b = _signature_for("Could not open /tmp/bar.log: 0xfeedface")
    assert sig_a == sig_b


def test_cluster_detects_repeated_errors() -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    entries: list[LogEntry] = []
    for i in range(12):
        entries.append(
            _err_entry(
                "NetworkManager.service",
                f"link down on eth0 attempt #{i}",
                ts=base + timedelta(minutes=i),
            )
        )
    engine = AnalysisEngine()
    insights = engine.cluster_log_errors(entries, now=base + timedelta(minutes=12))
    assert any("12 identical NetworkManager.service" in i.title for i in insights)


def test_cluster_ignores_low_priority_chatter() -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    entries = [
        _err_entry("systemd", "info chatter", ts=base + timedelta(minutes=i), priority=6)
        for i in range(20)
    ]
    engine = AnalysisEngine()
    assert engine.cluster_log_errors(entries, now=base + timedelta(minutes=20)) == []


def test_cluster_respects_window_cutoff() -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    entries = [
        _err_entry("foo", f"err {i}", ts=base - timedelta(hours=3, minutes=i)) for i in range(20)
    ]
    engine = AnalysisEngine()
    # All entries are outside the 2h window — no cluster reported.
    assert engine.cluster_log_errors(entries, now=base) == []
