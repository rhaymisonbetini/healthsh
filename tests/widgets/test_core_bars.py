"""CoreBars widget tests — geometry, threshold flip, idempotent updates."""

from __future__ import annotations

import pytest

from healthsh.ui.theme.palette import ACCENT_AMBER, ACCENT_BLUE
from healthsh.ui.widgets.core_bars import DEFAULT_WARNING_PCT, CoreBars


def test_warning_pct_rejects_out_of_range_values(qtbot) -> None:  # noqa: ARG001
    with pytest.raises(ValueError):
        CoreBars(warning_pct=0)
    with pytest.raises(ValueError):
        CoreBars(warning_pct=101)


def test_set_values_creates_one_cell_per_core(qtbot) -> None:
    widget = CoreBars()
    qtbot.addWidget(widget)
    assert widget.core_count() == 0
    widget.set_values([10.0, 20.0, 30.0, 40.0, 50.0])
    assert widget.core_count() == 5


def test_set_values_reuses_cells_across_updates(qtbot) -> None:
    """The grid must not rebuild when the per-core count is unchanged."""
    widget = CoreBars()
    qtbot.addWidget(widget)
    widget.set_values([10.0] * 8)
    cells_first = list(widget._cells)  # type: ignore[attr-defined]
    widget.set_values([60.0] * 8)
    cells_second = list(widget._cells)  # type: ignore[attr-defined]
    assert cells_first == cells_second


def test_threshold_flip_blue_to_amber(qtbot) -> None:
    """Below threshold → blue; at/above threshold → amber."""
    widget = CoreBars(warning_pct=DEFAULT_WARNING_PCT)
    qtbot.addWidget(widget)
    widget.set_values([70.0, 90.0, 86.0, 50.0])
    assert widget.cell_color_at(0) == ACCENT_BLUE
    assert widget.cell_color_at(1) == ACCENT_AMBER
    assert widget.cell_color_at(2) == ACCENT_AMBER
    assert widget.cell_color_at(3) == ACCENT_BLUE


def test_custom_warning_threshold_is_honored(qtbot) -> None:
    widget = CoreBars(warning_pct=50.0)
    qtbot.addWidget(widget)
    widget.set_values([40.0, 50.0, 60.0])
    assert widget.cell_color_at(0) == ACCENT_BLUE
    assert widget.cell_color_at(1) == ACCENT_AMBER
    assert widget.cell_color_at(2) == ACCENT_AMBER


def test_values_outside_zero_to_hundred_are_clamped(qtbot) -> None:
    widget = CoreBars()
    qtbot.addWidget(widget)
    widget.set_values([-10.0, 200.0])
    cells = widget._cells  # type: ignore[attr-defined]
    assert cells[0].value_pct() == 0.0
    assert cells[1].value_pct() == 100.0


def test_core_count_change_triggers_rebuild(qtbot) -> None:
    """Hot-plug edge case — switching core counts rebuilds the grid."""
    widget = CoreBars()
    qtbot.addWidget(widget)
    widget.set_values([0.0] * 4)
    assert widget.core_count() == 4
    widget.set_values([0.0] * 6)
    assert widget.core_count() == 6
