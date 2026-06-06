"""``LogFilterBar(QFrame)`` — unit dropdown + four severity pills.

Emits :pyattr:`filter_changed` whenever the user toggles a pill or picks a
unit. The dropdown is populated dynamically from the Logs screen as new units
arrive in the journal buffer — :meth:`set_units` only repopulates when the
incoming list differs from the current one (so the open popup doesn't snap
shut on every 3 s journald tick).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QWidget,
)

from healthsh.core.log_severity import CATEGORIES, SeverityCategory
from healthsh.domain.log_entry import LogFilter
from healthsh.ui.widgets.log_line import category_color

# Sentinel for the dropdown's "all units" option.
ALL_UNITS_TEXT: str = "all services"

# Pill geometry.
_PILL_PADDING_H: int = 10
_PILL_PADDING_V: int = 4


class _SeverityPill(QPushButton):
    """Checkable pill — filled when active, outlined when inactive."""

    def __init__(self, *, category: SeverityCategory, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self._category: SeverityCategory = category
        self.setText(category)
        self.setCheckable(True)
        self.setChecked(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggled.connect(self._refresh_style)
        self._refresh_style(True)

    def category(self) -> SeverityCategory:
        """Return the severity category this pill controls."""
        return self._category

    def _refresh_style(self, checked: bool) -> None:
        color = category_color(self._category)
        if checked:
            qss = (
                f"QPushButton {{ background-color: {color}; color: #1a1b26; "
                f"border: 1px solid {color}; "
                f"border-radius: 999px; padding: {_PILL_PADDING_V}px {_PILL_PADDING_H}px; "
                "font-weight: 500; }"
                "QPushButton:hover { background-color: " + color + "; }"
            )
        else:
            qss = (
                f"QPushButton {{ background-color: transparent; color: {color}; "
                f"border: 1px solid {color}; "
                f"border-radius: 999px; padding: {_PILL_PADDING_V}px {_PILL_PADDING_H}px; }}"
                f"QPushButton:hover {{ background-color: rgba(125,207,255,0.06); }}"
            )
        self.setStyleSheet(qss)


class LogFilterBar(QFrame):
    """Horizontal bar holding the unit dropdown + 4 severity pills."""

    filter_changed = Signal(object)  # LogFilter

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "card-small")
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        self._unit_combo = QComboBox()
        self._unit_combo.addItem(ALL_UNITS_TEXT)
        self._unit_combo.currentIndexChanged.connect(self._emit_filter)
        layout.addWidget(self._unit_combo)

        layout.addStretch(1)

        self._pills: dict[SeverityCategory, _SeverityPill] = {}
        for category in CATEGORIES:
            pill = _SeverityPill(category=category)
            pill.toggled.connect(self._emit_filter)
            self._pills[category] = pill
            layout.addWidget(pill)

    # ------------------------------------------------------------------ API

    def set_units(self, units: list[str]) -> None:
        """Repopulate the dropdown with the sorted, unique list of units.

        The currently-selected unit (if still in the new list) is preserved.
        A redundant call with the same units is a no-op — keeps the popup
        from snapping shut on every journald tick.
        """
        unique = sorted({u for u in units if u})
        existing = [self._unit_combo.itemText(i) for i in range(1, self._unit_combo.count())]
        if existing == unique:
            return
        current = self._unit_combo.currentText()
        # Block the signal while we mutate the list — we'll emit at most once
        # at the end if the selection actually changed.
        self._unit_combo.blockSignals(True)
        try:
            self._unit_combo.clear()
            self._unit_combo.addItem(ALL_UNITS_TEXT)
            for unit in unique:
                self._unit_combo.addItem(unit)
            if current in unique:
                index = self._unit_combo.findText(current)
                if index >= 0:
                    self._unit_combo.setCurrentIndex(index)
        finally:
            self._unit_combo.blockSignals(False)

    def current_filter(self) -> LogFilter:
        """Build the :class:`LogFilter` matching the current control state."""
        unit_text = self._unit_combo.currentText()
        units: tuple[str, ...] | None = None
        if unit_text and unit_text != ALL_UNITS_TEXT:
            units = (unit_text,)
        categories = frozenset(
            category for category, pill in self._pills.items() if pill.isChecked()
        )
        return LogFilter(units=units, categories=categories)

    def set_filter(self, filter_: LogFilter) -> None:
        """Force the controls to match ``filter_`` without emitting a signal."""
        self.blockSignals(True)
        try:
            if filter_.units is None or not filter_.units:
                self._unit_combo.setCurrentIndex(0)
            else:
                index = self._unit_combo.findText(filter_.units[0])
                if index >= 0:
                    self._unit_combo.setCurrentIndex(index)
            for category, pill in self._pills.items():
                pill.setChecked(category in filter_.categories)
        finally:
            self.blockSignals(False)

    def pill(self, category: SeverityCategory) -> _SeverityPill:
        """Return the pill controlling ``category`` (tests use this)."""
        return self._pills[category]

    # --------------------------------------------------------------- helpers

    def _emit_filter(self, *_args) -> None:  # noqa: D401 — Qt callback wrapper
        """Emit ``filter_changed`` with the current control state."""
        self.filter_changed.emit(self.current_filter())
