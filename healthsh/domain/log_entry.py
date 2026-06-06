"""Log-entry value objects produced by the journald collector.

journald reports each log line with a priority integer (0–7), a unit
(``foo.service`` / ``kernel`` / ``SYSLOG_IDENTIFIER``), a timestamp and a
message body. Healthsh keeps that shape intact in :class:`LogEntry`. UI
filtering rides on :class:`LogFilter`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class LogEntry:
    """One journald entry, normalised into a typed value object.

    Attributes:
        ts: Entry timestamp (UTC).
        unit: Reporting unit — ``_SYSTEMD_UNIT`` if present, else
            ``SYSLOG_IDENTIFIER``, else an empty string.
        priority: journald priority — 0 (emerg) to 7 (debug).
        message: Decoded message body. Binary-bytes messages are decoded with
            ``errors="replace"``.
        hostname: ``_HOSTNAME`` field (empty when not present).
    """

    ts: datetime
    unit: str
    priority: int
    message: str
    hostname: str = ""


@dataclass(frozen=True)
class LogFilter:
    """User-facing filter applied by the Logs screen.

    Attributes:
        units: Restrict to the listed units. ``None`` means "all units".
        categories: Severity categories to display. Empty means "none" (the
            user has unchecked every pill — the list is blank). Categories are
            the strings from :mod:`healthsh.core.log_severity`:
            ``"err"`` / ``"warn"`` / ``"info"`` / ``"debug"``.
    """

    units: tuple[str, ...] | None = None
    categories: frozenset[str] = field(default_factory=frozenset)
