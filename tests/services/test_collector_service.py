"""CollectorService tests — start/stop, signal relay, idempotent control."""

from __future__ import annotations

import pytest

from healthsh.domain.metrics import MetricsSnapshot
from healthsh.services.collector_service import CollectorService


@pytest.fixture()
def service(qtbot):
    s = CollectorService(interval_s=0.05)
    yield s
    s.stop()


def test_starts_and_emits_metrics(qtbot, service: CollectorService) -> None:
    received: list[MetricsSnapshot] = []
    service.metrics_ready.connect(received.append)
    service.start()
    qtbot.waitUntil(lambda: len(received) >= 2, timeout=1500)
    assert service.is_running()


def test_double_start_is_idempotent(qtbot, service: CollectorService) -> None:  # noqa: ARG001
    service.start()
    service.start()  # must not raise / leak a second thread
    assert service.is_running()


def test_stop_is_clean(qtbot, service: CollectorService) -> None:
    service.start()
    qtbot.waitUntil(service.is_running, timeout=1000)
    service.stop()
    assert not service.is_running()


def test_stop_without_start_is_noop(service: CollectorService) -> None:
    service.stop()  # must not crash on a never-started service
    assert not service.is_running()


def test_set_interval_propagates(service: CollectorService) -> None:
    service.set_interval(0.25)
    assert service.interval_s() == 0.25
