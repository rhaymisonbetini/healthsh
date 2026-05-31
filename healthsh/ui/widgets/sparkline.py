"""60-second sliding sparkline for CPU / RAM (PyQtGraph)."""

from __future__ import annotations

from collections import deque

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from healthsh.domain.metrics import MetricsSnapshot
from healthsh.ui.theme.palette import ACCENT_BLUE, ACCENT_PURPLE

# Module-level pyqtgraph config — antialiased lines on a transparent
# background so the card chrome shows through. Applied once at import.
pg.setConfigOptions(antialias=True, background=None)

# Sliding-window length (seconds). Matches the spec ("Usage over 60 s").
WINDOW_SECONDS: int = 60

# Stroke width (px) per the design spec.
_LINE_WIDTH: int = 2


def _legend_dot(color_hex: str) -> QLabel:
    """Return a small inline-HTML coloured bullet used in the card header legend."""
    dot = QLabel(f'<span style="color:{color_hex};font-size:14px;">●</span>')
    dot.setTextFormat(Qt.TextFormat.RichText)
    return dot


class Sparkline(QFrame):
    """A 60-second CPU + RAM sliding line chart wrapped in a styled card."""

    def __init__(self, *, title: str = "Usage over 60s", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._cpu_samples: deque[float] = deque(maxlen=WINDOW_SECONDS)
        self._ram_samples: deque[float] = deque(maxlen=WINDOW_SECONDS)

        # Header row: title left, legend right.
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        title_label = QLabel(title)
        title_label.setProperty("role", "section-title")
        header.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignLeft)
        header.addStretch(1)

        cpu_dot = _legend_dot(ACCENT_BLUE)
        cpu_text = QLabel("CPU")
        cpu_text.setProperty("role", "muted")
        ram_dot = _legend_dot(ACCENT_PURPLE)
        ram_text = QLabel("RAM")
        ram_text.setProperty("role", "muted")
        for widget in (cpu_dot, cpu_text, ram_dot, ram_text):
            header.addWidget(widget, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Plot area.
        self._plot = pg.PlotWidget(parent=self)
        self._plot.setBackground(None)
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.setMenuEnabled(False)
        self._plot.hideAxis("left")
        self._plot.hideAxis("bottom")
        self._plot.setYRange(0, 100, padding=0)
        self._plot.setXRange(-WINDOW_SECONDS + 1, 0, padding=0)
        self._plot.showGrid(x=False, y=False)

        self._cpu_curve = self._plot.plot(
            pen=pg.mkPen(ACCENT_BLUE, width=_LINE_WIDTH),
            name="CPU",
        )
        self._ram_curve = self._plot.plot(
            pen=pg.mkPen(ACCENT_PURPLE, width=_LINE_WIDTH),
            name="RAM",
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(6)
        outer.addLayout(header)
        outer.addWidget(self._plot, stretch=1)

    # ------------------------------------------------------------------ API

    def append(self, snapshot: MetricsSnapshot) -> None:
        """Push a new sample from ``snapshot`` and redraw both curves.

        Missing CPU / RAM data carries forward the previous value to keep the
        sliding window dense — if no previous value exists we drop in ``0.0``.
        """
        cpu_value = (
            snapshot.cpu.overall_pct if snapshot.cpu is not None else self._last(self._cpu_samples)
        )
        ram_value = (
            snapshot.mem.percent if snapshot.mem is not None else self._last(self._ram_samples)
        )

        self._cpu_samples.append(float(cpu_value))
        self._ram_samples.append(float(ram_value))
        self._refresh_curves()

    def reset(self) -> None:
        """Drop every buffered sample and clear the curves."""
        self._cpu_samples.clear()
        self._ram_samples.clear()
        self._refresh_curves()

    def cpu_buffer(self) -> tuple[float, ...]:
        """Return the current CPU buffer as an immutable tuple (used by tests)."""
        return tuple(self._cpu_samples)

    def ram_buffer(self) -> tuple[float, ...]:
        """Return the current RAM buffer as an immutable tuple (used by tests)."""
        return tuple(self._ram_samples)

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _last(samples: deque[float]) -> float:
        """Return the last sample or ``0.0`` when the buffer is empty."""
        return samples[-1] if samples else 0.0

    def _refresh_curves(self) -> None:
        """Recompute the (x, y) arrays from the deques and push them to the plot."""
        cpu = list(self._cpu_samples)
        ram = list(self._ram_samples)
        # X axis: most recent sample sits at 0, older samples extend negative
        # so the curves visibly scroll left as new data arrives.
        cpu_x = [-(len(cpu) - 1 - i) for i in range(len(cpu))]
        ram_x = [-(len(ram) - 1 - i) for i in range(len(ram))]
        self._cpu_curve.setData(cpu_x, cpu)
        self._ram_curve.setData(ram_x, ram)
