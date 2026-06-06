"""DockerCollector tests — typed DockerStatus across every detection branch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from healthsh.domain.container import ContainerInfo, ContainerStats, DockerStatus
from healthsh.infra.collectors import docker_collector as dc
from healthsh.infra.collectors.docker_collector import DockerCollector


class _FakeContainer:
    """Minimal stand-in for a docker-py Container object."""

    def __init__(
        self,
        *,
        id: str,
        name: str,
        status: str = "running",
        image: str = "alpine:latest",
        ports: dict | None = None,
        started_at: str = "2026-06-06T10:00:00.000000Z",
        stats_payload: dict | None = None,
        on_start: Any = None,
        on_stop: Any = None,
        on_restart: Any = None,
        logs_payload: bytes = b"line a\nline b\n",
    ) -> None:
        self.id = id
        self.name = name
        self.status = status
        self.attrs = {
            "Id": id,
            "Name": f"/{name}",
            "Config": {"Image": image},
            "State": {"Status": status, "StartedAt": started_at},
            "NetworkSettings": {"Ports": ports or {}},
        }
        self._stats_payload = stats_payload
        self._logs_payload = logs_payload
        self._on_start = on_start or (lambda: None)
        self._on_stop = on_stop or (lambda: None)
        self._on_restart = on_restart or (lambda: None)

    def stats(self, *, stream: bool) -> dict:  # noqa: ARG002
        return self._stats_payload or {}

    def logs(self, *, tail: int) -> bytes:  # noqa: ARG002
        return self._logs_payload

    def start(self) -> None:
        self._on_start()

    def stop(self) -> None:
        self._on_stop()

    def restart(self) -> None:
        self._on_restart()


class _FakeContainers:
    def __init__(self, items: list[_FakeContainer]) -> None:
        self._items = items
        self._by_id = {c.id: c for c in items}

    def list(self, *, all: bool = False) -> list[_FakeContainer]:  # noqa: A002, ARG002
        return list(self._items)

    def get(self, container_id: str) -> _FakeContainer:
        return self._by_id[container_id]


class _FakeClient:
    def __init__(
        self,
        *,
        containers: list[_FakeContainer] | None = None,
        ping_ok: bool = True,
        ping_exc: BaseException | None = None,
    ) -> None:
        self.containers = _FakeContainers(containers or [])
        self._ping_ok = ping_ok
        self._ping_exc = ping_exc

    def ping(self) -> bool:
        if self._ping_exc is not None:
            raise self._ping_exc
        return self._ping_ok


def _ok_factory(containers: list[_FakeContainer] | None = None) -> Any:
    client = _FakeClient(containers=containers or [])
    return lambda: client


# ---------------------------------------------------------------------------
# Detection branches.
# ---------------------------------------------------------------------------


def test_status_not_installed_when_no_binary_and_no_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dc.shutil, "which", lambda _: None)
    collector = DockerCollector(
        client_factory=lambda: pytest.fail("must not be called"),
        socket_path=tmp_path / "missing.sock",
    )
    status = collector.status()
    assert status.kind == "not_installed"


def test_status_ok_when_factory_and_ping_succeed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/docker")
    collector = DockerCollector(client_factory=_ok_factory())
    assert collector.status().kind == "ok"


def test_status_permission_denied_when_ping_raises_permission_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/docker")

    def _factory() -> Any:
        return _FakeClient(ping_exc=PermissionError("denied to /var/run/docker.sock"))

    collector = DockerCollector(client_factory=_factory)
    status = collector.status()
    assert status.kind == "permission_denied"


def test_status_daemon_down_on_docker_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/docker")

    def _factory() -> Any:
        raise dc.DockerException("Cannot connect to the Docker daemon — Connection refused")

    collector = DockerCollector(client_factory=_factory)
    status = collector.status()
    assert status.kind == "daemon_down"


def test_status_unknown_on_unexpected_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/docker")

    def _factory() -> Any:
        raise RuntimeError("the planet exploded")

    collector = DockerCollector(client_factory=_factory)
    status = collector.status()
    assert status.kind == "unknown"


# ---------------------------------------------------------------------------
# Caching + reprobe behaviour.
# ---------------------------------------------------------------------------


def test_status_caches_ok_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/docker")
    calls = []

    def _factory() -> Any:
        calls.append("probe")
        return _FakeClient()

    collector = DockerCollector(client_factory=_factory)
    collector.status()
    collector.status()
    assert len(calls) == 1


def test_status_reprobes_after_interval_when_not_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/docker")
    fake_clock = [0.0]
    attempts: list[str] = []

    def _factory() -> Any:
        attempts.append("probe")
        if len(attempts) == 1:
            raise dc.DockerException("Connection refused")
        return _FakeClient()

    collector = DockerCollector(client_factory=_factory, clock=lambda: fake_clock[0])
    assert collector.status().kind == "daemon_down"
    # Same tick → no second probe.
    assert collector.status().kind == "daemon_down"
    assert len(attempts) == 1
    # Advance past the reprobe interval and try again.
    fake_clock[0] = 61.0
    assert collector.status().kind == "ok"
    assert len(attempts) == 2


def test_force_recheck_bypasses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/docker")
    calls: list[str] = []

    def _factory() -> Any:
        calls.append("probe")
        return _FakeClient()

    collector = DockerCollector(client_factory=_factory)
    collector.status()
    collector.force_recheck()
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# list_containers + stats.
# ---------------------------------------------------------------------------


def test_list_containers_returns_typed_items_when_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/docker")
    fakes = [
        _FakeContainer(
            id="a",
            name="postgres-dev",
            status="running",
            image="postgres:16",
            ports={"5432/tcp": [{"HostPort": "5432"}]},
        ),
        _FakeContainer(id="b", name="redis", status="running"),
        _FakeContainer(id="c", name="grafana", status="exited"),
    ]
    collector = DockerCollector(client_factory=_ok_factory(fakes))
    status, items = collector.list_containers()
    assert status.kind == "ok"
    names = sorted(item.name for item in items)
    assert names == ["grafana", "postgres-dev", "redis"]
    postgres = next(i for i in items if i.name == "postgres-dev")
    assert postgres.image == "postgres:16"
    assert postgres.ports == ("5432:5432",)


def test_list_containers_returns_empty_when_not_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dc.shutil, "which", lambda _: None)
    collector = DockerCollector(
        client_factory=lambda: pytest.fail("must not be called"),
        socket_path=Path("/no/such/path.sock"),
    )
    status, items = collector.list_containers()
    assert status.kind == "not_installed"
    assert items == []


def test_stats_pairs_skips_stopped_and_aggregates_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/docker")
    payload = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 2_000_000_000, "percpu_usage": [1, 2, 3, 4]},
            "system_cpu_usage": 10_000_000_000,
            "online_cpus": 4,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 1_000_000_000},
            "system_cpu_usage": 9_000_000_000,
        },
        "memory_stats": {"usage": 256 * 1024 * 1024, "limit": 2 * 1024**3},
    }
    fakes = [
        _FakeContainer(id="r", name="redis", status="running", stats_payload=payload),
        _FakeContainer(id="s", name="grafana", status="exited"),
    ]
    collector = DockerCollector(client_factory=_ok_factory(fakes))
    _, items = collector.list_containers()
    pairs = collector.stats_pairs(items)
    by_name = {info.name: stats for info, stats in pairs}
    assert by_name["grafana"] is None
    stats = by_name["redis"]
    assert isinstance(stats, ContainerStats)
    assert stats.mem_used_b == 256 * 1024 * 1024
    assert stats.mem_limit_b == 2 * 1024**3
    # CPU% = (1e9 / 1e9) * 4 * 100 = 400
    assert stats.cpu_pct == 400.0


def test_actions_invoke_underlying_container_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/docker")
    seen: list[str] = []
    fake = _FakeContainer(
        id="abc",
        name="alpine",
        status="running",
        on_start=lambda: seen.append("start"),
        on_stop=lambda: seen.append("stop"),
        on_restart=lambda: seen.append("restart"),
    )
    collector = DockerCollector(client_factory=_ok_factory([fake]))
    collector.list_containers()  # primes the client
    collector.start("abc")
    collector.stop("abc")
    collector.restart("abc")
    assert seen == ["start", "stop", "restart"]


def test_tail_logs_splits_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/docker")
    fake = _FakeContainer(id="abc", name="alpine", logs_payload=b"alpha\nbeta\ngamma\n")
    collector = DockerCollector(client_factory=_ok_factory([fake]))
    collector.list_containers()
    assert collector.tail_logs("abc", n=3) == ["alpha", "beta", "gamma"]


def test_tail_logs_rejects_non_positive_n(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/docker")
    collector = DockerCollector(client_factory=_ok_factory())
    with pytest.raises(ValueError):
        collector.tail_logs("anything", n=0)


def test_container_info_helpers_are_pure() -> None:
    """Sanity check that the domain entities exposed by the collector are immutable."""
    info = ContainerInfo(id="x", name="x", status="running")
    with pytest.raises(Exception):  # noqa: B017 — dataclass FrozenInstanceError
        info.status = "stopped"  # type: ignore[misc]
    status = DockerStatus(kind="ok")
    with pytest.raises(Exception):  # noqa: B017
        status.kind = "unknown"  # type: ignore[misc]
