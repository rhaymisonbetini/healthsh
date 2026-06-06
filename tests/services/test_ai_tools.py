"""ai_tools tests — shapes, summarisers, parsing edges."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from healthsh.domain.container import ContainerInfo, ContainerStats, DockerStatus
from healthsh.infra.collectors.docker_collector import DockerCollector
from healthsh.infra.collectors.journald_collector import JournaldCollector
from healthsh.infra.db.sqlite_store import MetricsStore
from healthsh.services import ai_tools
from healthsh.services.history_service import HistoryService


@pytest.fixture()
def history(tmp_path: Path):
    store = MetricsStore(path=tmp_path / "history.db")
    service = HistoryService(store=store)
    yield service
    store.close()


def test_get_metrics_returns_iso_payload(history: HistoryService) -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    for offset in range(5):
        history.store().insert_metrics(
            base + timedelta(seconds=offset),
            [("cpu_pct", float(offset * 10))],
        )
    result = ai_tools.get_metrics(
        history,
        metric="cpu_pct",
        since=base.isoformat(),
        until=(base + timedelta(seconds=4)).isoformat(),
    )
    assert result["metric"] == "cpu_pct"
    assert len(result["samples"]) == 5
    assert result["samples"][0]["value"] == 0.0
    assert result["samples"][-1]["value"] == 40.0


def test_get_processes_returns_top_n(monkeypatch: pytest.MonkeyPatch) -> None:
    from healthsh.domain.process import ProcessInfo
    from healthsh.services import ai_tools as tools_mod

    fake = [
        ProcessInfo(pid=1, name="big", user="u", cpu_pct=1.0, mem_b=10 * 1024**3),
        ProcessInfo(pid=2, name="small", user="u", cpu_pct=99.0, mem_b=1 * 1024**2),
    ]
    monkeypatch.setattr(tools_mod, "list_all_processes", lambda: fake)
    by_mem = ai_tools.get_processes(top_n_by="memory", n=1)
    assert by_mem[0]["name"] == "big"
    by_cpu = ai_tools.get_processes(top_n_by="cpu", n=1)
    assert by_cpu[0]["name"] == "small"


def test_get_processes_rejects_invalid_n() -> None:
    with pytest.raises(ValueError):
        ai_tools.get_processes(n=0)


def test_get_processes_rejects_unknown_top_n_by() -> None:
    with pytest.raises(ValueError):
        ai_tools.get_processes(top_n_by="disk")  # type: ignore[arg-type]


def _journal_runner(payload: str) -> Any:
    def _runner(_argv: list[str]) -> Any:
        return subprocess.CompletedProcess(
            args=["journalctl"], returncode=0, stdout=payload, stderr=""
        )

    return _runner


def test_get_logs_filters_by_window() -> None:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    import json as _json

    payload = "\n".join(
        _json.dumps(
            {
                "__REALTIME_TIMESTAMP": str(
                    int((base + timedelta(seconds=i)).timestamp()) * 1_000_000
                ),
                "_SYSTEMD_UNIT": "nm.service",
                "PRIORITY": "4",
                "MESSAGE": f"event {i}",
                "_HOSTNAME": "h",
            }
        )
        for i in range(5)
    )
    journald = JournaldCollector(runner=_journal_runner(payload), binary_path="/fake")
    rows = ai_tools.get_logs(
        journald,
        since=(base + timedelta(seconds=2)).isoformat(),
        until=(base + timedelta(seconds=3)).isoformat(),
    )
    assert {r["message"] for r in rows} == {"event 2", "event 3"}


def test_get_containers_handles_not_installed_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("healthsh.infra.collectors.docker_collector.shutil.which", lambda _: None)
    collector = DockerCollector(socket_path=tmp_path / "missing.sock")
    payload = ai_tools.get_containers(collector)
    assert payload == {"status": "not_installed", "detail": payload["detail"], "containers": []}


class _FakeContainer:
    def __init__(self, *, id: str, name: str, status: str) -> None:
        self.id = id
        self.name = name
        self.status = status
        self.attrs = {
            "Id": id,
            "Name": f"/{name}",
            "Config": {"Image": "alpine"},
            "State": {"Status": status, "StartedAt": ""},
            "NetworkSettings": {"Ports": {}},
        }

    def stats(self, *, stream: bool) -> dict:  # noqa: ARG002
        return {"cpu_stats": {}, "precpu_stats": {}, "memory_stats": {}}


class _FakeContainers:
    def __init__(self, items: list[_FakeContainer]) -> None:
        self._items = items

    def list(self, *, all: bool = False) -> list[_FakeContainer]:  # noqa: A002, ARG002
        return list(self._items)

    def get(self, container_id: str) -> _FakeContainer:
        return next(c for c in self._items if c.id == container_id)


class _FakeClient:
    def __init__(self, items: list[_FakeContainer]) -> None:
        self.containers = _FakeContainers(items)

    def ping(self) -> bool:
        return True


def test_get_containers_ok_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "healthsh.infra.collectors.docker_collector.shutil.which", lambda _: "/usr/bin/docker"
    )
    fakes = [_FakeContainer(id="a", name="redis", status="running")]
    collector = DockerCollector(client_factory=lambda: _FakeClient(fakes))
    payload = ai_tools.get_containers(collector)
    assert payload["status"] == "ok"
    assert payload["containers"][0]["name"] == "redis"


def test_summary_helpers_produce_strings() -> None:
    metric_payload = {
        "metric": "cpu_pct",
        "samples": [{"ts": "2026-06-06T14:00:00+00:00", "value": 10.0}],
        "since": "2026-06-06T14:00:00+00:00",
        "until": "2026-06-06T14:05:00+00:00",
    }
    assert "cpu_pct" in ai_tools.summarise_metrics_result(metric_payload)
    assert "0 entries" in ai_tools.summarise_logs_result([])
    assert "containers" in ai_tools.summarise_containers_result(
        {"status": "ok", "containers": [{}]}
    )
    assert "processes" in ai_tools.summarise_processes_result([{}, {}, {}])


def test_log_summariser_picks_err_severity() -> None:
    rows = [
        {"priority": 3, "message": "boom", "ts": "", "unit": "x", "hostname": ""},
        {"priority": 6, "message": "info", "ts": "", "unit": "y", "hostname": ""},
    ]
    summary = ai_tools.summarise_logs_result(rows)
    assert "err" in summary


def test_container_summary_reports_status_when_not_ok() -> None:
    payload = {"status": "daemon_down", "detail": "x", "containers": []}
    summary = ai_tools.summarise_containers_result(payload)
    assert "daemon_down" in summary


def test_immutable_value_objects() -> None:
    info = ContainerInfo(id="x", name="y", status="running")
    stats = ContainerStats(cpu_pct=1.0, mem_used_b=1)
    status = DockerStatus(kind="ok")
    out = ai_tools._container_pair_as_dict(info, stats)
    assert out["name"] == "y"
    assert status.is_ok
