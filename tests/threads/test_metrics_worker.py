"""MetricsWorker tests — start/stop lifecycle, emission, isolation, configurability."""

from __future__ import annotations

import pytest

from healthsh.domain.metrics import MetricsSnapshot
from healthsh.infra.threads import metrics_worker as worker_mod
from healthsh.infra.threads.metrics_worker import MetricsWorker


@pytest.fixture()
def fast_worker(qtbot):
    """Build a worker with a tight tick so tests stay fast."""
    w = MetricsWorker(interval_s=0.05)
    yield w
    w.request_stop()
    w.wait(2000)


def test_emits_metrics_ready_at_each_tick(qtbot, fast_worker: MetricsWorker) -> None:
    """At least two snapshots must arrive within a 1.5 s window."""
    received: list[MetricsSnapshot] = []
    fast_worker.metrics_ready.connect(received.append)

    fast_worker.start()
    qtbot.waitUntil(lambda: len(received) >= 2, timeout=1500)

    assert len(received) >= 2
    assert all(isinstance(s, MetricsSnapshot) for s in received)
    assert all(s.ts is not None for s in received)


def test_clean_stop_completes_within_two_seconds(qtbot, fast_worker: MetricsWorker) -> None:  # noqa: ARG001
    """Stopping the worker returns within the 2 s SLA."""
    fast_worker.start()
    qtbot.waitUntil(fast_worker.isRunning, timeout=1000)
    fast_worker.request_stop()
    assert fast_worker.wait(2000) is True


def test_collector_failure_does_not_kill_worker(
    qtbot, monkeypatch: pytest.MonkeyPatch, fast_worker: MetricsWorker
) -> None:
    """If one collector raises every tick the worker still keeps ticking."""

    def _boom() -> None:
        raise RuntimeError("synthetic mem failure")

    monkeypatch.setattr(worker_mod, "collect_mem", _boom)

    received: list[MetricsSnapshot] = []
    fast_worker.metrics_ready.connect(received.append)
    fast_worker.start()
    qtbot.waitUntil(lambda: len(received) >= 3, timeout=2000)

    assert len(received) >= 3
    assert all(s.mem is None for s in received), "mem should be None on every tick"
    assert any(s.cpu is not None for s in received), (
        "other collectors must still produce values when mem fails"
    )


def test_rejects_non_positive_interval() -> None:
    with pytest.raises(ValueError):
        MetricsWorker(interval_s=0)
    with pytest.raises(ValueError):
        MetricsWorker(interval_s=-0.1)


def test_set_interval_updates_runtime(qtbot, fast_worker: MetricsWorker) -> None:  # noqa: ARG001
    """``set_interval`` updates the stored value (takes effect on the next sleep)."""
    fast_worker.set_interval(0.25)
    assert fast_worker.interval_s() == 0.25
    with pytest.raises(ValueError):
        fast_worker.set_interval(0)


def test_can_be_restarted_after_stop(qtbot, fast_worker: MetricsWorker) -> None:
    """The internal stop event clears on each ``run`` so the worker can restart."""
    fast_worker.start()
    qtbot.waitUntil(fast_worker.isRunning, timeout=1000)
    fast_worker.request_stop()
    assert fast_worker.wait(2000) is True

    received: list[MetricsSnapshot] = []
    fast_worker.metrics_ready.connect(received.append)
    fast_worker.start()
    qtbot.waitUntil(lambda: len(received) >= 1, timeout=1500)
    assert received
