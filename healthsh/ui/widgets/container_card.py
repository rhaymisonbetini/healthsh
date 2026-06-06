"""``ContainerCard(QFrame)`` — one Docker container's status + actions.

The visual unit on the Docker screen. Header row renders status dot, name,
image:tag and uptime; stats row renders CPU%, MEM and ports; action icons sit
on the right (pause/restart/logs for running containers; play for stopped).
Stopped containers paint with a dimmer background and ~0.7 opacity so the
"alive vs. not" signal is unmistakable.

Actions are emitted as :pyattr:`action_requested` signals — the Docker screen
(#19) is responsible for running them off the UI thread via a small
:class:`QThreadPool` worker. Confirmation dialogs and the logs modal live on
the card itself so each card is self-contained from a UX perspective.
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from healthsh.core.formatting import bytes_to_gb, format_uptime
from healthsh.domain.container import ContainerInfo, ContainerStats
from healthsh.ui.icons import get_icon_pixmap
from healthsh.ui.theme.palette import (
    ACCENT_AMBER,
    ACCENT_BLUE,
    ACCENT_GREEN,
    BG_CARD,
    BG_CHROME,
    TEXT_MUTED,
    TEXT_PRIMARY,
)

# Icons (Tabler outline names).
_ICON_PAUSE: str = "player-pause"
_ICON_RESTART: str = "refresh"
_ICON_LOGS: str = "file-text"
_ICON_PLAY: str = "player-play"

# Visual constants.
_STATUS_DOT_DIAMETER: int = 8
_ACTION_ICON_SIZE: int = 16
_STOPPED_OPACITY: float = 0.7

# Memory amber rule per spec — high if ≥ 1 GiB OR ≥ 80% of limit (when known).
_MEM_AMBER_GIB: float = 1.0
_MEM_AMBER_RATIO: float = 0.8

# Logs modal dimensions.
_LOGS_MODAL_W: int = 720
_LOGS_MODAL_H: int = 480


def _format_mem_bytes(mem_b: int) -> str:
    """Compact memory string — MB below 1 GiB, GiB above."""
    gib = bytes_to_gb(mem_b)
    if gib >= 1.0:
        return f"{gib:.1f} GiB"
    return f"{mem_b / (1024 * 1024):.0f} MB"


def _is_mem_high(stats: ContainerStats) -> bool:
    """Apply the §5.3 amber rule for the MEM cell."""
    if bytes_to_gb(stats.mem_used_b) >= _MEM_AMBER_GIB:
        return True
    if stats.mem_limit_b and stats.mem_limit_b > 0:
        return (stats.mem_used_b / stats.mem_limit_b) >= _MEM_AMBER_RATIO
    return False


def _status_dot(color_hex: str) -> QFrame:
    dot = QFrame()
    dot.setFixedSize(_STATUS_DOT_DIAMETER, _STATUS_DOT_DIAMETER)
    dot.setStyleSheet(
        f"background-color: {color_hex}; border-radius: {_STATUS_DOT_DIAMETER // 2}px;"
    )
    return dot


def _action_button(name: str, color_hex: str, tooltip: str) -> QPushButton:
    """Build a flat icon-only button that fires the matching action signal."""
    btn = QPushButton()
    btn.setProperty("role", "ghost")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setIcon(get_icon_pixmap(name, color_hex, _ACTION_ICON_SIZE))
    btn.setIconSize(QSize(_ACTION_ICON_SIZE, _ACTION_ICON_SIZE))
    btn.setFixedSize(QSize(_ACTION_ICON_SIZE + 12, _ACTION_ICON_SIZE + 8))
    btn.setToolTip(tooltip)
    btn.setStyleSheet(
        "QPushButton { background: transparent; border: 1px solid transparent; padding: 2px; }"
        f"QPushButton:hover {{ border: 1px solid {ACCENT_BLUE}; }}"
    )
    return btn


class _LogsDialog(QDialog):
    """Read-only modal showing the tail of a container's logs in a mono font."""

    def __init__(
        self,
        *,
        title: str,
        lines: Iterable[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(_LOGS_MODAL_W, _LOGS_MODAL_H)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        view = QPlainTextEdit()
        view.setReadOnly(True)
        font = QFont("JetBrains Mono")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPixelSize(12)
        view.setFont(font)
        view.setPlainText("\n".join(lines))
        layout.addWidget(view, stretch=1)


class ContainerCard(QFrame):
    """Visual + interactive card for one container."""

    action_requested = Signal(str, str)  # (container_id, action)

    def __init__(
        self,
        *,
        info: ContainerInfo,
        stats: ContainerStats | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._info: ContainerInfo = info
        self._stats: ContainerStats | None = stats
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)

        # Header row.
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self._status_dot = _status_dot(ACCENT_GREEN)
        header.addWidget(self._status_dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._name_label = QLabel()
        self._name_label.setProperty("role", "section-title")
        header.addWidget(self._name_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._image_label = QLabel()
        self._image_label.setProperty("role", "muted")
        header.addWidget(self._image_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        header.addStretch(1)

        # Actions container (right side of header row).
        self._actions_container = QWidget()
        actions_layout = QHBoxLayout(self._actions_container)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(4)
        self._btn_pause = _action_button(_ICON_PAUSE, TEXT_MUTED, "Pause")
        self._btn_restart = _action_button(_ICON_RESTART, TEXT_MUTED, "Restart")
        self._btn_logs = _action_button(_ICON_LOGS, TEXT_MUTED, "View logs (tail 200)")
        self._btn_play = _action_button(_ICON_PLAY, ACCENT_GREEN, "Start")
        for btn in (self._btn_pause, self._btn_restart, self._btn_logs, self._btn_play):
            actions_layout.addWidget(btn)
        header.addWidget(self._actions_container)
        outer.addLayout(header)

        self._btn_pause.clicked.connect(self._on_pause_clicked)
        self._btn_restart.clicked.connect(self._on_restart_clicked)
        self._btn_logs.clicked.connect(self._on_logs_clicked)
        self._btn_play.clicked.connect(self._on_play_clicked)

        # Stats row.
        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(12)
        self._cpu_label = QLabel()
        self._mem_label = QLabel()
        self._ports_label = QLabel()
        self._ports_label.setProperty("role", "muted")
        stats_row.addWidget(self._cpu_label)
        stats_row.addWidget(self._mem_label)
        stats_row.addStretch(1)
        stats_row.addWidget(self._ports_label)
        outer.addLayout(stats_row)

        # The logs callback is plugged in by the Docker screen — when None the
        # logs button degrades to an information message in the modal.
        self._logs_provider = None  # type: ignore[var-annotated]

        self.update_state(info, stats)

    # ------------------------------------------------------------------ API

    def info(self) -> ContainerInfo:
        """Return the currently rendered :class:`ContainerInfo`."""
        return self._info

    def stats(self) -> ContainerStats | None:
        """Return the currently rendered :class:`ContainerStats` (or ``None``)."""
        return self._stats

    def set_logs_provider(self, provider) -> None:
        """Wire a callable that returns the latest log tail for this container.

        The provider is called on the UI thread when the user clicks the logs
        icon. Callers (the Docker screen) typically hand a closure that calls
        ``docker_collector.tail_logs`` *off* the UI thread and resolves to the
        lines — but the modal itself is opened synchronously here.
        """
        self._logs_provider = provider

    def update_state(
        self,
        info: ContainerInfo,
        stats: ContainerStats | None = None,
    ) -> None:
        """Re-render the card in place from a fresh ``info`` + ``stats`` tuple.

        Labels are updated, not recreated, so hover states on the action icons
        and selection state on text survive 3 s refreshes.
        """
        self._info = info
        self._stats = stats
        running = info.is_running

        # Visual state — running vs stopped.
        self.setProperty("role", "card" if running else "card-inactive")
        self._opacity.setOpacity(1.0 if running else _STOPPED_OPACITY)
        self.setStyleSheet(
            f"QFrame[role='card'] {{ background-color: {BG_CARD}; }}"
            f"QFrame[role='card-inactive'] {{ background-color: {BG_CHROME}; }}"
        )

        # Status dot color.
        self._status_dot.setStyleSheet(
            f"background-color: {ACCENT_GREEN if running else TEXT_MUTED}; "
            f"border-radius: {_STATUS_DOT_DIAMETER // 2}px;"
        )

        # Header text.
        self._name_label.setText(info.name)
        suffix = f" · {info.image}" if info.image else ""
        uptime_suffix = f" · up {format_uptime(info.uptime_s)}" if running else ""
        self._image_label.setText(suffix + uptime_suffix)

        # Action visibility — running vs stopped.
        self._btn_pause.setVisible(running)
        self._btn_restart.setVisible(running)
        self._btn_logs.setVisible(running)
        self._btn_play.setVisible(not running)

        # Stats row content.
        if running and stats is not None:
            cpu_text = f"CPU {stats.cpu_pct:.1f}%"
            self._cpu_label.setText(cpu_text)
            self._cpu_label.setStyleSheet(f"color: {ACCENT_BLUE};")
            mem_amber = _is_mem_high(stats)
            self._mem_label.setText(f"MEM {_format_mem_bytes(stats.mem_used_b)}")
            self._mem_label.setStyleSheet(f"color: {ACCENT_AMBER if mem_amber else ACCENT_GREEN};")
        else:
            self._cpu_label.setText("CPU —")
            self._cpu_label.setStyleSheet(f"color: {TEXT_MUTED};")
            self._mem_label.setText("MEM —")
            self._mem_label.setStyleSheet(f"color: {TEXT_MUTED};")

        self._ports_label.setText(" · ".join(info.ports) if info.ports else "")
        # Silence unused-token warning when QSS roles override colors directly.
        _ = TEXT_PRIMARY

    # ------------------------------------------------------------------ slots

    def _on_pause_clicked(self) -> None:
        self.action_requested.emit(self._info.id, "pause")

    def _on_restart_clicked(self) -> None:
        if self._confirm("Restart container", f"Restart {self._info.name}?"):
            self.action_requested.emit(self._info.id, "restart")

    def _on_logs_clicked(self) -> None:
        provider = self._logs_provider
        if provider is None:
            lines = ["(no logs available — provider not wired by the parent screen)"]
        else:
            try:
                lines = list(provider(self._info.id))
            except Exception as exc:  # noqa: BLE001 — never crash the UI for log fetch
                lines = [f"(log fetch failed: {exc})"]
        dialog = _LogsDialog(title=f"Logs · {self._info.name}", lines=lines, parent=self)
        dialog.exec()

    def _on_play_clicked(self) -> None:
        # Starting a container is a benign action — no confirmation per spec.
        self.action_requested.emit(self._info.id, "start")

    def _confirm(self, title: str, body: str) -> bool:
        """Show a Yes/No confirmation dialog. Returns ``True`` on accept."""
        result = QMessageBox.question(
            self,
            title,
            body,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    # Public stop action used by the screen when wiring a separate "stop" path —
    # the spec lists pause+restart+logs for running containers; stop is exposed
    # for completeness in case the screen layout decides to surface it.

    def emit_stop_with_confirmation(self) -> None:
        """Emit ``("id", "stop")`` after a confirmation dialog."""
        if self._confirm("Stop container", f"Stop {self._info.name}?"):
            self.action_requested.emit(self._info.id, "stop")
