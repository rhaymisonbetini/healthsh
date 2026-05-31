"""Pure formatters used at the UI / AI banner edge.

Everything here is stateless, deterministic, and Qt-free so it can be reused
from tests and from the analysis engine without instantiating an app.
"""

from __future__ import annotations

from healthsh.domain.metrics import GpuMetric

_GIB: int = 1024 * 1024 * 1024


def bytes_to_gb(n: int) -> float:
    """Convert bytes to binary gibibytes (GiB), keeping decimal precision."""
    if n < 0:
        raise ValueError("bytes_to_gb requires a non-negative integer")
    return n / _GIB


def format_pct(value: float, *, decimals: int = 0) -> str:
    """Format a 0-100 percentage as ``"34%"`` (default) or with decimals."""
    return f"{value:.{decimals}f}%"


def format_temp_c(value: float | None) -> str:
    """Format a Celsius temperature as ``"48°C"`` or ``"n/a"`` when unknown."""
    if value is None:
        return "n/a"
    return f"{round(value)}°C"


def format_uptime(seconds: int) -> str:
    """Format ``seconds`` of uptime as a compact ``"Nd Nh"`` / ``"Nh Nm"`` string."""
    if seconds < 0:
        raise ValueError("format_uptime requires a non-negative integer")
    days, rem = divmod(seconds, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_gpu_label(gpu: GpuMetric | None) -> str:
    """Return the human-readable label shown below the GPU gauge.

    Per HEALTHSH_ROADMAP §5.1 and the updated issue #10:

    - NVIDIA / AMD with a temperature sensor: ``"<vendor> · 48°C"``.
    - Intel iGPU (no temp / shared VRAM): ``"Intel · shared"``.
    - ``None`` (no GPU): empty string — the UI uses that as the signal to
      hide the GPU section entirely.
    """
    if gpu is None:
        return ""
    vendor_label = {"nvidia": "NVIDIA", "amd": "AMD", "intel": "Intel"}[gpu.vendor]
    if gpu.vendor == "intel" or gpu.temp_c is None:
        suffix = "shared" if gpu.vendor == "intel" else "n/a"
        return f"{vendor_label} · {suffix}"
    return f"{vendor_label} · {format_temp_c(gpu.temp_c)}"
