"""Backwards-compatible re-export of the vendor-agnostic GPU collector.

The real implementation lives in :mod:`healthsh.infra.collectors.gpu` (issue
#5 split it per vendor: NVIDIA, AMD, Intel). This module exists so callers
that imported the original flat ``gpu_collector`` keep working.
"""

from healthsh.infra.collectors.gpu.detect import collect_gpu

__all__ = ["collect_gpu"]
