"""Multi-vendor GPU collectors.

The vendor-agnostic entry point is :func:`detect.collect_gpu`. Each vendor
module exposes a ``collect_<vendor>`` function that returns a
:class:`healthsh.domain.metrics.GpuMetric` or ``None`` (never raises).
"""

from healthsh.infra.collectors.gpu.detect import collect_gpu

__all__ = ["collect_gpu"]
