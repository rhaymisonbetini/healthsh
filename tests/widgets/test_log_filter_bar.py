"""LogFilterBar tests — pill toggles, dropdown population, filter_changed."""

from __future__ import annotations

from healthsh.domain.log_entry import LogFilter
from healthsh.ui.widgets.log_filter_bar import ALL_UNITS_TEXT, LogFilterBar


def test_default_filter_keeps_every_category_and_all_units(qtbot) -> None:
    bar = LogFilterBar()
    qtbot.addWidget(bar)
    f = bar.current_filter()
    assert f.units is None
    assert f.categories == frozenset({"err", "warn", "info", "debug"})


def test_toggling_a_pill_emits_filter_changed(qtbot) -> None:
    bar = LogFilterBar()
    qtbot.addWidget(bar)
    received: list[LogFilter] = []
    bar.filter_changed.connect(received.append)
    bar.pill("debug").setChecked(False)
    assert received and "debug" not in received[-1].categories


def test_picking_a_unit_emits_filter_with_that_unit(qtbot) -> None:
    bar = LogFilterBar()
    qtbot.addWidget(bar)
    bar.set_units(["NetworkManager.service", "systemd"])
    received: list[LogFilter] = []
    bar.filter_changed.connect(received.append)
    bar._unit_combo.setCurrentText("systemd")  # type: ignore[attr-defined]
    assert received[-1].units == ("systemd",)


def test_setting_unit_back_to_all_clears_units(qtbot) -> None:
    bar = LogFilterBar()
    qtbot.addWidget(bar)
    bar.set_units(["systemd"])
    bar._unit_combo.setCurrentText("systemd")  # type: ignore[attr-defined]
    received: list[LogFilter] = []
    bar.filter_changed.connect(received.append)
    bar._unit_combo.setCurrentText(ALL_UNITS_TEXT)  # type: ignore[attr-defined]
    assert received[-1].units is None


def test_set_units_is_idempotent_when_list_unchanged(qtbot) -> None:
    bar = LogFilterBar()
    qtbot.addWidget(bar)
    bar.set_units(["a", "b"])
    received: list[LogFilter] = []
    bar.filter_changed.connect(received.append)
    bar.set_units(["a", "b"])
    assert received == []


def test_set_units_preserves_selection_when_unit_still_present(qtbot) -> None:
    bar = LogFilterBar()
    qtbot.addWidget(bar)
    bar.set_units(["a", "b"])
    bar._unit_combo.setCurrentText("b")  # type: ignore[attr-defined]
    bar.set_units(["a", "b", "c"])
    assert bar._unit_combo.currentText() == "b"  # type: ignore[attr-defined]


def test_set_filter_updates_controls_without_emitting(qtbot) -> None:
    bar = LogFilterBar()
    qtbot.addWidget(bar)
    bar.set_units(["systemd"])
    received: list[LogFilter] = []
    bar.filter_changed.connect(received.append)
    bar.set_filter(LogFilter(units=("systemd",), categories=frozenset({"err"})))
    assert received == []
    assert bar.current_filter().units == ("systemd",)
    assert bar.current_filter().categories == frozenset({"err"})
