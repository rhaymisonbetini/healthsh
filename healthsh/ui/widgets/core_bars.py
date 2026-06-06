"""``CoreBars(QWidget)`` — 4-column grid of per-core mini-bars.

The widget visualises every logical CPU core as a thin track with a coloured
fill proportional to that core's utilisation. Cores at or above
:data:`DEFAULT_WARNING_PCT` flip from ``ACCENT_BLUE`` to ``ACCENT_AMBER`` so a
runaway / pinned core jumps out at a glance.

Cells are built **lazily** on the first :meth:`set_values` call (when the core
count is known) and then reused across updates — only the fill widths and
colours change, never the layout — which keeps the 1 Hz refresh flicker-free.
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from healthsh.ui.theme.palette import (
    ACCENT_AMBER,
    ACCENT_BLUE,
    RADIUS_BAR,
    TRACK,
)

# Default per-cell warning threshold (percent).
DEFAULT_WARNING_PCT: float = 85.0

# Grid geometry.
_COLUMNS: int = 4
_GRID_GAP_PX: int = 10

# Per-cell geometry.
_BAR_HEIGHT_PX: int = 6
_MIN_BAR_WIDTH_PX: int = 40
_CELL_GAP_PX: int = 4
_LABEL_HEIGHT_PX: int = 14


class _CoreCell(QWidget):
    """One core's label + track + fill — the atomic unit of :class:`CoreBars`."""

    def __init__(
        self,
        *,
        index: int,
        warning_pct: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._warning_pct = warning_pct
        self._value_pct: float = 0.0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(_CELL_GAP_PX)

        self._label = QLabel(f"core {index + 1}")
        self._label.setProperty("role", "hint")
        self._label.setFixedHeight(_LABEL_HEIGHT_PX)
        outer.addWidget(self._label)

        self._track = QFrame()
        self._track.setObjectName("core-track")
        self._track.setFixedHeight(_BAR_HEIGHT_PX)
        self._track.setMinimumWidth(_MIN_BAR_WIDTH_PX)
        self._track.setStyleSheet(
            f"#core-track {{ background-color: {TRACK}; border-radius: {RADIUS_BAR}px; }}"
        )
        track_layout = QHBoxLayout(self._track)
        track_layout.setContentsMargins(0, 0, 0, 0)
        track_layout.setSpacing(0)

        self._fill = QFrame(self._track)
        self._fill.setObjectName("core-fill")
        self._fill.setFixedHeight(_BAR_HEIGHT_PX)
        self._fill.setStyleSheet(self._fill_style(ACCENT_BLUE))
        track_layout.addWidget(self._fill, alignment=Qt.AlignmentFlag.AlignLeft)
        track_layout.addStretch(1)

        outer.addWidget(self._track)

    @staticmethod
    def _fill_style(color_hex: str) -> str:
        return f"#core-fill {{ background-color: {color_hex}; border-radius: {RADIUS_BAR}px; }}"

    def value_pct(self) -> float:
        """Return the last value (percent) the cell rendered."""
        return self._value_pct

    def set_value(self, pct: float) -> None:
        """Update the fill width + colour for the given utilisation percent."""
        clamped = max(0.0, min(100.0, float(pct)))
        self._value_pct = clamped
        color = ACCENT_AMBER if clamped >= self._warning_pct else ACCENT_BLUE
        self._fill.setStyleSheet(self._fill_style(color))
        self._refresh_fill_geometry()

    def _refresh_fill_geometry(self) -> None:
        track_w = max(self._track.width(), _MIN_BAR_WIDTH_PX)
        width = int(track_w * self._value_pct / 100.0)
        self._fill.setFixedWidth(max(0, min(width, track_w)))

    def fill_color_hex(self) -> str:
        """Return the current fill color (used by tests + the System screen)."""
        return ACCENT_AMBER if self._value_pct >= self._warning_pct else ACCENT_BLUE

    def resizeEvent(self, event) -> None:  # noqa: D401 — Qt callback name
        super().resizeEvent(event)
        self._refresh_fill_geometry()


class CoreBars(QWidget):
    """Grid of per-core utilisation mini-bars.

    Cells are created lazily on the first :meth:`set_values` call so the
    widget does not assume a core count at construction time. Subsequent
    calls reuse the same cells.
    """

    def __init__(
        self,
        *,
        warning_pct: float = DEFAULT_WARNING_PCT,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if warning_pct <= 0 or warning_pct > 100:
            raise ValueError(f"warning_pct must be in (0, 100], got {warning_pct!r}")
        self._warning_pct: float = float(warning_pct)
        self._cells: list[_CoreCell] = []

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(_GRID_GAP_PX)
        self._grid.setVerticalSpacing(_GRID_GAP_PX)
        for col in range(_COLUMNS):
            self._grid.setColumnStretch(col, 1)

    # ------------------------------------------------------------------ API

    def warning_pct(self) -> float:
        """Return the per-cell warning threshold (percent)."""
        return self._warning_pct

    def core_count(self) -> int:
        """Return the number of cells currently mounted (0 before first update)."""
        return len(self._cells)

    def set_values(self, per_core: list[float] | tuple[float, ...]) -> None:
        """Update every cell from a list of per-core percentages.

        Cells are created the first time this method is called and reused
        thereafter. If the core count changes (rare — e.g. CPU hotplug on
        servers) the grid is rebuilt.
        """
        values = list(per_core)
        if len(values) != len(self._cells):
            self._rebuild_cells(len(values))
        for cell, pct in zip(self._cells, values, strict=False):
            cell.set_value(float(pct))

    def cell_color_at(self, index: int) -> str:
        """Return the fill colour hex of the cell at ``index`` (tests use this)."""
        return self._cells[index].fill_color_hex()

    # --------------------------------------------------------------- helpers

    def _rebuild_cells(self, count: int) -> None:
        """Drop existing cells and recreate ``count`` of them in a fresh grid."""
        for cell in self._cells:
            self._grid.removeWidget(cell)
            cell.deleteLater()
        self._cells = []

        rows = max(1, math.ceil(count / _COLUMNS))
        for row in range(rows):
            self._grid.setRowStretch(row, 0)
        for i in range(count):
            row, col = divmod(i, _COLUMNS)
            cell = _CoreCell(index=i, warning_pct=self._warning_pct, parent=self)
            self._grid.addWidget(cell, row, col)
            self._cells.append(cell)
