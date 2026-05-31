"""Gauge widget tests — clamping, accent flip, rendering sanity."""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from PySide6.QtGui import QColor, QImage

from healthsh.ui.theme.palette import ACCENT_AMBER, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED
from healthsh.ui.widgets.gauge import Gauge


def _grab_image(widget: Gauge) -> QImage:
    """Render the widget into a QImage we can inspect pixel-by-pixel."""
    widget.resize(widget.sizeHint())
    pixmap = widget.grab()
    return pixmap.toImage()


def _pixel_counts(image: QImage, colors: Iterable[str]) -> dict[str, int]:
    """Return the count of pixels in ``image`` that match each color (exact)."""
    targets = {color: QColor(color).rgb() & 0x00FFFFFF for color in colors}
    counts = {color: 0 for color in colors}
    for y in range(image.height()):
        for x in range(image.width()):
            rgb = image.pixel(x, y) & 0x00FFFFFF
            for color, target in targets.items():
                if rgb == target:
                    counts[color] += 1
    return counts


def test_value_clamps_to_range(qtbot) -> None:
    g = Gauge(accent=ACCENT_BLUE, label="cpu")
    qtbot.addWidget(g)
    g.set_value(150)
    assert g.value() == 100
    g.set_value(-20)
    assert g.value() == 0
    g.set_value(42.5)
    assert g.value() == 42.5


def test_default_accent_used_below_warning(qtbot) -> None:
    g = Gauge(accent=ACCENT_BLUE)
    qtbot.addWidget(g)
    g.set_value(10)
    assert g.accent() == ACCENT_BLUE


def test_accent_flips_amber_at_warning(qtbot) -> None:
    g = Gauge(accent=ACCENT_BLUE)
    qtbot.addWidget(g)
    g.set_value(80)
    assert g.accent() == ACCENT_AMBER


def test_accent_flips_red_at_critical(qtbot) -> None:
    g = Gauge(accent=ACCENT_BLUE)
    qtbot.addWidget(g)
    g.set_value(95)
    assert g.accent() == ACCENT_RED


def test_custom_thresholds(qtbot) -> None:
    g = Gauge(accent=ACCENT_BLUE, warning_pct=50, critical_pct=80)
    qtbot.addWidget(g)
    g.set_value(60)
    assert g.accent() == ACCENT_AMBER
    g.set_value(85)
    assert g.accent() == ACCENT_RED


def test_thresholds_validate_order(qtbot) -> None:
    g = Gauge(accent=ACCENT_BLUE)
    qtbot.addWidget(g)
    with pytest.raises(ValueError):
        g.set_thresholds(warning=80, critical=70)
    with pytest.raises(ValueError):
        g.set_thresholds(warning=-1, critical=10)


def test_set_accent_changes_default(qtbot) -> None:
    g = Gauge(accent=ACCENT_BLUE)
    qtbot.addWidget(g)
    g.set_value(20)
    assert g.accent() == ACCENT_BLUE
    g.set_accent(ACCENT_GREEN)
    assert g.accent() == ACCENT_GREEN


def test_renders_value_pixels(qtbot) -> None:
    """A non-zero gauge must paint visible pixels in its accent color."""
    g = Gauge(accent=ACCENT_BLUE, label="cpu")
    qtbot.addWidget(g)
    g.set_value(50)
    image = _grab_image(g)
    counts = _pixel_counts(image, [ACCENT_BLUE])
    assert counts[ACCENT_BLUE] > 0, "expected accent.blue pixels for a non-zero gauge"


def test_renders_dash_when_value_is_none(qtbot) -> None:
    """An unset gauge renders an em-dash and stays in its default accent."""
    g = Gauge(accent=ACCENT_BLUE, label="gpu")
    qtbot.addWidget(g)
    g.set_value(None)
    image = _grab_image(g)
    # No accent arc when value is None.
    counts = _pixel_counts(image, [ACCENT_BLUE])
    assert counts[ACCENT_BLUE] == 0
    # The value text "—" should be rendered in TEXT_PRIMARY — we don't
    # tightly check the exact pixel count, but the image must not be empty.
    assert not image.isNull()
    assert image.width() > 0 and image.height() > 0
