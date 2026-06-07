"""form_rows tests — signals fire on user edits and stay silent on set_value."""

from __future__ import annotations

from healthsh.ui.widgets.form_rows import DropdownRow, IntRow, SliderRow, TextRow, ToggleRow


def test_int_row_silent_on_set_emits_on_user_change(qtbot) -> None:
    row = IntRow("X", minimum=0, maximum=100, step=5)
    qtbot.addWidget(row)
    seen: list[int] = []
    row.changed.connect(seen.append)
    row.set_value(40)
    assert seen == []
    assert row.value() == 40
    row._spin.setValue(45)  # type: ignore[attr-defined]
    assert seen == [45]


def test_toggle_row(qtbot) -> None:
    row = ToggleRow("on?")
    qtbot.addWidget(row)
    seen: list[bool] = []
    row.changed.connect(seen.append)
    row.set_value(True)
    assert seen == []
    assert row.value() is True
    row._check.setChecked(False)  # type: ignore[attr-defined]
    assert seen == [False]


def test_dropdown_row(qtbot) -> None:
    row = DropdownRow("pick", options=["a", "b", "c"])
    qtbot.addWidget(row)
    seen: list[str] = []
    row.changed.connect(seen.append)
    row.set_value("b")
    assert seen == []
    assert row.value() == "b"
    row._combo.setCurrentText("c")  # type: ignore[attr-defined]
    assert seen == ["c"]


def test_slider_row_readout_and_signal(qtbot) -> None:
    row = SliderRow("warn", minimum=0, maximum=100)
    qtbot.addWidget(row)
    seen: list[int] = []
    row.changed.connect(seen.append)
    row.set_value(75)
    assert seen == []
    assert row.value() == 75
    row._slider.setValue(80)  # type: ignore[attr-defined]
    assert seen == [80]


def test_text_row_password_masking(qtbot) -> None:
    row = TextRow("API key", password=True)
    qtbot.addWidget(row)
    assert row.is_masked() is True
    row._eye.setChecked(True)  # type: ignore[attr-defined]
    assert row.is_masked() is False
    row._eye.setChecked(False)  # type: ignore[attr-defined]
    assert row.is_masked() is True


def test_text_row_commits_on_editing_finished(qtbot) -> None:
    row = TextRow("endpoint")
    qtbot.addWidget(row)
    seen: list[str] = []
    row.changed.connect(seen.append)
    row.set_value("typed")
    assert seen == []
    row._edit.setText("http://x")  # type: ignore[attr-defined]
    row._edit.editingFinished.emit()  # type: ignore[attr-defined]
    assert seen == ["http://x"]
