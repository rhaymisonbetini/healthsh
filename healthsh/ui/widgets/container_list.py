"""Containers summary card for the Dashboard.

Sprint 1 ships this with placeholder data so the visual contract is in place;
issue #17 wires the real Docker collector that populates it.
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from healthsh.core.formatting import bytes_to_gb
from healthsh.domain.container import ContainerInfo
from healthsh.ui.theme.palette import (
    ACCENT_BLUE,
    ACCENT_GREEN,
    TEXT_MUTED,
)
from healthsh.ui.widgets.metric_card import MetricCard

_STATUS_DOT_DIAMETER: int = 8
_MEM_HIGH_GIB: float = 1.0  # ≥ 1 GiB → amber

# TODO(#17): replace with live docker_collector output.
PLACEHOLDER_CONTAINERS: tuple[tuple[ContainerInfo, int], ...] = (
    (ContainerInfo(id="placeholder-1", name="postgres-dev", status="running"), 4 * 1024**3),
    (ContainerInfo(id="placeholder-2", name="redis", status="running"), 128 * 1024**2),
    (ContainerInfo(id="placeholder-3", name="grafana", status="stopped"), 0),
)


def _format_mem(mem_b: int) -> str:
    gib = bytes_to_gb(mem_b)
    if gib >= 1.0:
        return f"{gib:.1f} GiB"
    return f"{mem_b / (1024 * 1024):.0f} MB"


class ContainerList(MetricCard):
    """Card showing running and stopped containers with a memory hint per row."""

    def __init__(self, *, title: str = "Containers", parent: QWidget | None = None) -> None:
        super().__init__(
            title=title,
            icon_name="brand-docker",
            icon_color=ACCENT_BLUE,
            parent=parent,
        )
        # Render placeholder data immediately so the card is never empty.
        self.set_containers(PLACEHOLDER_CONTAINERS)

    def set_containers(self, items: Iterable[tuple[ContainerInfo, int]]) -> None:
        """Replace visible rows with ``(container, mem_b)`` pairs."""
        self.clear_content()
        layout = self.content_layout()
        for container, mem_b in items:
            layout.addWidget(_build_row(container, mem_b))
        layout.addStretch(1)


def _status_dot(color_hex: str) -> QFrame:
    dot = QFrame()
    dot.setFixedSize(_STATUS_DOT_DIAMETER, _STATUS_DOT_DIAMETER)
    dot.setStyleSheet(
        f"background-color: {color_hex}; border-radius: {_STATUS_DOT_DIAMETER // 2}px;"
    )
    return dot


def _build_row(container: ContainerInfo, mem_b: int) -> QWidget:
    row = QWidget()
    row.setProperty("role", "row")
    box = QHBoxLayout(row)
    box.setContentsMargins(0, 4, 0, 4)
    box.setSpacing(8)

    box.addWidget(
        _status_dot(ACCENT_GREEN if container.is_running else TEXT_MUTED),
        alignment=Qt.AlignmentFlag.AlignVCenter,
    )

    name_label = QLabel(container.name)
    name_label.setProperty("role", "primary" if container.is_running else "muted")
    metrics = QFontMetrics(name_label.font())
    name_label.setText(metrics.elidedText(container.name, Qt.TextElideMode.ElideRight, 200))
    box.addWidget(name_label, stretch=1)

    mem_text = _format_mem(mem_b) if container.is_running else "—"
    mem_label = QLabel(mem_text)
    if container.is_running and bytes_to_gb(mem_b) >= _MEM_HIGH_GIB:
        mem_label.setProperty("role", "amber")
    else:
        mem_label.setProperty("role", "muted")
    box.addWidget(mem_label, alignment=Qt.AlignmentFlag.AlignRight)
    return row
