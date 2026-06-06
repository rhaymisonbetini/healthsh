"""SQLite metric history — schema, thread-safe writes, range queries, vacuum.

Append-only ``metric_samples`` table indexed on ``(ts, metric)`` is the source
of truth for the analysis engine in #24 (disk-fill forecast, memory-leak
detection) and the AI tools in #25. ``process_samples`` carries per-process
memory snapshots for leak detection.

Design choices:
- **stdlib only**: ``sqlite3`` from the standard library; no ORM, no async.
- **Single connection**: opened with ``check_same_thread=False`` and guarded
  by a :class:`threading.Lock` since the metrics worker writes from its own
  thread.
- **XDG-compliant path**: ``$XDG_DATA_HOME/healthsh/healthsh.db`` (falling
  back to ``~/.local/share/healthsh/healthsh.db``). Parent directory is
  created on first use.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
import threading
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

_LOG = logging.getLogger(__name__)

# Recognised metric series names. The schema itself does not constrain these
# — kept here as documentation and as the set the analysis engine queries.
KNOWN_METRICS: frozenset[str] = frozenset(
    {
        "cpu_pct",
        "mem_pct",
        "mem_used_b",
        "disk_used_b",
        "disk_pct",
        "gpu_pct",
        "gpu_temp_c",
    }
)


def default_db_path() -> Path:
    """Return the XDG-compliant default database path.

    Honours ``$XDG_DATA_HOME`` when set; otherwise falls back to
    ``~/.local/share/healthsh/healthsh.db``.
    """
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "healthsh" / "healthsh.db"


_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS metric_samples (
        ts INTEGER NOT NULL,
        metric TEXT NOT NULL,
        value REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_metric_samples_ts_metric ON metric_samples(ts, metric)",
    """
    CREATE TABLE IF NOT EXISTS process_samples (
        ts INTEGER NOT NULL,
        pid INTEGER NOT NULL,
        name TEXT NOT NULL,
        mem_b INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_process_samples_ts ON process_samples(ts)",
    "CREATE INDEX IF NOT EXISTS idx_process_samples_name_ts ON process_samples(name, ts)",
)


class MetricsStore:
    """Thread-safe SQLite wrapper for metric history persistence."""

    def __init__(self, *, path: Path | None = None) -> None:
        self._path: Path = path or default_db_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock: threading.Lock = threading.Lock()
        self._conn: sqlite3.Connection = sqlite3.connect(
            str(self._path),
            check_same_thread=False,
            isolation_level=None,  # autocommit; we open explicit transactions
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        for statement in _SCHEMA:
            self._conn.execute(statement)

    # ------------------------------------------------------------------ API

    def path(self) -> Path:
        """Return the on-disk DB path."""
        return self._path

    def close(self) -> None:
        """Close the underlying connection (idempotent)."""
        with self._lock, contextlib.suppress(sqlite3.ProgrammingError):
            self._conn.close()

    def insert_metrics(self, ts: datetime, rows: Iterable[tuple[str, float]]) -> int:
        """Insert one or more ``(metric, value)`` rows at a single timestamp.

        Returns the number of rows inserted. Skips rows where the value is
        ``None``/``NaN`` (the worker may have failed for that collector).
        """
        epoch_s = int(ts.timestamp())
        payload: list[tuple[int, str, float]] = []
        for metric, value in rows:
            if value is None:
                continue
            try:
                fvalue = float(value)
            except (TypeError, ValueError):
                continue
            if fvalue != fvalue:  # NaN check
                continue
            payload.append((epoch_s, str(metric), fvalue))
        if not payload:
            return 0
        with self._lock:
            self._conn.execute("BEGIN")
            self._conn.executemany(
                "INSERT INTO metric_samples (ts, metric, value) VALUES (?, ?, ?)",
                payload,
            )
            self._conn.execute("COMMIT")
        return len(payload)

    def insert_processes(
        self,
        ts: datetime,
        rows: Iterable[tuple[int, str, int]],
    ) -> int:
        """Insert ``(pid, name, mem_b)`` rows for a single timestamp.

        Returns the number of rows inserted. Used by #24's leak detector.
        """
        epoch_s = int(ts.timestamp())
        payload = [(epoch_s, int(pid), str(name), int(mem_b)) for pid, name, mem_b in rows]
        if not payload:
            return 0
        with self._lock:
            self._conn.execute("BEGIN")
            self._conn.executemany(
                "INSERT INTO process_samples (ts, pid, name, mem_b) VALUES (?, ?, ?, ?)",
                payload,
            )
            self._conn.execute("COMMIT")
        return len(payload)

    def query(
        self,
        metric: str,
        *,
        since: datetime,
        until: datetime,
    ) -> list[tuple[datetime, float]]:
        """Return ``(ts, value)`` rows for ``metric`` in ``[since, until]``."""
        if since > until:
            raise ValueError("since must be <= until")
        from datetime import UTC

        with self._lock:
            cur = self._conn.execute(
                "SELECT ts, value FROM metric_samples "
                "WHERE metric = ? AND ts >= ? AND ts <= ? ORDER BY ts ASC",
                (metric, int(since.timestamp()), int(until.timestamp())),
            )
            rows = cur.fetchall()
        return [(datetime.fromtimestamp(ts, tz=UTC), float(value)) for ts, value in rows]

    def query_aggregate(
        self,
        metric: str,
        *,
        since: datetime,
        until: datetime,
        bucket_s: int,
    ) -> list[tuple[datetime, float]]:
        """Return downsampled ``(bucket_start, avg_value)`` rows.

        Useful for charts that don't need every 1 Hz sample. Buckets average
        all samples falling within a ``bucket_s``-wide window.
        """
        if bucket_s <= 0:
            raise ValueError(f"bucket_s must be positive, got {bucket_s!r}")
        if since > until:
            raise ValueError("since must be <= until")
        from datetime import UTC

        with self._lock:
            cur = self._conn.execute(
                "SELECT (ts / ?) * ?, AVG(value) "
                "FROM metric_samples WHERE metric = ? AND ts >= ? AND ts <= ? "
                "GROUP BY ts / ? ORDER BY ts ASC",
                (
                    bucket_s,
                    bucket_s,
                    metric,
                    int(since.timestamp()),
                    int(until.timestamp()),
                    bucket_s,
                ),
            )
            rows = cur.fetchall()
        return [(datetime.fromtimestamp(ts, tz=UTC), float(avg)) for ts, avg in rows]

    def query_process(
        self,
        name: str,
        *,
        since: datetime,
        until: datetime,
    ) -> list[tuple[datetime, int]]:
        """Return ``(ts, mem_b)`` rows for a single process name."""
        if since > until:
            raise ValueError("since must be <= until")
        from datetime import UTC

        with self._lock:
            cur = self._conn.execute(
                "SELECT ts, mem_b FROM process_samples "
                "WHERE name = ? AND ts >= ? AND ts <= ? ORDER BY ts ASC",
                (name, int(since.timestamp()), int(until.timestamp())),
            )
            rows = cur.fetchall()
        return [(datetime.fromtimestamp(ts, tz=UTC), int(mem_b)) for ts, mem_b in rows]

    def vacuum_old(self, *, retain_days: int, now: datetime | None = None) -> int:
        """Delete rows older than ``retain_days`` and reclaim disk space.

        Returns the total number of rows removed from both tables.
        """
        if retain_days <= 0:
            raise ValueError(f"retain_days must be positive, got {retain_days!r}")
        from datetime import UTC

        cutoff_dt = now or datetime.now(tz=UTC)
        cutoff_epoch = int(cutoff_dt.timestamp()) - retain_days * 86_400
        with self._lock:
            self._conn.execute("BEGIN")
            cur1 = self._conn.execute("DELETE FROM metric_samples WHERE ts < ?", (cutoff_epoch,))
            cur2 = self._conn.execute(
                "DELETE FROM process_samples WHERE ts < ?",
                (cutoff_epoch,),
            )
            removed = (cur1.rowcount or 0) + (cur2.rowcount or 0)
            self._conn.execute("COMMIT")
            # VACUUM is run outside the transaction.
            try:
                self._conn.execute("VACUUM")
            except sqlite3.OperationalError as exc:
                _LOG.debug("VACUUM skipped: %s", exc)
        return removed

    def count_rows(self, table: str = "metric_samples") -> int:
        """Return the total row count for the given table (used by tests)."""
        if table not in ("metric_samples", "process_samples"):
            raise ValueError(f"unknown table: {table!r}")
        with self._lock:
            cur = self._conn.execute(f"SELECT COUNT(*) FROM {table}")
            return int(cur.fetchone()[0])
