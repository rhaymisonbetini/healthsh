"""Mapping between journald priorities and the four UI severity categories.

journald priorities are integers 0–7 (``emerg``, ``alert``, ``crit``, ``err``,
``warning``, ``notice``, ``info``, ``debug``). The Logs screen surfaces only
four buckets (``err``, ``warn``, ``info``, ``debug``) to keep the filter UI
glanceable — this module is the canonical mapping for the category name. The
colour-token side of the mapping is owned by the UI layer
(:mod:`healthsh.ui.widgets.log_line`) so ``core`` stays free of Qt.
"""

from __future__ import annotations

from typing import Literal

SeverityCategory = Literal["err", "warn", "info", "debug"]

# Canonical category list, in display order. Used by the filter bar to render
# pills in a stable left-to-right sequence.
CATEGORIES: tuple[SeverityCategory, ...] = ("err", "warn", "info", "debug")


def priority_to_category(priority: int) -> SeverityCategory:
    """Bucket a journald priority into one of the four UI categories.

    Priority semantics:

    - ``priority <= 3`` → ``"err"``  (emerg/alert/crit/err)
    - ``priority == 4`` → ``"warn"`` (warning)
    - ``priority == 5 or 6`` → ``"info"`` (notice/info)
    - everything else → ``"debug"``

    Out-of-range values default to ``"debug"`` rather than raising — log entries
    occasionally arrive with unexpected priorities.
    """
    if priority <= 3:
        return "err"
    if priority == 4:
        return "warn"
    if priority in (5, 6):
        return "info"
    return "debug"
