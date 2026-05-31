"""Docker container value objects.

Minimal shape for Sprint 1 — enough for the Dashboard's containers summary
(name + running flag + memory). The full :class:`ContainerInfo` (image tag,
ports, uptime) and :class:`DockerStatus` arrive with the Docker collector in
issue #17 and reuse this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContainerInfo:
    """Brief information about a single container."""

    id: str
    name: str
    image: str = ""
    status: str = "stopped"  # 'running' | 'stopped' | 'paused' | other docker statuses
    ports: tuple[str, ...] = field(default_factory=tuple)
    uptime_s: int = 0

    @property
    def is_running(self) -> bool:
        """Convenience flag — ``True`` when the container reports as running."""
        return self.status == "running"


@dataclass(frozen=True)
class ContainerStats:
    """Live resource stats for a container (populated by the Docker collector)."""

    cpu_pct: float
    mem_used_b: int
    mem_limit_b: int | None = None
