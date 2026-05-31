"""Sparkline tests — buffer cap, missing-data carry-forward, reset, scroll."""

from __future__ import annotations

from datetime import UTC, datetime

from healthsh.domain.metrics import CpuMetric, MemMetric, MetricsSnapshot
from healthsh.ui.widgets.sparkline import WINDOW_SECONDS, Sparkline


def _snap(cpu: float | None, mem_pct: float | None) -> MetricsSnapshot:
    cpu_metric = (
        CpuMetric(
            overall_pct=cpu, per_core_pct=(), physical_cores=0, logical_cores=0, freq_mhz=None
        )
        if cpu is not None
        else None
    )
    mem_metric = MemMetric(total_b=1, used_b=0, percent=mem_pct) if mem_pct is not None else None
    return MetricsSnapshot(
        cpu=cpu_metric, mem=mem_metric, disk=None, gpu=None, ts=datetime.now(tz=UTC)
    )


def test_buffer_cap_holds_at_window_size(qtbot) -> None:
    """Feeding more than WINDOW_SECONDS samples must drop the oldest."""
    s = Sparkline()
    qtbot.addWidget(s)
    for i in range(WINDOW_SECONDS + 25):
        s.append(_snap(cpu=float(i % 100), mem_pct=float(i % 100)))
    assert len(s.cpu_buffer()) == WINDOW_SECONDS
    assert len(s.ram_buffer()) == WINDOW_SECONDS


def test_appends_individual_samples(qtbot) -> None:
    s = Sparkline()
    qtbot.addWidget(s)
    s.append(_snap(cpu=10.0, mem_pct=20.0))
    s.append(_snap(cpu=15.0, mem_pct=25.0))
    assert s.cpu_buffer() == (10.0, 15.0)
    assert s.ram_buffer() == (20.0, 25.0)


def test_reset_clears_buffers(qtbot) -> None:
    s = Sparkline()
    qtbot.addWidget(s)
    for i in range(5):
        s.append(_snap(cpu=float(i), mem_pct=float(i)))
    s.reset()
    assert s.cpu_buffer() == ()
    assert s.ram_buffer() == ()


def test_missing_cpu_carries_previous_value(qtbot) -> None:
    """If CPU collection fails the sparkline carries the last known value forward."""
    s = Sparkline()
    qtbot.addWidget(s)
    s.append(_snap(cpu=50.0, mem_pct=60.0))
    s.append(_snap(cpu=None, mem_pct=65.0))  # CPU failed transiently
    assert s.cpu_buffer() == (50.0, 50.0)
    assert s.ram_buffer() == (60.0, 65.0)


def test_missing_at_start_uses_zero(qtbot) -> None:
    """No previous value + None now → 0.0 to keep the curve continuous."""
    s = Sparkline()
    qtbot.addWidget(s)
    s.append(_snap(cpu=None, mem_pct=None))
    assert s.cpu_buffer() == (0.0,)
    assert s.ram_buffer() == (0.0,)


def test_buffer_size_after_long_run(qtbot) -> None:
    """Running through many ticks must keep the buffer bounded — no memory growth."""
    s = Sparkline()
    qtbot.addWidget(s)
    for i in range(500):
        s.append(_snap(cpu=float(i % 100), mem_pct=float(i % 100)))
    assert len(s.cpu_buffer()) == WINDOW_SECONDS
    assert len(s.ram_buffer()) == WINDOW_SECONDS
    # And the buffer reflects the most recent 60 samples.
    assert s.cpu_buffer()[-1] == float(499 % 100)
