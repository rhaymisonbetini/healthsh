"""Top-memory process list card used on the Dashboard."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from healthsh.core.formatting import bytes_to_gb
from healthsh.domain.process import ProcessInfo
from healthsh.ui.theme.palette import ACCENT_RED
from healthsh.ui.widgets.metric_card import MetricCard


def _format_mem(mem_b: int) -> str:
    """Compact human-friendly memory string — MB below 1 GiB, GiB above."""
    gib = bytes_to_gb(mem_b)
    if gib >= 1.0:
        return f"{gib:.1f} GiB"
    return f"{mem_b / (1024 * 1024):.0f} MB"


class ProcessList(MetricCard):
    """Card showing the top-N processes by memory."""

    def __init__(self, *, title: str = "Top memory", parent: QWidget | None = None) -> None:
        super().__init__(
            title=title,
            icon_name="flame",
            icon_color=ACCENT_RED,
            parent=parent,
        )

    def set_processes(self, processes: Iterable[ProcessInfo]) -> None:
        """Replace the visible rows with the supplied processes (already sorted)."""
        self.clear_content()
        layout = self.content_layout()
        for proc in processes:
            layout.addWidget(_build_row(proc))
        layout.addStretch(1)


def _build_row(proc: ProcessInfo) -> QWidget:
    row = QWidget()
    row.setProperty("role", "row")
    box = QHBoxLayout(row)
    box.setContentsMargins(0, 4, 0, 4)
    box.setSpacing(8)

    name_label = QLabel(proc.name or f"pid {proc.pid}")
    name_label.setProperty("role", "primary")
    name_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    metrics = QFontMetrics(name_label.font())
    name_label.setText(metrics.elidedText(name_label.text(), Qt.TextElideMode.ElideRight, 220))
    box.addWidget(name_label, stretch=1)

    mem_label = QLabel(_format_mem(proc.mem_b))
    mem_label.setProperty("role", "purple")
    box.addWidget(mem_label, alignment=Qt.AlignmentFlag.AlignRight)
    return row
