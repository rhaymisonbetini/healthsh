"""NVIDIA GPU collector tests — runner injection, csv parsing, error paths."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from healthsh.infra.collectors.gpu.nvidia import collect_nvidia


def _fake_runner(stdout: str = "", returncode: int = 0):
    """Build a runner that always returns the supplied stdout / returncode."""

    def _run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")

    return _run


def test_returns_none_when_smi_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """No nvidia-smi on PATH and no override → None."""
    monkeypatch.setattr("shutil.which", lambda _name: None)
    assert collect_nvidia() is None


def test_parses_typical_smi_output() -> None:
    line = "NVIDIA GeForce RTX 4070, 24, 3072, 8192, 56\n"
    metric = collect_nvidia(runner=_fake_runner(line), smi_path="/usr/bin/nvidia-smi")
    assert metric is not None
    assert metric.vendor == "nvidia"
    assert metric.name == "NVIDIA GeForce RTX 4070"
    assert metric.util_pct == 24.0
    assert metric.mem_used_b == 3072 * 1024 * 1024
    assert metric.mem_total_b == 8192 * 1024 * 1024
    assert metric.temp_c == 56.0


def test_handles_na_cells_gracefully() -> None:
    line = "NVIDIA Tesla T4, [N/A], 0, 16384, [N/A]\n"
    metric = collect_nvidia(runner=_fake_runner(line), smi_path="/usr/bin/nvidia-smi")
    assert metric is not None
    assert metric.util_pct is None
    assert metric.mem_used_b == 0
    assert metric.mem_total_b == 16384 * 1024 * 1024
    assert metric.temp_c is None


def test_returns_none_on_non_zero_exit() -> None:
    metric = collect_nvidia(
        runner=_fake_runner("garbage", returncode=1),
        smi_path="/usr/bin/nvidia-smi",
    )
    assert metric is None


def test_returns_none_on_empty_output() -> None:
    metric = collect_nvidia(runner=_fake_runner(""), smi_path="/usr/bin/nvidia-smi")
    assert metric is None


def test_returns_none_on_short_csv() -> None:
    metric = collect_nvidia(runner=_fake_runner("NVIDIA, 10, 100"), smi_path="/usr/bin/nvidia-smi")
    assert metric is None


def test_returns_none_on_subprocess_failure() -> None:
    def _raises(*_a: Any, **_kw: Any):
        raise FileNotFoundError("no such file")

    assert collect_nvidia(runner=_raises, smi_path="/usr/bin/nvidia-smi") is None


def test_returns_none_on_timeout() -> None:
    def _timeout(*_a: Any, **_kw: Any):
        raise subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=2.0)

    assert collect_nvidia(runner=_timeout, smi_path="/usr/bin/nvidia-smi") is None
