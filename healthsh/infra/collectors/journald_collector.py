"""journald collector — shells out to ``journalctl -o json`` and parses entries.

We deliberately do not use the ``systemd`` Python bindings: they require a C
extension that is not consistently packaged across distros, and the wheels are
not on PyPI for every Python version we care about. ``journalctl`` is the
stable, always-available CLI on any systemd-based host. On hosts without
journalctl (containers, non-systemd distros) the collector returns an empty
list quietly so the UI can render its "journald is unavailable" state.

Reads are **incremental**: the collector caches the timestamp of the most
recently seen entry and passes it as ``--since=@<unix_seconds>`` on the next
call, so each tick only pays for what is new since the last tick. The first
call uses a configurable lookback window (default 2 hours).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from healthsh.domain.log_entry import LogEntry

_LOG = logging.getLogger(__name__)

# Default lookback used on the very first read (no cached cursor yet).
DEFAULT_LOOKBACK_S: int = 2 * 60 * 60

# Hard ceiling on how many entries one call may return — protects against
# pathological catch-up scenarios (the user came back from lunch).
_MAX_ENTRIES_PER_CALL: int = 5000

# Subprocess timeout (seconds) per journalctl invocation.
_SUBPROC_TIMEOUT_S: float = 5.0


# Injection seam — callers can substitute a fake runner in tests.
JournalctlRunner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def _default_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        timeout=_SUBPROC_TIMEOUT_S,
    )


def _decode_message(raw: Any) -> str:
    """Decode a journald ``MESSAGE`` field into a Python ``str``.

    journalctl returns the message either as a UTF-8 string or — for binary
    payloads — as a list of integers (one per byte). Both shapes are handled
    here with a tolerant ``errors='replace'`` so a single malformed log entry
    cannot crash the worker.
    """
    if raw is None:
        return ""
    if isinstance(raw, list):
        try:
            return bytes(int(b) & 0xFF for b in raw).decode("utf-8", errors="replace")
        except (TypeError, ValueError):
            return ""
    return str(raw)


def _parse_ts(microseconds_str: str) -> datetime:
    """Convert journald's microsecond-precision string into a UTC ``datetime``."""
    try:
        micro = int(microseconds_str)
    except (TypeError, ValueError):
        return datetime.now(tz=UTC)
    return datetime.fromtimestamp(micro / 1_000_000.0, tz=UTC)


def _parse_priority(raw: Any) -> int:
    """journald reports priority as a string in JSON; default to 6 (info)."""
    if raw is None:
        return 6
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 6


def _entry_from_json(payload: dict[str, Any]) -> LogEntry:
    unit = (
        payload.get("_SYSTEMD_UNIT")
        or payload.get("UNIT")
        or payload.get("SYSLOG_IDENTIFIER")
        or ""
    )
    return LogEntry(
        ts=_parse_ts(payload.get("__REALTIME_TIMESTAMP", "")),
        unit=str(unit),
        priority=_parse_priority(payload.get("PRIORITY")),
        message=_decode_message(payload.get("MESSAGE")),
        hostname=str(payload.get("_HOSTNAME", "") or ""),
    )


class JournaldCollector:
    """Incremental journald reader.

    The collector caches the timestamp of the last entry it returned so the
    next call only fetches what is new. Filters by ``units`` (one or many)
    and ``max_priority`` (drop entries strictly above the integer).

    Hosts without ``journalctl`` are first-class: ``read_recent`` returns an
    empty list and ``is_available()`` reports ``False`` so the Logs screen
    can render its empty state instead of an error.
    """

    def __init__(
        self,
        *,
        runner: JournalctlRunner | None = None,
        lookback_s: int = DEFAULT_LOOKBACK_S,
        binary_path: str | None = None,
    ) -> None:
        if lookback_s <= 0:
            raise ValueError(f"lookback_s must be positive, got {lookback_s!r}")
        self._runner: JournalctlRunner = runner or _default_runner
        self._lookback_s: int = int(lookback_s)
        self._binary_path: str | None = binary_path
        # Last timestamp returned (UTC). None until the first successful call.
        self._cursor_ts: datetime | None = None

    # ------------------------------------------------------------------ API

    def is_available(self) -> bool:
        """Return ``True`` when ``journalctl`` is on the PATH (or pinned)."""
        if self._binary_path is not None:
            return True
        return shutil.which("journalctl") is not None

    def lookback_s(self) -> int:
        """Return the first-call lookback window in seconds."""
        return self._lookback_s

    def cursor_ts(self) -> datetime | None:
        """Return the cursor (timestamp of the last entry returned, or None)."""
        return self._cursor_ts

    def read_recent(
        self,
        *,
        units: list[str] | None = None,
        max_priority: int | None = None,
        now: datetime | None = None,
    ) -> list[LogEntry]:
        """Return new entries since the last successful call.

        Args:
            units: Optional list of unit names (passed as ``--unit=...``).
            max_priority: When set, only entries with ``priority <= max``
                are returned (e.g. ``4`` keeps warnings + errors).
            now: Override the wall clock — used by tests for determinism.

        Returns:
            Newly-seen entries in chronological order (oldest first). On
            failure / when journalctl is unavailable, returns ``[]``.
        """
        if not self.is_available():
            return []
        argv = self._build_argv(units, max_priority, now or datetime.now(tz=UTC))
        try:
            result = self._runner(argv)
        except (subprocess.TimeoutExpired, OSError) as exc:
            _LOG.debug("journalctl invocation failed: %s", exc)
            return []
        if result.returncode != 0:
            _LOG.debug("journalctl exited %d: %s", result.returncode, (result.stderr or "")[:200])
            return []
        entries = self._parse_stdout(result.stdout)
        if entries:
            self._cursor_ts = entries[-1].ts
        return entries

    # --------------------------------------------------------------- helpers

    def _build_argv(
        self,
        units: list[str] | None,
        max_priority: int | None,
        now: datetime,
    ) -> list[str]:
        binary = self._binary_path or "journalctl"
        argv: list[str] = [binary, "--output=json", "--no-pager"]

        since_dt = self._cursor_ts
        if since_dt is None:
            since_dt = datetime.fromtimestamp(now.timestamp() - float(self._lookback_s), tz=UTC)
        # `--since="@<epoch>"` is the supported epoch-seconds form.
        argv.append(f"--since=@{int(since_dt.timestamp())}")

        if max_priority is not None:
            argv.append(f"--priority={int(max_priority)}")
        if units:
            for unit in units:
                argv.append(f"--unit={unit}")
        # Cap the read so a giant backlog cannot stall the slow worker.
        argv.append(f"--lines={_MAX_ENTRIES_PER_CALL}")
        return argv

    def _parse_stdout(self, stdout: str) -> list[LogEntry]:
        out: list[LogEntry] = []
        for line in stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                _LOG.debug("skipping malformed journalctl line")
                continue
            if not isinstance(payload, dict):
                continue
            try:
                entry = _entry_from_json(payload)
            except (TypeError, ValueError):
                _LOG.debug("skipping malformed journald entry", exc_info=True)
                continue
            # Drop entries at-or-before the cursor when we've already seen them
            # (--since is inclusive of equal timestamps).
            if self._cursor_ts is not None and entry.ts <= self._cursor_ts:
                continue
            out.append(entry)
        out.sort(key=lambda e: e.ts)
        return out
