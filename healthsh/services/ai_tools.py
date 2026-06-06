"""Tool functions exposed to the LLM agent.

Each function returns plain JSON-friendly Python (dicts / lists / scalars) so
the agent base can serialise them straight into the next model turn without
custom encoders. The tool layer is intentionally thin — the heavy lifting
lives in :class:`HistoryService` (#23) and :class:`AnalysisEngine` (#24).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from healthsh.domain.container import ContainerInfo, ContainerStats
from healthsh.domain.log_entry import LogEntry
from healthsh.infra.collectors.docker_collector import DockerCollector
from healthsh.infra.collectors.journald_collector import JournaldCollector
from healthsh.infra.collectors.process_collector import list_all as list_all_processes
from healthsh.services.history_service import HistoryService

_LOG = logging.getLogger(__name__)

# How many log entries the model is allowed to receive at once.
DEFAULT_MAX_LOG_ENTRIES: int = 200

# JSON-Schema-ish tool definitions. The shape mirrors what OpenAI / Anthropic
# tool-calling APIs accept; backends translate this into their native form.
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_metrics",
        "description": (
            "Return time-series metric samples between two ISO-8601 timestamps. "
            "Use this to answer questions about CPU / RAM / disk / GPU history."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": [
                        "cpu_pct",
                        "mem_pct",
                        "mem_used_b",
                        "disk_used_b",
                        "disk_pct",
                        "gpu_pct",
                        "gpu_temp_c",
                    ],
                },
                "since": {"type": "string", "description": "ISO-8601 timestamp"},
                "until": {"type": "string", "description": "ISO-8601 timestamp"},
            },
            "required": ["metric", "since", "until"],
        },
    },
    {
        "name": "get_logs",
        "description": (
            "Return recent journald entries in a time window. Use to investigate "
            "errors that coincide with a metric spike or container event."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filter_units": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of systemd unit names",
                },
                "max_priority": {
                    "type": "integer",
                    "description": "Drop entries with priority > this (0–7)",
                },
                "since": {"type": "string"},
                "until": {"type": "string"},
                "max_entries": {"type": "integer", "default": DEFAULT_MAX_LOG_ENTRIES},
            },
            "required": ["since", "until"],
        },
    },
    {
        "name": "get_containers",
        "description": "List Docker containers visible to the local daemon.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_processes",
        "description": "Return the top-N OS processes sorted by memory or CPU.",
        "parameters": {
            "type": "object",
            "properties": {
                "top_n_by": {
                    "type": "string",
                    "enum": ["memory", "cpu"],
                    "default": "memory",
                },
                "n": {"type": "integer", "default": 10},
            },
        },
    },
]


def _parse_iso(text: str) -> datetime:
    """Parse an ISO-8601 string into a UTC datetime (Z and offsets accepted)."""
    cleaned = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def get_metrics(
    history: HistoryService,
    *,
    metric: str,
    since: str,
    until: str,
) -> dict[str, Any]:
    """Return ``{"metric": ..., "samples": [{"ts": iso, "value": v}, ...]}``."""
    since_dt = _parse_iso(since)
    until_dt = _parse_iso(until)
    rows = history.query(metric, since=since_dt, until=until_dt)
    return {
        "metric": metric,
        "since": since_dt.isoformat(),
        "until": until_dt.isoformat(),
        "samples": [{"ts": ts.isoformat(), "value": float(v)} for ts, v in rows],
    }


def get_logs(
    journald: JournaldCollector,
    *,
    filter_units: list[str] | None = None,
    max_priority: int | None = None,
    since: str | None = None,
    until: str | None = None,
    max_entries: int = DEFAULT_MAX_LOG_ENTRIES,
) -> list[dict[str, Any]]:
    """Return up to ``max_entries`` log dicts in chronological order.

    ``since`` / ``until`` are advisory: the collector returns entries since its
    internal cursor, so the tool slices the result by timestamp afterwards.
    """
    entries = journald.read_recent(units=filter_units, max_priority=max_priority)
    if since is not None:
        since_dt = _parse_iso(since)
        entries = [e for e in entries if e.ts >= since_dt]
    if until is not None:
        until_dt = _parse_iso(until)
        entries = [e for e in entries if e.ts <= until_dt]
    return [_log_entry_as_dict(e) for e in entries[:max_entries]]


def get_containers(docker: DockerCollector) -> dict[str, Any]:
    """Return Docker availability + container list as JSON-friendly dicts."""
    status, infos = docker.list_containers()
    if not status.is_ok:
        return {
            "status": status.kind,
            "detail": status.detail,
            "containers": [],
        }
    pairs = docker.stats_pairs(infos)
    return {
        "status": "ok",
        "containers": [_container_pair_as_dict(info, stats) for info, stats in pairs],
    }


def get_processes(
    *,
    top_n_by: str = "memory",
    n: int = 10,
) -> list[dict[str, Any]]:
    """Return the top ``n`` processes sorted by memory or CPU."""
    if n <= 0:
        raise ValueError(f"n must be positive, got {n!r}")
    if top_n_by not in ("memory", "cpu"):
        raise ValueError(f"top_n_by must be 'memory' or 'cpu', got {top_n_by!r}")
    processes = list_all_processes()
    if top_n_by == "memory":
        processes = sorted(processes, key=lambda p: p.mem_b, reverse=True)
    else:
        processes = sorted(processes, key=lambda p: p.cpu_pct, reverse=True)
    return [
        {
            "pid": p.pid,
            "name": p.name,
            "user": p.user,
            "cpu_pct": p.cpu_pct,
            "mem_b": p.mem_b,
        }
        for p in processes[:n]
    ]


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _log_entry_as_dict(entry: LogEntry) -> dict[str, Any]:
    return {
        "ts": entry.ts.isoformat(),
        "unit": entry.unit,
        "priority": entry.priority,
        "message": entry.message,
        "hostname": entry.hostname,
    }


def _container_pair_as_dict(info: ContainerInfo, stats: ContainerStats | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": info.id,
        "name": info.name,
        "image": info.image,
        "status": info.status,
        "ports": list(info.ports),
        "uptime_s": info.uptime_s,
    }
    if stats is not None:
        out["cpu_pct"] = stats.cpu_pct
        out["mem_used_b"] = stats.mem_used_b
        out["mem_limit_b"] = stats.mem_limit_b
    return out


def summarise_metrics_result(payload: dict[str, Any]) -> str:
    """Build a short chip label from a :func:`get_metrics` result payload."""
    metric = payload.get("metric", "")
    samples = payload.get("samples", [])
    count = len(samples)
    since = payload.get("since", "")
    until = payload.get("until", "")
    return f"read {metric} · {count} samples · {since[11:16]}–{until[11:16]}"


def summarise_logs_result(rows: Iterable[dict[str, Any]]) -> str:
    """Build a short chip label from a :func:`get_logs` result."""
    rows_list = list(rows)
    if not rows_list:
        return "read journald · 0 entries"
    priorities = {int(r["priority"]) for r in rows_list}
    severity = "err" if any(p <= 3 for p in priorities) else ("warn" if 4 in priorities else "info")
    return f"read journald ({severity}) · {len(rows_list)} entries"


def summarise_containers_result(payload: dict[str, Any]) -> str:
    """Build a short chip label from a :func:`get_containers` result."""
    if payload.get("status") != "ok":
        return f"docker · {payload.get('status', 'unknown')}"
    return f"listed containers · {len(payload.get('containers', []))}"


def summarise_processes_result(rows: list[dict[str, Any]]) -> str:
    """Build a short chip label from a :func:`get_processes` result."""
    return f"top {len(rows)} processes"
