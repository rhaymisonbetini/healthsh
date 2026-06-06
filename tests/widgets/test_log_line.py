"""LogLine widget tests — severity bar color, mono unit, message elision."""

from __future__ import annotations

from datetime import UTC, datetime

from healthsh.domain.log_entry import LogEntry
from healthsh.ui.theme.palette import ACCENT_AMBER, ACCENT_BLUE, ACCENT_RED, TEXT_MUTED
from healthsh.ui.widgets.log_line import LogLine, mono_font


def _entry(priority: int, message: str = "boot") -> LogEntry:
    return LogEntry(
        ts=datetime(2026, 6, 6, 14, 3, 21, tzinfo=UTC),
        unit="NetworkManager.service",
        priority=priority,
        message=message,
        hostname="host",
    )


def test_renders_err_in_red(qtbot) -> None:
    line = LogLine(_entry(priority=3))
    qtbot.addWidget(line)
    assert line.category() == "err"
    assert line.category_color_hex() == ACCENT_RED


def test_renders_warn_in_amber(qtbot) -> None:
    line = LogLine(_entry(priority=4))
    qtbot.addWidget(line)
    assert line.category() == "warn"
    assert line.category_color_hex() == ACCENT_AMBER


def test_renders_info_in_blue(qtbot) -> None:
    line = LogLine(_entry(priority=6))
    qtbot.addWidget(line)
    assert line.category() == "info"
    assert line.category_color_hex() == ACCENT_BLUE


def test_renders_debug_in_muted(qtbot) -> None:
    line = LogLine(_entry(priority=7))
    qtbot.addWidget(line)
    assert line.category() == "debug"
    assert line.category_color_hex() == TEXT_MUTED


def test_mono_font_is_cached(qtbot) -> None:  # noqa: ARG001
    assert mono_font() is mono_font()


def test_message_is_elided_for_long_text(qtbot) -> None:
    big = "very long message " * 50
    line = LogLine(_entry(priority=6, message=big))
    qtbot.addWidget(line)
    # The label content is short enough to fit at the minimum width — must end
    # with the ellipsis character introduced by QFontMetrics.elidedText.
    text = line._message_label.text()  # type: ignore[attr-defined]
    assert "…" in text


def test_unit_falls_back_to_em_dash_when_blank(qtbot) -> None:
    entry = LogEntry(
        ts=datetime(2026, 6, 6, 14, 3, 21, tzinfo=UTC),
        unit="",
        priority=6,
        message="hi",
    )
    line = LogLine(entry)
    qtbot.addWidget(line)
    from PySide6.QtWidgets import QLabel

    unit_label = next(
        c for c in line.findChildren(QLabel) if c.text() not in ("hi", "14:03:21") and c.text()
    )
    assert unit_label.text() == "—"
