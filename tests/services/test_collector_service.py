"""CollectorService tests — start/stop, signal relay, idempotent control."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from healthsh.domain.container import DockerStatus
from healthsh.domain.metrics import MetricsSnapshot
from healthsh.infra.collectors.docker_collector import DockerCollector
from healthsh.infra.collectors.journald_collector import JournaldCollector
from healthsh.services.collector_service import CollectorService


def _empty_runner(_argv: list[str]) -> Any:
    return subprocess.CompletedProcess(args=["journalctl"], returncode=0, stdout="", stderr="")


class _DockerStub(DockerCollector):
    """Cheap docker stub — never touches a real daemon, returns a fixed status."""

    def __init__(self, *, kind: str = "not_installed") -> None:
        # Skip the real __init__ — we own every method we override below.
        self._cached_status = DockerStatus(kind=kind)  # type: ignore[arg-type]
        self._client = None
        self._last_probe_at = 0.0
        self._factory = lambda: None
        self._socket_path = None  # type: ignore[assignment]
        self._clock = lambda: 0.0

    def status(self) -> DockerStatus:
        return self._cached_status  # type: ignore[return-value]

    def list_containers(self) -> tuple[DockerStatus, list]:
        return self._cached_status, []  # type: ignore[return-value]

    def stats_pairs(self, infos, *, max_workers: int = 4):  # noqa: ARG002
        return [(info, None) for info in infos]


@pytest.fixture()
def service(qtbot):
    # Use stubs so the slow worker never spawns a real journalctl / docker
    # call — tests stay deterministic and fast.
    s = CollectorService(
        interval_s=0.05,
        slow_interval_s=0.05,
        docker_collector=_DockerStub(),
        journald_collector=JournaldCollector(runner=_empty_runner, binary_path="/fake"),
    )
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
