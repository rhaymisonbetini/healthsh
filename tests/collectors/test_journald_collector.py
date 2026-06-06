"""JournaldCollector tests — argv construction, parsing, incremental tailing."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from typing import Any

import pytest

from healthsh.domain.log_entry import LogEntry
from healthsh.infra.collectors.journald_collector import (
    DEFAULT_LOOKBACK_S,
    JournaldCollector,
)


def _completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> Any:
    return subprocess.CompletedProcess(
        args=["journalctl"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _journal_payload(
    *,
    ts_micro: int,
    unit: str = "NetworkManager.service",
    priority: int = 6,
    message: Any = "iface up",
    hostname: str = "host",
) -> str:
    payload = {
        "__REALTIME_TIMESTAMP": str(ts_micro),
        "_SYSTEMD_UNIT": unit,
        "PRIORITY": str(priority),
        "MESSAGE": message,
        "_HOSTNAME": hostname,
    }
    return json.dumps(payload)


def test_rejects_non_positive_lookback() -> None:
    with pytest.raises(ValueError):
        JournaldCollector(lookback_s=0)
    with pytest.raises(ValueError):
        JournaldCollector(lookback_s=-1)


def test_read_recent_returns_empty_when_journalctl_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No journalctl on PATH → is_available() False → no subprocess invocation."""
    monkeypatch.setattr(
        "healthsh.infra.collectors.journald_collector.shutil.which",
        lambda _: None,
    )

    def _runner(_argv: list[str]) -> Any:
        raise AssertionError("runner must not be called when journalctl is missing")

    collector = JournaldCollector(runner=_runner)
    assert collector.is_available() is False
    assert collector.read_recent() == []


def test_parses_a_batch_of_entries() -> None:
    base_micro = 1_700_000_000_000_000
    lines = [
        _journal_payload(ts_micro=base_micro, unit="systemd", priority=6, message="boot"),
        _journal_payload(
            ts_micro=base_micro + 1_000_000,
            unit="NetworkManager.service",
            priority=3,
            message="network down",
        ),
        _journal_payload(
            ts_micro=base_micro + 2_000_000,
            unit="systemd",
            priority=4,
            message="warn",
            hostname="other",
        ),
    ]
    runner_argv: list[list[str]] = []

    def _runner(argv: list[str]) -> Any:
        runner_argv.append(argv)
        return _completed(stdout="\n".join(lines))

    collector = JournaldCollector(runner=_runner, binary_path="/usr/bin/journalctl")
    entries = collector.read_recent()
    assert [e.message for e in entries] == ["boot", "network down", "warn"]
    assert [e.priority for e in entries] == [6, 3, 4]
    assert all(isinstance(e, LogEntry) for e in entries)
    assert all(isinstance(e.ts, datetime) for e in entries)
    # First call uses the lookback window — argv must include --since=@<epoch>.
    assert any(arg.startswith("--since=@") for arg in runner_argv[0])
    assert "--output=json" in runner_argv[0]


def test_filters_units_and_priority_in_argv() -> None:
    captured: list[list[str]] = []

    def _runner(argv: list[str]) -> Any:
        captured.append(argv)
        return _completed(stdout="")

    collector = JournaldCollector(runner=_runner, binary_path="/usr/bin/journalctl")
    collector.read_recent(
        units=["NetworkManager.service", "systemd-networkd.service"],
        max_priority=4,
    )
    argv = captured[0]
    assert "--unit=NetworkManager.service" in argv
    assert "--unit=systemd-networkd.service" in argv
    assert "--priority=4" in argv


def test_incremental_tailing_uses_cursor_on_second_call() -> None:
    base_micro = 1_700_000_000_000_000
    first_batch = "\n".join(
        [
            _journal_payload(ts_micro=base_micro, message="a"),
            _journal_payload(ts_micro=base_micro + 1_000_000, message="b"),
            _journal_payload(ts_micro=base_micro + 2_000_000, message="c"),
        ]
    )
    second_batch = _journal_payload(ts_micro=base_micro + 3_000_000, message="d")
    invocations: list[list[str]] = []

    def _runner(argv: list[str]) -> Any:
        invocations.append(argv)
        return _completed(stdout=first_batch if len(invocations) == 1 else second_batch)

    collector = JournaldCollector(runner=_runner, binary_path="/usr/bin/journalctl")
    first = collector.read_recent()
    assert [e.message for e in first] == ["a", "b", "c"]
    cursor = collector.cursor_ts()
    assert cursor is not None
    # Second call: cursor advances to the last entry's timestamp, --since uses it.
    second = collector.read_recent()
    assert [e.message for e in second] == ["d"]
    # The argv on the second call must use the cursor, not the lookback window.
    expected_since = int(first[-1].ts.timestamp())
    assert f"--since=@{expected_since}" in invocations[1]


def test_first_call_uses_lookback_window() -> None:
    captured: list[list[str]] = []

    def _runner(argv: list[str]) -> Any:
        captured.append(argv)
        return _completed(stdout="")

    collector = JournaldCollector(
        runner=_runner,
        binary_path="/usr/bin/journalctl",
        lookback_s=DEFAULT_LOOKBACK_S,
    )
    pinned_now = datetime.fromtimestamp(1_700_000_000, tz=UTC)
    collector.read_recent(now=pinned_now)
    expected = int(pinned_now.timestamp()) - DEFAULT_LOOKBACK_S
    assert f"--since=@{expected}" in captured[0]


def test_binary_message_is_decoded() -> None:
    """journald sometimes returns MESSAGE as a list of byte ints — decode it."""
    payload = {
        "__REALTIME_TIMESTAMP": "1700000000000000",
        "_SYSTEMD_UNIT": "kernel",
        "PRIORITY": "3",
        "MESSAGE": [ord("o"), ord("k"), 0xC3, 0xA9],  # "oké" in UTF-8
        "_HOSTNAME": "host",
    }

    def _runner(_argv: list[str]) -> Any:
        return _completed(stdout=json.dumps(payload))

    collector = JournaldCollector(runner=_runner, binary_path="/usr/bin/journalctl")
    entries = collector.read_recent()
    assert entries[0].message == "oké"


def test_entry_without_unit_falls_back_to_syslog_identifier() -> None:
    payload = {
        "__REALTIME_TIMESTAMP": "1700000000000000",
        "SYSLOG_IDENTIFIER": "myapp",
        "PRIORITY": "6",
        "MESSAGE": "hello",
    }

    def _runner(_argv: list[str]) -> Any:
        return _completed(stdout=json.dumps(payload))

    collector = JournaldCollector(runner=_runner, binary_path="/usr/bin/journalctl")
    entries = collector.read_recent()
    assert entries[0].unit == "myapp"


def test_returns_empty_when_journalctl_exits_nonzero() -> None:
    def _runner(_argv: list[str]) -> Any:
        return _completed(returncode=1, stderr="boom")

    collector = JournaldCollector(runner=_runner, binary_path="/usr/bin/journalctl")
    assert collector.read_recent() == []


def test_returns_empty_when_subprocess_times_out() -> None:
    def _runner(argv: list[str]) -> Any:
        raise subprocess.TimeoutExpired(argv, timeout=1)

    collector = JournaldCollector(runner=_runner, binary_path="/usr/bin/journalctl")
    assert collector.read_recent() == []


def test_malformed_lines_are_skipped() -> None:
    valid = _journal_payload(ts_micro=1_700_000_000_000_000, message="real")

    def _runner(_argv: list[str]) -> Any:
        return _completed(stdout=f"\nnot-json\n{valid}\n")

    collector = JournaldCollector(runner=_runner, binary_path="/usr/bin/journalctl")
    entries = collector.read_recent()
    assert [e.message for e in entries] == ["real"]
