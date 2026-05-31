"""Circular gauge widget drawn entirely with :class:`QPainter`.

The gauge paints a colored arc over a neutral ``track`` background ring, with
the current percentage in the centre and a small label below. It is the unit
used by the Dashboard's four KPI cards (CPU, RAM, Disk, GPU).

The accent color is swapped automatically when the value crosses the warning
or critical thresholds — so a CPU gauge configured with the default
``warning=75 / critical=90`` paints in :data:`ACCENT_BLUE` up to 74 %,
:data:`ACCENT_AMBER` at 75 %, and :data:`ACCENT_RED` at 90 %.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from healthsh.ui.theme.palette import (
    ACCENT_AMBER,
    ACCENT_RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TRACK,
)

# Geometry (px) — matches HEALTHSH_ROADMAP §5.1 (~24px radius, 6px stroke).
_RING_RADIUS: int = 24
_RING_STROKE: int = 6
_VALUE_FONT_PX: int = 14
_LABEL_FONT_PX: int = 11
_VALUE_TO_LABEL_GAP: int = 4

# Padding around the gauge content (px) — the parent MetricCard owns the
# outer card padding; this keeps the ring breathing inside its widget box.
_INNER_PADDING: int = 6


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp ``value`` to ``[low, high]``."""
    if value < low:
        return low
    if value > high:
        return high
    return value


class Gauge(QWidget):
    """Circular KPI gauge — value (0..100), accent color, single-line label."""

    def __init__(
        self,
        *,
        accent: str,
        label: str = "",
        warning_pct: float = 75.0,
        critical_pct: float = 90.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._accent_default: str = accent
        self._accent_current: str = accent
        self._label: str = label
        self._value: float | None = None  # None renders as em-dash "—"
        self._warning: float = warning_pct
        self._critical: float = critical_pct

        # Size hint: ring diameter + padding + value text height + label.
        edge = 2 * _RING_RADIUS + 2 * _INNER_PADDING
        height = edge + _VALUE_FONT_PX + _VALUE_TO_LABEL_GAP + _LABEL_FONT_PX + _INNER_PADDING
        self._size_hint: QSize = QSize(edge + 24, height)
        self.setMinimumSize(self._size_hint)

    # ------------------------------------------------------------------ API

    def set_value(self, value: float | None) -> None:
        """Update the gauge value (0..100) or ``None`` to show an em-dash."""
        if value is None:
            self._value = None
        else:
            self._value = _clamp(float(value))
        self._refresh_accent()
        self.update()

    def value(self) -> float | None:
        """Return the current value (post-clamp), or ``None`` when unset."""
        return self._value

    def set_label(self, text: str) -> None:
        """Update the small label below the value."""
        self._label = text
        self.update()

    def label(self) -> str:
        """Return the current label text."""
        return self._label

    def set_thresholds(self, *, warning: float = 75.0, critical: float = 90.0) -> None:
        """Override the warning / critical thresholds."""
        if warning < 0 or critical < 0:
            raise ValueError("thresholds must be non-negative")
        if critical < warning:
            raise ValueError("critical must be >= warning")
        self._warning = float(warning)
        self._critical = float(critical)
        self._refresh_accent()
        self.update()

    def set_accent(self, color: str) -> None:
        """Replace the default accent color (e.g. when GPU vendor changes)."""
        self._accent_default = color
        self._refresh_accent()
        self.update()

    def accent(self) -> str:
        """Return the *currently displayed* accent color (post-threshold flip)."""
        return self._accent_current

    # ------------------------------------------------------------------ Qt

    def sizeHint(self) -> QSize:  # noqa: D401 — Qt callback name
        """Return the preferred widget size."""
        return self._size_hint

    def paintEvent(self, _event) -> None:  # noqa: D401 — Qt callback name
        """Paint the track ring, the value arc, the value text and the label."""
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

            ring_rect = self._ring_rect()
            self._paint_track(painter, ring_rect)
            if self._value is not None and self._value > 0:
                self._paint_arc(painter, ring_rect, self._value)

            self._paint_value(painter, ring_rect)
            self._paint_label(painter, ring_rect)
        finally:
            painter.end()

    # -------------------------------------------------------------- helpers

    def _refresh_accent(self) -> None:
        if self._value is None:
            self._accent_current = self._accent_default
            return
        if self._value >= self._critical:
            self._accent_current = ACCENT_RED
        elif self._value >= self._warning:
            self._accent_current = ACCENT_AMBER
        else:
            self._accent_current = self._accent_default

    def _ring_rect(self) -> QRectF:
        """Square rect enclosing the ring, centred horizontally near the top."""
        edge = 2 * _RING_RADIUS
        x = (self.width() - edge) / 2
        y = float(_INNER_PADDING)
        return QRectF(x, y, edge, edge)

    def _paint_track(self, painter: QPainter, ring_rect: QRectF) -> None:
        pen = QPen(QColor(TRACK))
        pen.setWidth(_RING_STROKE)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        # Inset by half the pen width so the stroke stays inside the rect.
        half = _RING_STROKE / 2
        painter.drawEllipse(ring_rect.adjusted(half, half, -half, -half))

    def _paint_arc(self, painter: QPainter, ring_rect: QRectF, value: float) -> None:
        pen = QPen(QColor(self._accent_current))
        pen.setWidth(_RING_STROKE)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        half = _RING_STROKE / 2
        rect = ring_rect.adjusted(half, half, -half, -half)
        # Qt arc angles are in 1/16 of a degree. 0 is 3 o'clock, positive
        # rotates counter-clockwise. We want to start at 12 o'clock and sweep
        # clockwise — that's start=90deg (90 * 16) with a negative span.
        start_angle = 90 * 16
        span_angle = -int((value / 100.0) * 360 * 16)
        painter.drawArc(rect, start_angle, span_angle)

    def _paint_value(self, painter: QPainter, ring_rect: QRectF) -> None:
        text = "—" if self._value is None else f"{int(round(self._value))}%"
        font = QFont(self.font())
        font.setPixelSize(_VALUE_FONT_PX)
        font.setWeight(QFont.Weight.Medium)  # 500
        painter.setFont(font)
        painter.setPen(QPen(QColor(TEXT_PRIMARY)))
        painter.drawText(ring_rect, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_label(self, painter: QPainter, ring_rect: QRectF) -> None:
        if not self._label:
            return
        font = QFont(self.font())
        font.setPixelSize(_LABEL_FONT_PX)
        painter.setFont(font)
        painter.setPen(QPen(QColor(TEXT_MUTED)))
        # Place the label below the ring, centered horizontally.
        label_top = ring_rect.bottom() + _VALUE_TO_LABEL_GAP
        label_rect = QRectF(
            0,
            label_top,
            float(self.width()),
            float(_LABEL_FONT_PX + 4),
        )
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignHCenter, self._label)
        # Silence unused-import-like warning by referencing QPointF in __doc__.
        _ = QPointF
