"""ProcessTable widget tests — sorting, per-column colors, scroll preservation."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QColor

from healthsh.domain.process import ProcessInfo
from healthsh.ui.theme.palette import (
    ACCENT_AMBER,
    ACCENT_BLUE,
    ACCENT_PURPLE,
    TEXT_MUTED,
    TEXT_PRIMARY,
)
from healthsh.ui.widgets.process_table import ProcessTable, ProcessTableModel


def _sample() -> list[ProcessInfo]:
    return [
        ProcessInfo(pid=10, name="postgres-dev", user="postgres", cpu_pct=2.0, mem_b=4 * 1024**3),
        ProcessInfo(pid=11, name="chrome", user="me", cpu_pct=80.0, mem_b=800 * 1024**2),
        ProcessInfo(pid=12, name="python", user="me", cpu_pct=0.5, mem_b=50 * 1024**2),
        ProcessInfo(pid=13, name="gnome-shell", user="me", cpu_pct=12.0, mem_b=400 * 1024**2),
    ]


def _display_value(model: ProcessTableModel, row: int, col: int) -> str:
    return str(model.data(model.index(row, col), Qt.ItemDataRole.DisplayRole))


def _foreground(model: ProcessTableModel, row: int, col: int) -> QColor | None:
    value = model.data(model.index(row, col), Qt.ItemDataRole.ForegroundRole)
    return value if isinstance(value, QColor) else None


def test_default_sort_is_by_memory_descending(qtbot) -> None:
    table = ProcessTable()
    qtbot.addWidget(table)
    table.set_processes(_sample())
    model = table.model()
    pids = [int(_display_value(model, r, 0)) for r in range(model.rowCount(QModelIndex()))]
    # postgres-dev has the biggest mem → row 0; chrome row 1; gnome-shell row 2; python last.
    assert pids == [10, 11, 13, 12]


def test_toggle_sort_to_cpu_reorders_rows(qtbot) -> None:
    table = ProcessTable()
    qtbot.addWidget(table)
    table.set_processes(_sample())
    table.set_sort_key("cpu")
    model = table.model()
    pids = [int(_display_value(model, r, 0)) for r in range(model.rowCount(QModelIndex()))]
    # chrome 80% first; gnome-shell 12%; postgres-dev 2%; python 0.5%.
    assert pids == [11, 13, 10, 12]
    assert table.sort_key() == "cpu"


def test_cpu_column_color_flips_at_amber_threshold(qtbot) -> None:
    table = ProcessTable()
    qtbot.addWidget(table)
    table.set_processes(_sample())
    model = table.model()
    # Default sort = memory desc → row 0 = postgres-dev (cpu 2%), row 1 = chrome (cpu 80%).
    assert _foreground(model, 0, 2) == QColor(ACCENT_BLUE)
    assert _foreground(model, 1, 2) == QColor(ACCENT_AMBER)


def test_static_column_colors_match_spec(qtbot) -> None:
    table = ProcessTable()
    qtbot.addWidget(table)
    table.set_processes(_sample())
    model = table.model()
    # row 0 = postgres-dev: PID muted, Name primary, MEM purple, User muted.
    assert _foreground(model, 0, 0) == QColor(TEXT_MUTED)
    assert _foreground(model, 0, 1) == QColor(TEXT_PRIMARY)
    assert _foreground(model, 0, 3) == QColor(ACCENT_PURPLE)
    assert _foreground(model, 0, 4) == QColor(TEXT_MUTED)


def test_mem_column_formats_gib_and_mb(qtbot) -> None:
    table = ProcessTable()
    qtbot.addWidget(table)
    table.set_processes(_sample())
    model = table.model()
    # postgres-dev → 4.0 GiB; python → 50 MB.
    assert "GiB" in _display_value(model, 0, 3)
    last = model.rowCount(QModelIndex()) - 1
    assert "MB" in _display_value(model, last, 3)


def test_scroll_position_preserved_across_updates(qtbot) -> None:
    """The widget must read the scroll value before reset and write it back after."""
    table = ProcessTable()
    qtbot.addWidget(table)
    big = [
        ProcessInfo(pid=i, name=f"proc-{i}", user="me", cpu_pct=0.0, mem_b=(i + 1) * 1024 * 1024)
        for i in range(80)
    ]
    table.set_processes(big)
    # Force a non-trivial scroll range so setValue(50) is not clamped to 0 by an
    # un-laid-out view in offscreen mode.
    scroll_bar = table._view.verticalScrollBar()  # type: ignore[attr-defined]
    scroll_bar.setRange(0, 200)
    scroll_bar.setValue(50)
    table.set_processes(big)
    assert scroll_bar.value() == 50


def test_sort_changed_signal_emits_on_toggle(qtbot) -> None:
    table = ProcessTable()
    qtbot.addWidget(table)
    received: list[str] = []
    table.sort_changed.connect(received.append)
    table.set_processes(_sample())
    table.set_sort_key("cpu")
    table.set_sort_key("memory")
    assert received == ["cpu", "memory"]
