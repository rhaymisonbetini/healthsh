"""``ProcessTable(QWidget)`` — sortable, scroll-stable live process table.

The widget composes a tiny header bar (title + sort toggle) over a
``QTableView`` backed by a custom :class:`ProcessTableModel`. Sorting is done
in Python before pushing rows to the model (we do not enable the view's
in-place sort, which would fight the 1 Hz refresh cycle).

Per-column colours are applied via ``Qt.ForegroundRole`` on the model — no
custom delegate is needed, which keeps the cell paint fast. The vertical
scroll position is captured before each reset and restored after so the user
never loses their place during the live update.
"""

from __future__ import annotations

from typing import Any, Literal

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from healthsh.core.formatting import bytes_to_gb
from healthsh.domain.process import ProcessInfo
from healthsh.ui.theme.palette import (
    ACCENT_AMBER,
    ACCENT_BLUE,
    ACCENT_PURPLE,
    TEXT_MUTED,
    TEXT_PRIMARY,
)

# Sort keys exposed via the sort toggle.
SortKey = Literal["memory", "cpu"]

# CPU% threshold above which the CPU column paints amber.
_CPU_AMBER_THRESHOLD: float = 75.0

# Column indices — keep stable, the model and view rely on this order.
_COL_PID: int = 0
_COL_NAME: int = 1
_COL_CPU: int = 2
_COL_MEM: int = 3
_COL_USER: int = 4
_NUM_COLS: int = 5

_HEADERS: tuple[str, ...] = ("PID", "Name", "CPU%", "MEM", "User")


def _format_mem(mem_b: int) -> str:
    """Compact memory string — MB below 1 GiB, GiB above."""
    gib = bytes_to_gb(mem_b)
    if gib >= 1.0:
        return f"{gib:.1f} GiB"
    return f"{mem_b / (1024 * 1024):.0f} MB"


class ProcessTableModel(QAbstractTableModel):
    """Adapter exposing a list of :class:`ProcessInfo` as a 5-column table.

    Updates always replace the full list — there is no fine-grained
    ``dataChanged`` path. ``beginResetModel`` is plenty fast for the ~200-row
    workload and trivially keeps state consistent. Per-column colour is
    delivered via :data:`Qt.ItemDataRole.ForegroundRole`.
    """

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[ProcessInfo] = []
        self._color_primary: QColor = QColor(TEXT_PRIMARY)
        self._color_muted: QColor = QColor(TEXT_MUTED)
        self._color_blue: QColor = QColor(ACCENT_BLUE)
        self._color_amber: QColor = QColor(ACCENT_AMBER)
        self._color_purple: QColor = QColor(ACCENT_PURPLE)

    # ------------------------------------------------------------------ Qt

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008, ARG002
        return _NUM_COLS

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return _HEADERS[section]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return self._alignment_for(section)
        return None

    def data(
        self,
        index: QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_for(row, col)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return self._alignment_for(col)
        if role == Qt.ItemDataRole.ForegroundRole:
            return self._foreground_for(row, col)
        return None

    # ----------------------------------------------------------------- API

    def set_processes(self, processes: list[ProcessInfo]) -> None:
        """Replace the full row list (full reset — see class docstring)."""
        self.beginResetModel()
        self._rows = list(processes)
        self.endResetModel()

    def rows(self) -> list[ProcessInfo]:
        """Return the current row list (defensive copy)."""
        return list(self._rows)

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _alignment_for(col: int) -> int:
        if col in (_COL_PID, _COL_CPU, _COL_MEM, _COL_USER):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    @staticmethod
    def _display_for(row: ProcessInfo, col: int) -> str:
        if col == _COL_PID:
            return str(row.pid)
        if col == _COL_NAME:
            return row.name or f"pid {row.pid}"
        if col == _COL_CPU:
            return f"{row.cpu_pct:.1f}"
        if col == _COL_MEM:
            return _format_mem(row.mem_b)
        if col == _COL_USER:
            return row.user
        return ""

    def _foreground_for(self, row: ProcessInfo, col: int) -> QColor | None:
        if col == _COL_PID:
            return self._color_muted
        if col == _COL_NAME:
            return self._color_primary
        if col == _COL_CPU:
            return self._color_amber if row.cpu_pct >= _CPU_AMBER_THRESHOLD else self._color_blue
        if col == _COL_MEM:
            return self._color_purple
        if col == _COL_USER:
            return self._color_muted
        return None


class _SortToggleButton(QPushButton):
    """Flat right-aligned button that cycles the sort key between memory↔cpu."""

    sort_changed = Signal(str)

    def __init__(self, *, initial: SortKey = "memory", parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.setProperty("role", "ghost")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._key: SortKey = initial
        self._refresh_text()
        self.clicked.connect(self._toggle)

    def key(self) -> SortKey:
        """Return the currently-selected sort key."""
        return self._key

    def set_key(self, key: SortKey) -> None:
        """Force the sort key (skipping the toggle path)."""
        if key not in ("memory", "cpu"):
            raise ValueError(f"unknown sort key: {key!r}")
        if self._key == key:
            return
        self._key = key
        self._refresh_text()
        self.sort_changed.emit(self._key)

    def _toggle(self) -> None:
        self._key = "cpu" if self._key == "memory" else "memory"
        self._refresh_text()
        self.sort_changed.emit(self._key)

    def _refresh_text(self) -> None:
        # Active key tinted blue per spec; muted leading text via QSS role.
        self.setText(f"sort by: {self._key} ▾")
        self.setStyleSheet(
            f"QPushButton {{ color: {ACCENT_BLUE}; border: 1px solid transparent; "
            f"background: transparent; padding: 4px 6px; }}"
            f"QPushButton:hover {{ color: {ACCENT_BLUE}; "
            f"border: 1px solid {ACCENT_BLUE}; }}"
        )


def _sort_processes(processes: list[ProcessInfo], key: SortKey) -> list[ProcessInfo]:
    if key == "cpu":
        return sorted(processes, key=lambda p: (p.cpu_pct, p.mem_b), reverse=True)
    return sorted(processes, key=lambda p: (p.mem_b, p.cpu_pct), reverse=True)


class ProcessTable(QWidget):
    """Header (title + sort toggle) + live ``QTableView`` of running processes."""

    sort_changed = Signal(str)

    def __init__(
        self,
        *,
        initial_sort: SortKey = "memory",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sort_key: SortKey = initial_sort
        self._raw: list[ProcessInfo] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        title = QLabel("Processes")
        title.setProperty("role", "section-title")
        header.addWidget(title)
        header.addStretch(1)
        self._sort_button = _SortToggleButton(initial=initial_sort)
        self._sort_button.sort_changed.connect(self._on_sort_changed)
        header.addWidget(self._sort_button)
        outer.addLayout(header)

        self._model = ProcessTableModel(parent=self)
        self._view = QTableView()
        self._view.setModel(self._model)
        self._view.setShowGrid(False)
        self._view.setAlternatingRowColors(False)
        self._view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._view.setSortingEnabled(False)  # we sort externally — see class docstring
        self._view.verticalHeader().setVisible(False)
        self._view.horizontalHeader().setStretchLastSection(False)
        self._view.horizontalHeader().setSectionResizeMode(
            _COL_NAME, QHeaderView.ResizeMode.Stretch
        )
        for col in (_COL_PID, _COL_CPU, _COL_MEM, _COL_USER):
            self._view.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        outer.addWidget(self._view, stretch=1)

    # ------------------------------------------------------------------ API

    def model(self) -> ProcessTableModel:
        """Return the underlying table model (used by tests + the System screen)."""
        return self._model

    def sort_key(self) -> SortKey:
        """Return the current sort key (``"memory"`` or ``"cpu"``)."""
        return self._sort_key

    def set_sort_key(self, key: SortKey) -> None:
        """Programmatically set the sort key (and re-sort the visible rows)."""
        self._sort_button.set_key(key)

    def set_processes(self, processes: list[ProcessInfo]) -> None:
        """Replace the visible row set; preserves scroll position across the reset."""
        self._raw = list(processes)
        scroll_value = self._view.verticalScrollBar().value()
        self._model.set_processes(_sort_processes(self._raw, self._sort_key))
        self._view.verticalScrollBar().setValue(scroll_value)

    # --------------------------------------------------------------- internal

    def _on_sort_changed(self, key: str) -> None:
        if key not in ("memory", "cpu"):
            return
        self._sort_key = key  # type: ignore[assignment]
        # Re-render with the new ordering (uses the cached raw list).
        self._model.set_processes(_sort_processes(self._raw, self._sort_key))
        self.sort_changed.emit(self._sort_key)
