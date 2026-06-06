"""AI insight value object.

An :class:`Insight` is the typed output of the analysis engine in #24 and the
LLM agent in #25. Severity is a small enum so the UI can paint the banner
the right colour deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

InsightSeverity = Literal["info", "warning", "critical"]

# Symbolic constants for the three target screens — used by InsightService
# when picking which insight to surface where.
InsightTarget = Literal["dashboard", "docker", "logs"]


@dataclass(frozen=True)
class Insight:
    """A single AI / analysis insight surfaced on a banner or chat.

    Attributes:
        severity: ``"info"`` (calm), ``"warning"`` (amber), ``"critical"``
            (red border).
        title: Short headline rendered as the bold prefix on the banner.
        message: Longer body with optional backtick-delimited entities; the
            UI parser highlights entities in :data:`accent.blue` mono.
        source: Tag identifying the analyser (e.g. ``"disk_forecast"``,
            ``"leak_detector"``, ``"log_cluster"``). Used by the AI agent to
            attribute findings.
        entities: Pre-extracted entity names referenced by the insight (process
            names, container names, paths). Lets the UI route clicks to the
            right screen without re-parsing ``message``.
        ts: Wall-clock time the insight was generated (UTC).
    """

    severity: InsightSeverity
    title: str
    message: str
    source: str
    entities: tuple[str, ...] = field(default_factory=tuple)
    ts: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
