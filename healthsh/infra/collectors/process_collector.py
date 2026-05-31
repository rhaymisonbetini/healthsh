"""Process collector via psutil — top-N by memory and full listing.

Both functions tolerate the natural race where a process exits during
iteration (``psutil.NoSuchProcess`` / ``AccessDenied``) and simply skip the
dead entry. Neither function ever raises for routine failures — the worst
case is an empty list.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import psutil

from healthsh.domain.process import ProcessInfo

_LOG = logging.getLogger(__name__)

# psutil attributes pulled in a single iteration to minimise syscalls.
_ATTRS: tuple[str, ...] = ("pid", "name", "username", "memory_info", "cpu_percent")


def _iter_process_info() -> Iterator[ProcessInfo]:
    """Yield :class:`ProcessInfo` for every visible process, swallowing race errors."""
    for proc in psutil.process_iter(_ATTRS):
        info = proc.info
        try:
            mem_info = info.get("memory_info")
            mem_b = int(mem_info.rss) if mem_info is not None else 0
            cpu_pct = float(info.get("cpu_percent") or 0.0)
            yield ProcessInfo(
                pid=int(info.get("pid") or 0),
                name=str(info.get("name") or ""),
                user=str(info.get("username") or ""),
                cpu_pct=cpu_pct,
                mem_b=mem_b,
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            _LOG.debug("process disappeared during iteration", exc_info=True)
            continue


def top_n_by_memory(n: int = 5) -> list[ProcessInfo]:
    """Return the top ``n`` processes by resident memory, descending.

    Args:
        n: Maximum entries to return. Must be > 0.
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n!r}")
    all_processes = list(_iter_process_info())
    all_processes.sort(key=lambda p: p.mem_b, reverse=True)
    return all_processes[:n]


def list_all() -> list[ProcessInfo]:
    """Return every visible process unsorted (used by the System screen table)."""
    return list(_iter_process_info())
