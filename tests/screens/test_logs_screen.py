"""LogsScreen tests — filter wiring, empty-state, auto-scroll-pause."""

from __future__ import annotations

from datetime import UTC, datetime

from healthsh.domain.log_entry import LogEntry, LogFilter
from healthsh.ui.screens.logs_screen import LogsScreen


def _entry(unit: str, priority: int, message: str = "msg", offset_s: int = 0) -> LogEntry:
    base = datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC)
    ts = base.replace(second=offset_s)
    return LogEntry(ts=ts, unit=unit, priority=priority, message=message)


def test_buffer_capped_at_5000(qtbot) -> None:
    screen = LogsScreen()
    qtbot.addWidget(screen)
    batch = [_entry("u", 6, offset_s=i % 60) for i in range(6000)]
    screen.on_journal(batch)
    assert screen.buffer_size() == 5000


def test_visible_lines_match_buffer_default(qtbot) -> None:
    screen = LogsScreen()
    qtbot.addWidget(screen)
    screen.on_journal(
        [
            _entry("a", 3, "err msg"),
            _entry("b", 4, "warn msg"),
            _entry("c", 6, "info msg"),
            _entry("d", 7, "debug msg"),
        ]
    )
    assert len(screen.visible_lines()) == 4


def test_unchecking_debug_hides_debug_lines(qtbot) -> None:
    screen = LogsScreen()
    qtbot.addWidget(screen)
    screen.on_journal(
        [
            _entry("a", 3, "err msg"),
            _entry("b", 4, "warn msg"),
            _entry("c", 6, "info msg"),
            _entry("d", 7, "debug msg"),
        ]
    )
    screen._filter_bar.pill("debug").setChecked(False)  # type: ignore[attr-defined]
    visible_messages = [line.entry().message for line in screen.visible_lines()]
    assert "debug msg" not in visible_messages
    assert len(visible_messages) == 3


def test_picking_a_unit_filters_to_that_unit(qtbot) -> None:
    screen = LogsScreen()
    qtbot.addWidget(screen)
    screen.on_journal(
        [
            _entry("NetworkManager.service", 6, "nm a"),
            _entry("systemd", 6, "sd a"),
            _entry("NetworkManager.service", 6, "nm b"),
        ]
    )
    bar = screen._filter_bar  # type: ignore[attr-defined]
    bar._unit_combo.setCurrentText("NetworkManager.service")  # type: ignore[attr-defined]
    messages = [line.entry().message for line in screen.visible_lines()]
    assert messages == ["nm a", "nm b"]


def test_subtitle_reports_lookback_window(qtbot) -> None:
    screen = LogsScreen(lookback_hours=6)
    qtbot.addWidget(screen)
    assert "last 6h" in screen.header_subtitle()


def test_filter_changed_re_renders_even_without_new_batch(qtbot) -> None:
    """Toggling a pill after a non-empty batch must update the visible list."""
    screen = LogsScreen()
    qtbot.addWidget(screen)
    screen.on_journal([_entry("u", 6), _entry("u", 7)])
    screen._filter_bar.pill("info").setChecked(False)  # type: ignore[attr-defined]
    # Only the debug entry should remain.
    assert [line.entry().priority for line in screen.visible_lines()] == [7]


def test_empty_state_surface(qtbot) -> None:
    """set_journald_unavailable should swap the inner stack."""
    screen = LogsScreen()
    qtbot.addWidget(screen)
    screen.set_journald_unavailable()
    assert screen.stack().currentIndex() == 1


def test_pause_flag_toggles_when_scroll_above_bottom(qtbot) -> None:
    screen = LogsScreen()
    qtbot.addWidget(screen)
    # Seed enough entries so the scrollbar has range.
    screen.on_journal([_entry("u", 6, message=f"m{i}", offset_s=i) for i in range(60)])
    bar = screen._scroll.verticalScrollBar()  # type: ignore[attr-defined]
    bar.setRange(0, 200)
    bar.setValue(200)
    # Scrolling up sets the paused flag.
    bar.setValue(50)
    assert screen.is_paused() is True
    # Returning to the bottom resumes live tail.
    bar.setValue(200)
    assert screen.is_paused() is False


def test_default_filter_keeps_every_category(qtbot) -> None:
    screen = LogsScreen()
    qtbot.addWidget(screen)
    f: LogFilter = screen.current_filter()
    assert f.categories == frozenset({"err", "warn", "info", "debug"})
    assert f.units is None
