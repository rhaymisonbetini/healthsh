"""Detection-chain tests for :func:`healthsh.infra.collectors.gpu.collect_gpu`."""

from __future__ import annotations

from healthsh.domain.metrics import GpuMetric
from healthsh.infra.collectors.gpu.detect import collect_gpu


def _stub(metric: GpuMetric | None):
    def _probe() -> GpuMetric | None:
        return metric

    return _probe


def _raises(_msg: str = "boom"):
    def _probe() -> GpuMetric | None:
        raise RuntimeError("synthetic probe failure")

    return _probe


def test_returns_first_hit_in_chain() -> None:
    nvidia = GpuMetric("nvidia", "RTX 4070", 12.0, None, None, 48.0)
    amd = GpuMetric("amd", "Radeon", 30.0, None, None, 52.0)
    assert collect_gpu(probes=(_stub(nvidia), _stub(amd))) is nvidia


def test_falls_through_to_next_when_first_returns_none() -> None:
    amd = GpuMetric("amd", "Radeon", 30.0, None, None, 52.0)
    assert collect_gpu(probes=(_stub(None), _stub(amd))) is amd


def test_returns_none_when_all_probes_return_none() -> None:
    assert collect_gpu(probes=(_stub(None), _stub(None), _stub(None))) is None


def test_swallows_probe_exceptions_and_continues() -> None:
    intel = GpuMetric("intel", "iGPU", 22.0, None, None, None)
    assert collect_gpu(probes=(_raises(), _stub(None), _stub(intel))) is intel


def test_empty_probe_chain_returns_none() -> None:
    assert collect_gpu(probes=()) is None


def test_default_chain_does_not_raise_on_realistic_machine() -> None:
    """Smoke: the real default chain (nvidia/amd/intel) must never raise."""
    # Whatever the host actually has is fine — we just need a non-raising call.
    result = collect_gpu()
    assert result is None or result.vendor in {"nvidia", "amd", "intel"}
