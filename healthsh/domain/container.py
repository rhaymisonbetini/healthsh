"""Docker container value objects.

These types are consumed by both the Dashboard's containers summary (#9) and
the Docker screen (#19). All entities are frozen so they can flow across
threads (the slow worker → the UI signal pipeline) without ownership pitfalls.

:class:`DockerStatus` is the typed answer to the question *"is Docker
available right now?"*. The UI in #19 swaps between *cards mode* and a calm,
informational empty-state screen based on this status — there is no exception
path on the rendering side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DockerStatusKind = Literal[
    "ok",
    "not_installed",
    "daemon_down",
    "permission_denied",
    "unknown",
]


@dataclass(frozen=True)
class DockerStatus:
    """Snapshot of the host's Docker availability.

    The collector layer is *the* source of truth for this — the UI never tries
    to interpret docker-py exceptions itself. ``detail`` is a short
    diagnostic message (often the underlying exception text) intended for the
    ``unknown`` empty state.
    """

    kind: DockerStatusKind
    detail: str = ""

    @property
    def is_ok(self) -> bool:
        """Convenience flag — ``True`` when Docker is reachable."""
        return self.kind == "ok"


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
