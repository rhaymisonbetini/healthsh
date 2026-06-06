"""Logs screen — filter bar + AI placeholder banner + live tail of journald.

Holds a bounded buffer of the most recent journald entries (capped at
:data:`_BUFFER_CAP`), re-renders the visible slice through the current
:class:`LogFilter`, and auto-scrolls to the bottom unless the user has
manually scrolled up — at which point a *paused* pill appears that, when
clicked, jumps back to live tail.

When ``journalctl`` is unavailable on the host, the screen swaps to a calm
empty state instead of an empty list of logs.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from healthsh.core.log_severity import CATEGORIES, priority_to_category
from healthsh.domain.log_entry import LogEntry, LogFilter
from healthsh.services.collector_service import CollectorService
from healthsh.ui.theme.palette import ACCENT_BLUE, ACCENT_GREEN, TEXT_MUTED
from healthsh.ui.widgets.ai_banner import AIBanner
from healthsh.ui.widgets.log_filter_bar import LogFilterBar
from healthsh.ui.widgets.log_line import LogLine

# Hard cap on the in-memory entry buffer (#22 task list).
_BUFFER_CAP: int = 5000

# Scrollbar-from-bottom slack below which we consider the user "at the
# bottom" and resume auto-scroll.
_AT_BOTTOM_SLACK_PX: int = 20

# AI banner placeholder copy.
_LOGS_AI_PLACEHOLDER_PREFIX: str = "Analysis:"
_LOGS_AI_PLACEHOLDER_BODY: str = (
    "AI-grouped errors will appear here once Sprint 5 wires the agent base. "
    "Example: `12 identical NetworkManager errors in 2h — possible "
    "connection flapping`. View details."
)

# Default lookback window for the screen's subtitle.
_DEFAULT_LOOKBACK_HOURS: int = 2


class _LiveStatusPill(QPushButton):
    """Right-aligned pill toggling between ``live`` and ``paused`` indicators."""

    resume_requested = Signal()

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._paused: bool = False
        self._refresh_style()
        self.clicked.connect(self._on_clicked)

    def set_paused(self, paused: bool) -> None:
        """Switch between live and paused states (idempotent)."""
        if paused == self._paused:
            return
        self._paused = bool(paused)
        self._refresh_style()

    def is_paused(self) -> bool:
        """Return whether the pill is currently in the paused state."""
        return self._paused

    def _on_clicked(self) -> None:
        if self._paused:
            self.resume_requested.emit()

    def _refresh_style(self) -> None:
        if self._paused:
            self.setText("paused — click for live")
            color = TEXT_MUTED
        else:
            self.setText("live")
            color = ACCENT_GREEN
        self.setStyleSheet(
            f"QPushButton {{ background-color: transparent; color: {color}; "
            f"border: 1px solid {color}; border-radius: 999px; "
            "padding: 2px 10px; font-weight: 500; }}"
            f"QPushButton:hover {{ border: 1px solid {ACCENT_BLUE}; color: {ACCENT_BLUE}; }}"
        )


class LogsScreen(QWidget):
    """Logs screen composing filter bar + AI banner + scrolling tail."""

    def __init__(
        self,
        *,
        collector_service: CollectorService | None = None,
        lookback_hours: int = _DEFAULT_LOOKBACK_HOURS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._collector_service: CollectorService | None = collector_service
        self._buffer: deque[LogEntry] = deque(maxlen=_BUFFER_CAP)
        self._filter: LogFilter = LogFilter(units=None, categories=frozenset(CATEGORIES))
        self._auto_scroll: bool = True
        self._lookback_hours: int = lookback_hours
        self._subtitle_text: str = f"journald · last {lookback_hours}h"
        # Set by _on_filter_changed so a subsequent empty journald batch still
        # forces a re-render (otherwise on_journal early-returns).
        self._filter_was_just_set: bool = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        self._filter_bar = LogFilterBar()
        self._filter_bar.filter_changed.connect(self._on_filter_changed)
        outer.addWidget(self._filter_bar)

        self._ai_banner = AIBanner(
            prefix=_LOGS_AI_PLACEHOLDER_PREFIX,
            body=_LOGS_AI_PLACEHOLDER_BODY,
        )
        outer.addWidget(self._ai_banner)

        self._live_pill = _LiveStatusPill()
        self._live_pill.resume_requested.connect(self._jump_to_live)
        pill_row = QVBoxLayout()
        pill_row.setContentsMargins(0, 0, 0, 0)
        pill_row.setSpacing(0)
        pill_row.addWidget(self._live_pill, alignment=Qt.AlignmentFlag.AlignRight)
        outer.addLayout(pill_row)

        # Two-view stack: live tail (0) + journald-unavailable empty state (1).
        self._stack = QStackedWidget()
        outer.addWidget(self._stack, stretch=1)

        # Live tail view.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll_content = QWidget()
        self._list_layout = QVBoxLayout(self._scroll_content)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch(1)
        self._scroll.setWidget(self._scroll_content)
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self._stack.addWidget(self._scroll)

        # Empty state view (journald unavailable).
        self._empty_state = QLabel("journald is unavailable on this system.")
        self._empty_state.setProperty("role", "muted")
        self._empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._empty_state)

        if collector_service is not None:
            collector_service.journal_ready.connect(self.on_journal)

        # Silence unused-token warning when palette tokens are used only via QSS.
        _ = (ACCENT_BLUE, TEXT_MUTED)

    # ------------------------------------------------------------------ API

    def header_subtitle(self) -> str:
        """Return the muted subtitle (recomputed on each journal_ready)."""
        return self._subtitle_text

    def on_journal(self, entries: Iterable[LogEntry]) -> None:
        """Slot for ``CollectorService.journal_ready``.

        Merges the new entries into the bounded buffer, repopulates the
        unit dropdown, and re-renders the visible list under the current
        filter. Auto-scrolls to the bottom unless the user has scrolled up.
        """
        added = 0
        for entry in entries:
            self._buffer.append(entry)
            added += 1
        if added == 0 and not self._filter_was_just_set:
            return
        self._filter_was_just_set = False

        if (
            self._stack.currentIndex() == 1
            and self._collector_service is not None
            and self._collector_service.journald_collector().is_available()
        ):
            # journald became available — swap back to the live tail view.
            self._stack.setCurrentIndex(0)

        self._refresh_unit_dropdown()
        self._render_visible()
        self._subtitle_text = f"journald · last {self._lookback_hours}h"

    def set_journald_unavailable(self) -> None:
        """Force the screen into the empty-state view (used by the wiring layer)."""
        self._stack.setCurrentIndex(1)

    def buffer_size(self) -> int:
        """Return the current number of entries in the bounded buffer."""
        return len(self._buffer)

    def visible_lines(self) -> list[LogLine]:
        """Return the LogLine widgets currently mounted (used by tests)."""
        out: list[LogLine] = []
        for i in range(self._list_layout.count()):
            widget = self._list_layout.itemAt(i).widget()
            if isinstance(widget, LogLine):
                out.append(widget)
        return out

    def current_filter(self) -> LogFilter:
        """Return the LogFilter the screen is currently applying."""
        return self._filter

    def is_paused(self) -> bool:
        """Return ``True`` when the auto-scroll-pause pill is showing 'paused'."""
        return self._live_pill.is_paused()

    def stack(self) -> QStackedWidget:
        """Return the inner stacked widget (tests use this)."""
        return self._stack

    def set_insight(self, insight) -> None:
        """Replace the AI banner content with a live :class:`Insight`."""
        self._ai_banner.set_insight(insight)

    # --------------------------------------------------------------- helpers

    def _on_filter_changed(self, new_filter: LogFilter) -> None:
        self._filter = new_filter
        self._filter_was_just_set = True
        self._render_visible()

    def _refresh_unit_dropdown(self) -> None:
        units = sorted({entry.unit for entry in self._buffer if entry.unit})
        self._filter_bar.set_units(units)

    def _render_visible(self) -> None:
        # Clear the existing line widgets (the trailing stretch stays).
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        filter_units = self._filter.units
        filter_categories = self._filter.categories
        filtered: list[LogEntry] = []
        for entry in self._buffer:
            if filter_units is not None and entry.unit not in filter_units:
                continue
            if priority_to_category(entry.priority) not in filter_categories:
                continue
            filtered.append(entry)

        for entry in filtered:
            line = LogLine(entry)
            # Insert before the trailing stretch.
            self._list_layout.insertWidget(self._list_layout.count() - 1, line)

        if self._auto_scroll:
            self._jump_to_live()

    def _on_scroll_changed(self, value: int) -> None:
        max_value = self._scroll.verticalScrollBar().maximum()
        at_bottom = value >= max_value - _AT_BOTTOM_SLACK_PX
        if at_bottom and not self._auto_scroll:
            self._auto_scroll = True
            self._live_pill.set_paused(False)
        elif not at_bottom and self._auto_scroll:
            self._auto_scroll = False
            self._live_pill.set_paused(True)

    def _jump_to_live(self) -> None:
        self._auto_scroll = True
        self._live_pill.set_paused(False)
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
