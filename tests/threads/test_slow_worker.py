"""SlowWorker tests — emission, cooperative stop, recheck, restartability."""

from __future__ import annotations

import threading

import pytest

from healthsh.domain.container import ContainerInfo, DockerStatus
from healthsh.infra.threads.slow_worker import SlowWorker


class _ScriptedCollector:
    """Synchronous fake :class:`DockerCollector` for slow-worker tests."""

    def __init__(self, status: DockerStatus, items: list[ContainerInfo] | None = None) -> None:
        self.status_value = status
        self.items = items or []
        self.ticks = 0
        self.rechecks = 0
        self._lock = threading.Lock()

    def list_containers(self) -> tuple[DockerStatus, list[ContainerInfo]]:
        with self._lock:
            self.ticks += 1
        return self.status_value, list(self.items)

    def stats_pairs(self, infos, *, max_workers: int = 4):  # noqa: ARG002
        return [(info, None) for info in infos]

    def force_recheck(self) -> DockerStatus:
        with self._lock:
            self.rechecks += 1
        return self.status_value


def test_rejects_non_positive_interval() -> None:
    with pytest.raises(ValueError):
        SlowWorker(interval_s=0)
    with pytest.raises(ValueError):
        SlowWorker(interval_s=-1)


def test_emits_docker_ready_each_tick(qtbot) -> None:
    """The worker emits docker_ready ≥ 2 times within a 1.5 s window at fast cadence."""
    collector = _ScriptedCollector(DockerStatus(kind="ok"))
    worker = SlowWorker(docker_collector=collector, interval_s=0.05)
    received: list[tuple[DockerStatus, list]] = []
    worker.docker_ready.connect(lambda s, p: received.append((s, p)))

    try:
        worker.start()
        qtbot.waitUntil(lambda: len(received) >= 2, timeout=1500)
        assert all(s.kind == "ok" for s, _ in received)
    finally:
        worker.request_stop()
        worker.wait(2000)


def test_emits_typed_status_when_not_ok(qtbot) -> None:
    """When status is not_installed the worker still emits — no exceptions."""
    collector = _ScriptedCollector(DockerStatus(kind="not_installed"))
    worker = SlowWorker(docker_collector=collector, interval_s=0.05)
    received: list[DockerStatus] = []
    worker.docker_ready.connect(lambda s, _p: received.append(s))

    try:
        worker.start()
        qtbot.waitUntil(lambda: len(received) >= 2, timeout=1500)
        assert all(s.kind == "not_installed" for s in received)
    finally:
        worker.request_stop()
        worker.wait(2000)


def test_clean_stop_within_two_seconds(qtbot) -> None:
    collector = _ScriptedCollector(DockerStatus(kind="ok"))
    worker = SlowWorker(docker_collector=collector, interval_s=0.05)
    worker.start()
    qtbot.waitUntil(worker.isRunning, timeout=1000)
    worker.request_stop()
    assert worker.wait(2000) is True


def test_can_be_restarted_after_stop(qtbot) -> None:
    collector = _ScriptedCollector(DockerStatus(kind="ok"))
    worker = SlowWorker(docker_collector=collector, interval_s=0.05)
    worker.start()
    qtbot.waitUntil(worker.isRunning, timeout=1000)
    worker.request_stop()
    assert worker.wait(2000) is True

    received: list[DockerStatus] = []
    worker.docker_ready.connect(lambda s, _p: received.append(s))
    worker.start()
    try:
        qtbot.waitUntil(lambda: len(received) >= 1, timeout=1500)
        assert received
    finally:
        worker.request_stop()
        worker.wait(2000)


def test_request_recheck_shortens_next_iteration(qtbot) -> None:
    """The recheck flag drops the wait between the current and next tick."""
    collector = _ScriptedCollector(DockerStatus(kind="ok"))
    # Long interval so without recheck we would not get a second emission inside the window.
    worker = SlowWorker(docker_collector=collector, interval_s=2.0)
    received: list[DockerStatus] = []
    worker.docker_ready.connect(lambda s, _p: received.append(s))

    try:
        worker.start()
        qtbot.waitUntil(lambda: len(received) >= 1, timeout=1000)
        worker.request_recheck()
        qtbot.waitUntil(lambda: len(received) >= 2, timeout=1000)
        assert len(received) >= 2
    finally:
        worker.request_stop()
        worker.wait(2000)
