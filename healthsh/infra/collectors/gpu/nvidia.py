"""NVIDIA GPU collector via ``nvidia-smi``.

Detection: the ``nvidia-smi`` binary must be discoverable on ``PATH``. Runtime
is a single subprocess call returning a CSV row that we parse into a
:class:`GpuMetric`. The function never raises — any failure produces ``None``
so the higher-level detection chain can move on to the next vendor.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable

from healthsh.domain.metrics import GpuMetric

_LOG = logging.getLogger(__name__)

# Default ``subprocess.run`` shape — injectable for tests.
Runner = Callable[..., subprocess.CompletedProcess[str]]

_SMI_CMD: tuple[str, ...] = (
    "nvidia-smi",
    "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
    "--format=csv,noheader,nounits",
)

# Subprocess timeout (seconds) — nvidia-smi is normally fast but a wedged
# driver can hang; bound the wait so the metrics worker never blocks.
_SMI_TIMEOUT: float = 2.0


def _parse_value(raw: str) -> float | None:
    """Parse one CSV cell into a float; return ``None`` for ``[N/A]`` / blanks."""
    stripped = raw.strip()
    if not stripped or stripped.lower().startswith("[n/a"):
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def collect_nvidia(
    *,
    runner: Runner = subprocess.run,
    smi_path: str | None = None,
) -> GpuMetric | None:
    """Return a :class:`GpuMetric` for the first NVIDIA GPU, or ``None``.

    Args:
        runner: Subprocess runner (defaults to :func:`subprocess.run`).
        smi_path: Explicit path to ``nvidia-smi`` (defaults to PATH discovery).

    Returns:
        A :class:`GpuMetric` with ``vendor="nvidia"``, or ``None`` if no
        usable NVIDIA GPU is detected.
    """
    executable = smi_path or shutil.which("nvidia-smi")
    if executable is None:
        return None

    try:
        completed = runner(
            (executable, *_SMI_CMD[1:]),
            capture_output=True,
            text=True,
            timeout=_SMI_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _LOG.debug("nvidia-smi invocation failed: %s", exc)
        return None

    if completed.returncode != 0 or not completed.stdout.strip():
        _LOG.debug("nvidia-smi non-zero exit (%s): %s", completed.returncode, completed.stderr)
        return None

    first_line = completed.stdout.splitlines()[0]
    parts = [cell.strip() for cell in first_line.split(",")]
    if len(parts) < 5:
        _LOG.debug("nvidia-smi unexpected csv: %r", first_line)
        return None

    name = parts[0] or "NVIDIA GPU"
    util_pct = _parse_value(parts[1])
    mem_used_mib = _parse_value(parts[2])
    mem_total_mib = _parse_value(parts[3])
    temp_c = _parse_value(parts[4])

    mem_used_b = int(mem_used_mib * 1024 * 1024) if mem_used_mib is not None else None
    mem_total_b = int(mem_total_mib * 1024 * 1024) if mem_total_mib is not None else None

    return GpuMetric(
        vendor="nvidia",
        name=name,
        util_pct=util_pct,
        mem_used_b=mem_used_b,
        mem_total_b=mem_total_b,
        temp_c=temp_c,
    )
