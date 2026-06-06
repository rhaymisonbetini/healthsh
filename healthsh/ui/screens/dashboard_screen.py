"""Dashboard screen — gauges + sparkline + AI banner + Containers/Top-mem grid.

The gauge row is **adaptive**: the GPU slot only appears when a GPU is
actually detected. After five consecutive ``None`` GPU snapshots the screen
commits to a 3-column layout (CPU / RAM / Disk) and does not flip back.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from healthsh.core.formatting import bytes_to_gb, format_gpu_label
from healthsh.domain.metrics import GpuMetric, MetricsSnapshot
from healthsh.ui.theme.palette import (
    ACCENT_AMBER,
    ACCENT_BLUE,
    ACCENT_GREEN,
    ACCENT_PURPLE,
    GPU_ACCENT,
    TEXT_MUTED,
)
from healthsh.ui.widgets.ai_banner import AIBanner
from healthsh.ui.widgets.container_list import ContainerList
from healthsh.ui.widgets.gauge import Gauge
from healthsh.ui.widgets.process_list import ProcessList
from healthsh.ui.widgets.sparkline import Sparkline

# Subtitle prefix; the distro name (or 'unknown') is appended at runtime.
_SUBTITLE_PREFIX: str = "system health · "

# After this many consecutive ``None`` GPU snapshots, we commit to "no GPU"
# and stop probing — the row stays at three gauges for the rest of the run.
_GPU_DECISION_TICKS: int = 5

# Live indicator dot diameter (px).
_LIVE_DOT_DIAMETER: int = 8

# os-release path; tests can override by patching the constant.
_OS_RELEASE_PATH: Path = Path("/etc/os-release")


def _read_distro_pretty_name() -> str:
    """Return the friendly distro name from /etc/os-release, or 'unknown'."""
    try:
        text = _OS_RELEASE_PATH.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    for line in text.splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return "unknown"


def _gauge_card(gauge: Gauge) -> QFrame:
    """Wrap a :class:`Gauge` in the small-card chrome from the design system."""
    card = QFrame()
    card.setProperty("role", "card-small")
    card.setFrameShape(QFrame.Shape.NoFrame)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(0)
    layout.addWidget(gauge, alignment=Qt.AlignmentFlag.AlignHCenter)
    return card


def _live_indicator() -> QWidget:
    """Build the small 'live · 1s' chip for the header's right slot."""
    widget = QWidget()
    box = QHBoxLayout(widget)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(6)

    dot = QFrame()
    dot.setFixedSize(_LIVE_DOT_DIAMETER, _LIVE_DOT_DIAMETER)
    dot.setStyleSheet(
        f"background-color: {ACCENT_GREEN}; border-radius: {_LIVE_DOT_DIAMETER // 2}px;"
    )
    box.addWidget(dot, alignment=Qt.AlignmentFlag.AlignVCenter)

    label = QLabel("live · 1s")
    label.setProperty("role", "muted")
    box.addWidget(label, alignment=Qt.AlignmentFlag.AlignVCenter)
    return widget


class DashboardScreen(QWidget):
    """Top-level Dashboard composition (gauges, sparkline, AI banner, grid)."""

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._distro: str = _read_distro_pretty_name()

        # Gauges (CPU / RAM / Disk are always built; GPU is lazy).
        self._cpu_gauge = Gauge(accent=ACCENT_BLUE, label="CPU")
        self._ram_gauge = Gauge(accent=ACCENT_PURPLE, label="RAM")
        self._disk_gauge = Gauge(accent=ACCENT_BLUE, label="Disk")
        self._gpu_gauge: Gauge | None = None
        self._gpu_card: QFrame | None = None
        self._gpu_decision_made: bool = False
        self._no_gpu_streak: int = 0

        # Composition.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        # Row 1 — adaptive gauge grid.
        self._gauges_row = QHBoxLayout()
        self._gauges_row.setSpacing(10)
        self._gauges_row.addWidget(_gauge_card(self._cpu_gauge), stretch=1)
        self._gauges_row.addWidget(_gauge_card(self._ram_gauge), stretch=1)
        self._gauges_row.addWidget(_gauge_card(self._disk_gauge), stretch=1)
        outer.addLayout(self._gauges_row)

        # Row 2 — sparkline.
        self._sparkline = Sparkline()
        outer.addWidget(self._sparkline)

        # Row 3 — AI banner placeholder.
        self._ai_banner = AIBanner()
        outer.addWidget(self._ai_banner)

        # Row 4 — two-column grid.
        self._grid = QGridLayout()
        self._grid.setSpacing(12)
        self._container_list = ContainerList()
        self._process_list = ProcessList()
        self._grid.addWidget(self._container_list, 0, 0)
        self._grid.addWidget(self._process_list, 0, 1)
        outer.addLayout(self._grid, stretch=1)

        # Header right slot — Dashboard owns the 'live · 1s' chip.
        self._live_widget: QWidget = _live_indicator()

    # ----------------------------------------------------------------- API

    def on_snapshot(self, snapshot: MetricsSnapshot) -> None:
        """Update every visible widget from a fresh :class:`MetricsSnapshot`."""
        self._update_cpu(snapshot)
        self._update_ram(snapshot)
        self._update_disk(snapshot)
        self._update_gpu(snapshot)
        self._sparkline.append(snapshot)

    def header_subtitle(self) -> str:
        """Return the muted subtitle for the application header."""
        return f"{_SUBTITLE_PREFIX}{self._distro}"

    def header_right_widget(self) -> QWidget:
        """Return the widget to mount in the header's right slot."""
        return self._live_widget

    def has_gpu_gauge(self) -> bool:
        """Whether the GPU gauge is currently mounted (used by tests and #26)."""
        return self._gpu_card is not None

    def set_insight(self, insight) -> None:
        """Replace the AI banner content with a live :class:`Insight`."""
        self._ai_banner.set_insight(insight)

    # --------------------------------------------------------------- helpers

    def _update_cpu(self, snapshot: MetricsSnapshot) -> None:
        if snapshot.cpu is None:
            self._cpu_gauge.set_value(None)
            return
        self._cpu_gauge.set_value(snapshot.cpu.overall_pct)
        self._cpu_gauge.set_label(f"CPU · {snapshot.cpu.logical_cores} cores")

    def _update_ram(self, snapshot: MetricsSnapshot) -> None:
        if snapshot.mem is None:
            self._ram_gauge.set_value(None)
            return
        self._ram_gauge.set_value(snapshot.mem.percent)
        used_gib = bytes_to_gb(snapshot.mem.used_b)
        total_gib = bytes_to_gb(snapshot.mem.total_b)
        self._ram_gauge.set_label(f"RAM · {used_gib:.1f}/{total_gib:.0f}G")

    def _update_disk(self, snapshot: MetricsSnapshot) -> None:
        if snapshot.disk is None:
            self._disk_gauge.set_value(None)
            return
        # Disk gauge flips to amber automatically at warning_pct (75 default);
        # we only need to drive the value and label here.
        self._disk_gauge.set_value(snapshot.disk.percent)
        self._disk_gauge.set_label(f"Disk · {snapshot.disk.percent:.0f}%")

    def _update_gpu(self, snapshot: MetricsSnapshot) -> None:
        gpu: GpuMetric | None = snapshot.gpu

        if gpu is None:
            if self._gpu_decision_made:
                return  # Nothing to update — GPU is permanently absent.
            if self._gpu_card is not None:
                # We had a gauge but the GPU disappeared transiently — leave
                # the gauge in place but show the em-dash so the user notices.
                self._gpu_gauge.set_value(None)  # type: ignore[union-attr]
                return
            self._no_gpu_streak += 1
            if self._no_gpu_streak >= _GPU_DECISION_TICKS:
                self._gpu_decision_made = True
            return

        # GPU present.
        if self._gpu_gauge is None:
            if self._gpu_decision_made:
                # Layout was already committed to "no GPU" — do not rebuild
                # the row to avoid flicker for a late eGPU plug-in.
                return
            self._ensure_gpu_gauge(gpu.vendor)
        else:
            # Vendor may have changed (eGPU plug-in scenarios) — keep accent fresh.
            self._gpu_gauge.set_accent(GPU_ACCENT.get(gpu.vendor, ACCENT_AMBER))

        util = gpu.util_pct if gpu.util_pct is not None else 0.0
        self._gpu_gauge.set_value(util)  # type: ignore[union-attr]
        self._gpu_gauge.set_label(format_gpu_label(gpu))  # type: ignore[union-attr]
        self._gpu_decision_made = True
        self._no_gpu_streak = 0

    def _ensure_gpu_gauge(self, vendor: str) -> None:
        """Lazily construct and mount the GPU gauge in the gauges row."""
        if self._gpu_gauge is not None:
            return
        accent = GPU_ACCENT.get(vendor, ACCENT_AMBER)
        self._gpu_gauge = Gauge(accent=accent, label="GPU")
        self._gpu_card = _gauge_card(self._gpu_gauge)
        self._gauges_row.addWidget(self._gpu_card, stretch=1)
        # Silence unused-token warnings in linters that miss conditional use.
        _ = TEXT_MUTED
