"""Docker collector — typed :class:`DockerStatus` + container list/stats/actions.

The collector is the single source of truth for *"can we reach Docker right
now?"*. Detection returns a typed :class:`DockerStatus` per the table in
issue #17:

================  =====================================================
``kind``           when
================  =====================================================
``ok``             ``docker.from_env()`` + ``client.ping()`` succeed
``not_installed``  no ``docker`` binary AND no ``/var/run/docker.sock``
``daemon_down``    binary or socket present, but the daemon is not up
``permission_denied`` socket exists but ``ping`` raises permission denied
``unknown``        any other failure (logged)
================  =====================================================

Re-probing is cheap when the status is bad (every 60 s — the UI recovers
within a minute of the user fixing the issue) and lazy when ok (only re-probe
on a request failure). Detection is wrapped in a callable injection seam so
tests can drive every branch without a real Docker daemon.
"""

from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from healthsh.domain.container import ContainerInfo, ContainerStats, DockerStatus

_LOG = logging.getLogger(__name__)

# Re-probe interval (seconds) when the cached status is not ok.
_REPROBE_INTERVAL_S: float = 60.0

# Default socket path used to distinguish "not installed" from "daemon down".
_DOCKER_SOCKET: Path = Path("/var/run/docker.sock")


# ---------------------------------------------------------------------------
# Optional docker-py import — kept lazy so the test for "not_installed" can
# run even on machines without docker-py available, and so the module imports
# cleanly in the layered packages test.
# ---------------------------------------------------------------------------
try:
    import docker  # type: ignore[import-untyped]
    from docker.errors import DockerException  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - import is exercised on dev boxes
    docker = None  # type: ignore[assignment]
    DockerException = Exception  # type: ignore[assignment, misc]


# Type alias for the client factory injection seam — returns a docker.DockerClient
# in production and a fake in tests.
ClientFactory = Callable[[], Any]


def _default_client_factory() -> Any:
    """Production client factory: ``docker.from_env()`` (raises on missing daemon)."""
    if docker is None:
        raise RuntimeError("docker-py is not importable")
    return docker.from_env()


def _now() -> float:
    """Wall-clock helper kept as a single seam for monkeypatching in tests."""
    return time.monotonic()


def _classify_failure(exc: BaseException) -> DockerStatus:
    """Map a connection failure to the closest :class:`DockerStatus` kind."""
    text = str(exc).lower()
    if "permission denied" in text:
        return DockerStatus(kind="permission_denied", detail=str(exc))
    if "connection refused" in text or "no such file or directory" in text:
        # Socket exists / binary exists, daemon is down.
        return DockerStatus(kind="daemon_down", detail=str(exc))
    return DockerStatus(kind="daemon_down", detail=str(exc))


class DockerCollector:
    """Stateful collector that owns the cached :class:`DockerStatus`.

    The cache lives on the instance so a long-running slow worker re-uses the
    same probe schedule across ticks. The collector is *not* thread-safe by
    itself — it is intended to be driven exclusively by the slow worker.
    """

    def __init__(
        self,
        *,
        client_factory: ClientFactory | None = None,
        socket_path: Path | None = None,
        clock: Callable[[], float] = _now,
    ) -> None:
        self._factory: ClientFactory = client_factory or _default_client_factory
        self._socket_path: Path = socket_path or _DOCKER_SOCKET
        self._clock: Callable[[], float] = clock
        self._client: Any = None
        self._cached_status: DockerStatus | None = None
        self._last_probe_at: float = -1.0

    # ------------------------------------------------------------------ status

    def status(self) -> DockerStatus:
        """Return the current (cached) :class:`DockerStatus`, re-probing as needed."""
        now = self._clock()
        cached = self._cached_status
        if cached is None:
            return self._probe(now)
        if cached.kind != "ok" and now - self._last_probe_at >= _REPROBE_INTERVAL_S:
            return self._probe(now)
        return cached

    def force_recheck(self) -> DockerStatus:
        """Re-run the detection chain immediately (used by *Re-check now*)."""
        return self._probe(self._clock())

    def _probe(self, now: float) -> DockerStatus:
        old_kind = self._cached_status.kind if self._cached_status else None
        new_status = self._detect()
        self._cached_status = new_status
        self._last_probe_at = now
        if old_kind != new_status.kind:
            _LOG.info("docker status transition: %s -> %s", old_kind, new_status.kind)
        return new_status

    def _detect(self) -> DockerStatus:
        if docker is None or (shutil.which("docker") is None and not self._socket_path.exists()):
            self._client = None
            return DockerStatus(kind="not_installed", detail="docker not found on PATH or socket")
        try:
            client = self._factory()
            ok = client.ping()
        except PermissionError as exc:
            self._client = None
            return DockerStatus(kind="permission_denied", detail=str(exc))
        except DockerException as exc:
            self._client = None
            return _classify_failure(exc)
        except Exception as exc:  # noqa: BLE001 — unknown failure mode
            self._client = None
            _LOG.exception("unexpected docker probe failure")
            return DockerStatus(kind="unknown", detail=str(exc))

        if not ok:
            self._client = None
            return DockerStatus(kind="daemon_down", detail="ping returned falsy")

        self._client = client
        return DockerStatus(kind="ok", detail="")

    # ---------------------------------------------------------------- listing

    def list_containers(self) -> tuple[DockerStatus, list[ContainerInfo]]:
        """Return ``(status, items)``. ``items`` is always a list (possibly empty)."""
        status = self.status()
        if status.kind != "ok" or self._client is None:
            return status, []
        try:
            raw = self._client.containers.list(all=True)
        except Exception as exc:  # noqa: BLE001 — degrade to a transient daemon_down
            _LOG.warning("docker list raised; flipping to daemon_down: %s", exc)
            new_status = _classify_failure(exc)
            self._cached_status = new_status
            self._last_probe_at = self._clock()
            return new_status, []
        return status, [_container_info_from_raw(c) for c in raw]

    def stats_pairs(
        self,
        infos: list[ContainerInfo],
        *,
        max_workers: int = 4,
    ) -> list[tuple[ContainerInfo, ContainerStats | None]]:
        """Return ``(info, stats|None)`` pairs.

        Only **running** containers get a real ``ContainerStats`` — fetching
        ``stats(stream=False)`` per container is an HTTP round-trip and we
        keep the slow-worker tick under budget by running them concurrently.
        Stopped containers are paired with ``None``.
        """
        if not infos or self._client is None:
            return [(info, None) for info in infos]

        running = [info for info in infos if info.is_running]
        results: dict[str, ContainerStats | None] = {info.id: None for info in infos}

        if running:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                for info, stats in zip(
                    running, pool.map(self._stats_for_safe, running), strict=False
                ):
                    results[info.id] = stats
        return [(info, results[info.id]) for info in infos]

    def _stats_for_safe(self, info: ContainerInfo) -> ContainerStats | None:
        try:
            return self._stats_for(info.id)
        except Exception:  # noqa: BLE001 — one bad container must not poison the tick
            _LOG.debug("stats failed for %s", info.name, exc_info=True)
            return None

    def _stats_for(self, container_id: str) -> ContainerStats | None:
        if self._client is None:
            return None
        container = self._client.containers.get(container_id)
        raw = container.stats(stream=False)
        return _container_stats_from_raw(raw)

    # ---------------------------------------------------------------- actions

    def start(self, container_id: str) -> None:
        """Start a stopped container (no-op if Docker is unavailable)."""
        if self._client is None:
            return
        self._client.containers.get(container_id).start()

    def stop(self, container_id: str) -> None:
        """Stop a running container."""
        if self._client is None:
            return
        self._client.containers.get(container_id).stop()

    def restart(self, container_id: str) -> None:
        """Restart a container."""
        if self._client is None:
            return
        self._client.containers.get(container_id).restart()

    def tail_logs(self, container_id: str, n: int = 200) -> list[str]:
        """Return the last ``n`` log lines (stdout+stderr) as plain strings."""
        if n <= 0:
            raise ValueError(f"n must be positive, got {n!r}")
        if self._client is None:
            return []
        raw = self._client.containers.get(container_id).logs(tail=n)
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        return text.splitlines()


# ---------------------------------------------------------------------------
# Raw → domain conversions.
# ---------------------------------------------------------------------------


def _container_info_from_raw(raw: Any) -> ContainerInfo:
    """Translate a docker-py ``Container`` into the immutable :class:`ContainerInfo`."""
    attrs: dict[str, Any] = getattr(raw, "attrs", {}) or {}
    image_tag = ""
    image = attrs.get("Config", {}).get("Image") or ""
    if image:
        image_tag = image
    else:
        tags = getattr(raw, "image", None)
        tags_attr = getattr(tags, "tags", []) if tags is not None else []
        image_tag = tags_attr[0] if tags_attr else ""

    state = attrs.get("State", {}) or {}
    status = state.get("Status") or getattr(raw, "status", "stopped")

    started_at = state.get("StartedAt") or ""
    uptime_s = _parse_uptime_seconds(started_at, status)
    ports = _format_port_bindings(attrs.get("NetworkSettings", {}).get("Ports") or {})

    return ContainerInfo(
        id=getattr(raw, "id", "") or attrs.get("Id", ""),
        name=(getattr(raw, "name", None) or attrs.get("Name", "") or "").lstrip("/"),
        image=image_tag,
        status=str(status or "stopped"),
        ports=tuple(ports),
        uptime_s=uptime_s,
    )


def _container_stats_from_raw(raw: dict[str, Any]) -> ContainerStats | None:
    """Compute Docker-style CPU% and resident memory from a single stats payload."""
    cpu_stats = raw.get("cpu_stats") or {}
    pre_cpu = raw.get("precpu_stats") or {}
    cpu_total = (cpu_stats.get("cpu_usage") or {}).get("total_usage") or 0
    pre_total = (pre_cpu.get("cpu_usage") or {}).get("total_usage") or 0
    sys_total = cpu_stats.get("system_cpu_usage") or 0
    pre_sys = pre_cpu.get("system_cpu_usage") or 0
    online_cpus = cpu_stats.get("online_cpus") or len(
        (cpu_stats.get("cpu_usage") or {}).get("percpu_usage") or []
    )

    cpu_delta = cpu_total - pre_total
    sys_delta = sys_total - pre_sys
    if cpu_delta <= 0 or sys_delta <= 0 or not online_cpus:
        cpu_pct = 0.0
    else:
        cpu_pct = (cpu_delta / sys_delta) * float(online_cpus) * 100.0

    mem_stats = raw.get("memory_stats") or {}
    mem_used = int(mem_stats.get("usage") or 0)
    mem_limit = mem_stats.get("limit")
    return ContainerStats(
        cpu_pct=round(float(cpu_pct), 2),
        mem_used_b=mem_used,
        mem_limit_b=int(mem_limit) if mem_limit else None,
    )


def _parse_uptime_seconds(started_at: str, status: str) -> int:
    """Return seconds since the container started, or 0 when not running."""
    if not started_at or str(status).lower() != "running":
        return 0
    # Docker's StartedAt is RFC3339; strip nanoseconds beyond 6 digits + Z handling.
    from datetime import UTC, datetime

    cleaned = started_at
    if "." in cleaned:
        head, tail = cleaned.split(".", 1)
        # Tail looks like '1234567890Z' — Python only accepts up to 6 fractional digits.
        tail = tail.rstrip("Z")
        cleaned = f"{head}.{tail[:6]}+00:00"
    else:
        cleaned = cleaned.replace("Z", "+00:00")
    try:
        ts = datetime.fromisoformat(cleaned)
    except ValueError:
        return 0
    now = datetime.now(tz=UTC)
    return max(int((now - ts).total_seconds()), 0)


def _format_port_bindings(ports: dict[str, Any]) -> list[str]:
    """Render docker port bindings as ``"host:container"`` strings, sorted."""
    out: list[str] = []
    for container_port, bindings in (ports or {}).items():
        if not bindings:
            continue
        for binding in bindings:
            host_port = binding.get("HostPort") if isinstance(binding, dict) else None
            if host_port:
                out.append(f"{host_port}:{container_port.split('/')[0]}")
    return sorted(set(out))
