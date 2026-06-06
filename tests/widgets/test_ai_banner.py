"""AIBanner tests — entity highlighting + Insight wiring + healthy fallback."""

from __future__ import annotations

from datetime import UTC, datetime

from healthsh.domain.insight import Insight
from healthsh.ui.theme.palette import (
    ACCENT_AMBER,
    ACCENT_BLUE,
    ACCENT_RED,
    TEXT_MUTED,
)
from healthsh.ui.widgets.ai_banner import (
    HEALTHY_PREFIX,
    AIBanner,
)


def _insight(severity: str = "warning", message: str = "All good.") -> Insight:
    return Insight(
        severity=severity,  # type: ignore[arg-type]
        title="t",
        message=message,
        source="x",
        ts=datetime(2026, 6, 6, 14, 0, 0, tzinfo=UTC),
    )


def test_set_text_renders_entities_in_blue_mono(qtbot) -> None:
    banner = AIBanner()
    qtbot.addWidget(banner)
    banner.set_text("Analysis:", "Container `postgres-dev` is leaking.")
    body = banner.body()
    assert "postgres-dev" in body
    assert ACCENT_BLUE.lower() in body.lower()


def test_set_insight_uses_severity_color_for_prefix(qtbot) -> None:
    banner = AIBanner()
    qtbot.addWidget(banner)
    banner.set_insight(_insight(severity="critical"))
    style = banner._prefix_label.styleSheet()  # type: ignore[attr-defined]
    assert ACCENT_RED.lower() in style.lower()


def test_set_insight_warning_color(qtbot) -> None:
    banner = AIBanner()
    qtbot.addWidget(banner)
    banner.set_insight(_insight(severity="warning"))
    style = banner._prefix_label.styleSheet()  # type: ignore[attr-defined]
    assert ACCENT_AMBER.lower() in style.lower()


def test_set_insight_info_color(qtbot) -> None:
    banner = AIBanner()
    qtbot.addWidget(banner)
    banner.set_insight(_insight(severity="info"))
    style = banner._prefix_label.styleSheet()  # type: ignore[attr-defined]
    assert ACCENT_BLUE.lower() in style.lower()


def test_set_insight_none_shows_healthy_fallback(qtbot) -> None:
    banner = AIBanner()
    qtbot.addWidget(banner)
    banner.set_insight(_insight())
    banner.set_insight(None)
    assert banner.prefix() == HEALTHY_PREFIX
    style = banner._prefix_label.styleSheet()  # type: ignore[attr-defined]
    assert TEXT_MUTED.lower() in style.lower()


def test_set_insight_highlights_entities_in_message(qtbot) -> None:
    banner = AIBanner()
    qtbot.addWidget(banner)
    banner.set_insight(_insight(message="`/var/lib/docker` filling fast."))
    body = banner.body()
    assert "/var/lib/docker" in body
    assert ACCENT_BLUE.lower() in body.lower()


def test_current_insight_records_last_set(qtbot) -> None:
    banner = AIBanner()
    qtbot.addWidget(banner)
    insight = _insight()
    banner.set_insight(insight)
    assert banner.current_insight() is insight
    banner.set_insight(None)
    assert banner.current_insight() is None
