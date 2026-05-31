"""Process value object."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessInfo:
    """Lightweight snapshot of a single OS process.

    Memory is the resident-set size in bytes. CPU percentage is normalised
    against the total available CPU (matching ``psutil.Process.cpu_percent``)
    and may exceed 100 % on multi-core processes.
    """

    pid: int
    name: str
    user: str
    cpu_pct: float
    mem_b: int
