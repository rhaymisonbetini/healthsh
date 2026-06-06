"""System / Processes screen — per-core bars, three small cards, process table.

Composes the widgets from #14 (:class:`CoreBars`) and #15 (:class:`ProcessTable`)
with three small stat cards (CPU temperature, swap, process count) into the
full §5.2 layout. The screen subscribes to live snapshots via the
``on_snapshot`` method (the main window already routes ``metrics_ready``
emissions to every screen that implements it).

Temperature flips to ``accent.amber`` at or above 70 °C — a calm warning that
matches the rest of the design language. The header subtitle is recomputed on
every tick so ``load`` and ``uptime`` stay current.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from healthsh.core.formatting import bytes_to_gb, format_load, format_temp_c, format_uptime
from healthsh.domain.metrics import MetricsSnapshot, SystemMetric, TempReading
from healthsh.ui.theme.palette import ACCENT_AMBER, TEXT_MUTED, TEXT_PRIMARY
from healthsh.ui.widgets.core_bars import CoreBars
from healthsh.ui.widgets.process_table import ProcessTable

# Temperature warning threshold for the small CPU-temp card (°C).
_TEMP_WARNING_C: float = 70.0

# Section spacing (px).
_SECTION_GAP: int = 12
_SMALL_CARD_GAP: int = 10

# Label shown above the per-core grid (§5.2 — "Por núcleo").
_BY_CORE_LABEL: str = "By core"

# Chips preferred when picking the "primary CPU temp" for the small card.
# coretemp = Intel, k10temp = AMD; everything else is fallback.
_PRIMARY_CPU_CHIPS: tuple[str, ...] = ("coretemp", "k10temp")


def _pick_primary_cpu_temp(temps: tuple[TempReading, ...]) -> float | None:
    """Return the most representative CPU temperature for the small card."""
    by_sensor = {t.sensor.lower(): t.value_c for t in temps}
    for chip in _PRIMARY_CPU_CHIPS:
        if chip in by_sensor:
            return by_sensor[chip]
    return temps[0].value_c if temps else None


def _format_swap(swap_total_b: int, swap_used_b: int) -> str:
    """Format the swap card body as ``used/total`` GiB, or ``"no swap"``."""
    if swap_total_b <= 0:
        return "no swap"
    return f"{bytes_to_gb(swap_used_b):.1f} / {bytes_to_gb(swap_total_b):.1f} GiB"


class _StatCard(QFrame):
    """Small stat card — title (muted) on top, value (primary or amber) below."""

    def __init__(self, *, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "card-small")
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(4)

        self._title = QLabel(title)
        self._title.setProperty("role", "muted")
        outer.addWidget(self._title)

        self._value = QLabel("—")
        self._value.setProperty("role", "kpi")
        outer.addWidget(self._value)
        outer.addStretch(1)

    def set_value(self, text: str, *, amber: bool = False) -> None:
        """Update the card's body text and accent."""
        self._value.setText(text)
        # Override the kpi role color when we need amber.
        if amber:
            self._value.setStyleSheet(f"color: {ACCENT_AMBER};")
        else:
            self._value.setStyleSheet(f"color: {TEXT_PRIMARY};")


class SystemScreen(QWidget):
    """Composed System / Processes screen."""

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._subtitle_text: str = "processes and sensors"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(_SECTION_GAP)

        # Section 1 — per-core bars.
        by_core_label = QLabel(_BY_CORE_LABEL)
        by_core_label.setProperty("role", "muted")
        outer.addWidget(by_core_label)

        self._core_bars = CoreBars()
        outer.addWidget(self._core_bars)

        # Section 2 — three small stat cards.
        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(_SMALL_CARD_GAP)

        self._temp_card = _StatCard(title="Temp CPU")
        self._swap_card = _StatCard(title="Swap")
        self._proc_count_card = _StatCard(title="Processes")
        cards_row.addWidget(self._temp_card, stretch=1)
        cards_row.addWidget(self._swap_card, stretch=1)
        cards_row.addWidget(self._proc_count_card, stretch=1)
        outer.addLayout(cards_row)

        # Section 3 — process table.
        self._process_table = ProcessTable()
        outer.addWidget(self._process_table, stretch=1)

        # Silence unused-token warning when only the QSS role color is used.
        _ = TEXT_MUTED

    # ------------------------------------------------------------------ API

    def header_subtitle(self) -> str:
        """Return the latest subtitle (the chrome refreshes it on screen change)."""
        return self._subtitle_text

    def on_snapshot(self, snapshot: MetricsSnapshot) -> None:
        """Push fresh data into every section of the screen."""
        self._update_subtitle(snapshot)
        self._update_core_bars(snapshot)
        self._update_small_cards(snapshot)
        self._update_process_table(snapshot)

    def core_bars(self) -> CoreBars:
        """Expose the CoreBars instance (used by tests)."""
        return self._core_bars

    def process_table(self) -> ProcessTable:
        """Expose the ProcessTable instance (used by tests)."""
        return self._process_table

    # --------------------------------------------------------------- helpers

    def _update_subtitle(self, snapshot: MetricsSnapshot) -> None:
        cores = snapshot.cpu.logical_cores if snapshot.cpu else 0
        if snapshot.system is None:
            self._subtitle_text = f"{cores} cores · load — · up —"
            return
        load_text = format_load(snapshot.system.load)
        uptime_text = format_uptime(snapshot.system.uptime_s)
        self._subtitle_text = f"{cores} cores · load {load_text} · up {uptime_text}"

    def _update_core_bars(self, snapshot: MetricsSnapshot) -> None:
        if snapshot.cpu is None or not snapshot.cpu.per_core_pct:
            return
        self._core_bars.set_values(list(snapshot.cpu.per_core_pct))

    def _update_small_cards(self, snapshot: MetricsSnapshot) -> None:
        system: SystemMetric | None = snapshot.system
        temp_c = _pick_primary_cpu_temp(system.temps) if system is not None else None
        if temp_c is None:
            self._temp_card.set_value("n/a")
        else:
            amber = temp_c >= _TEMP_WARNING_C
            self._temp_card.set_value(format_temp_c(temp_c), amber=amber)

        if system is None:
            self._swap_card.set_value("—")
        else:
            self._swap_card.set_value(_format_swap(system.swap.total_b, system.swap.used_b))

        proc_count = len(snapshot.processes_full)
        if proc_count == 0:
            self._proc_count_card.set_value("—")
        else:
            self._proc_count_card.set_value(str(proc_count))

    def _update_process_table(self, snapshot: MetricsSnapshot) -> None:
        if not snapshot.processes_full:
            return
        self._process_table.set_processes(list(snapshot.processes_full))
