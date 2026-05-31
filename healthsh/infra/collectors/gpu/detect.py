"""Vendor-agnostic GPU detection chain.

Probes NVIDIA, AMD, then Intel in that order and returns the first vendor that
successfully reports a :class:`GpuMetric`. Returns ``None`` when no GPU is
detected, which the UI uses to hide the GPU section entirely.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from healthsh.domain.metrics import GpuMetric
from healthsh.infra.collectors.gpu.amd import collect_amd
from healthsh.infra.collectors.gpu.intel import collect_intel
from healthsh.infra.collectors.gpu.nvidia import collect_nvidia

_LOG = logging.getLogger(__name__)

_ProbeFn = Callable[[], GpuMetric | None]


def collect_gpu(probes: tuple[_ProbeFn, ...] | None = None) -> GpuMetric | None:
    """Run the GPU detection chain and return the first successful reading.

    Args:
        probes: Optional override sequence of zero-arg probe callables. Tests
            inject deterministic stubs; production code passes ``None`` and
            gets the default ``(nvidia, amd, intel)`` chain.
    """
    # Use the explicit ``is None`` check (not ``probes or ...``) so callers can
    # pass an empty tuple to mean "probe nothing" — handy in tests.
    chain: tuple[_ProbeFn, ...] = (
        (collect_nvidia, collect_amd, collect_intel) if probes is None else probes
    )
    for probe in chain:
        try:
            result = probe()
        except Exception:  # noqa: BLE001 — never propagate from a probe
            _LOG.debug("gpu probe %s raised", probe.__name__, exc_info=True)
            continue
        if result is not None:
            return result
    return None
