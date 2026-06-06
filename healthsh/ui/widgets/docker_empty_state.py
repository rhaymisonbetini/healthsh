"""``DockerEmptyState(QWidget)`` — calm informational view for the four no-Docker kinds.

This widget never renders red accents — the no-Docker UX is **informational,
not alarming**. It picks one of four variants from :class:`DockerStatus.kind`
and adds the matching action button: an *Install Docker* link, a
*Re-check now* button, or a click-to-copy mono snippet.

The widget is scoped to ``not_installed``, ``daemon_down``, ``permission_denied``
and ``unknown``. The ``ok`` kind is handled by the cards view in #19, not here.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from healthsh.domain.container import DockerStatus
from healthsh.ui.icons import get_icon_pixmap
from healthsh.ui.theme.palette import (
    BG_CARD,
    BG_WINDOW,
    TEXT_MUTED,
    TEXT_PRIMARY,
)

# Centred card geometry.
_CARD_MAX_WIDTH: int = 480
_LOGO_SIZE: int = 36

# Docker install docs URL (#19 task list).
_INSTALL_DOCS_URL: str = "https://docs.docker.com/engine/install/"

# Snippet shown in the permission_denied empty state.
_PERMISSION_SNIPPET: str = "sudo usermod -aG docker $USER"

# How long the "copied" toast stays visible (ms).
_COPIED_TOAST_MS: int = 1600


def _mono_font() -> QFont:
    font = QFont("JetBrains Mono")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPixelSize(12)
    return font


class _CopyableSnippet(QFrame):
    """One-line mono snippet with a clipboard icon; click anywhere to copy."""

    copied = Signal(str)

    def __init__(self, *, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text
        self.setProperty("role", "card-small")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        label = QLabel(text)
        label.setFont(_mono_font())
        label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(label, stretch=1)

        icon = QLabel()
        icon.setFixedSize(16, 16)
        icon.setPixmap(get_icon_pixmap("copy", TEXT_MUTED, 16))
        layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event) -> None:  # noqa: D401 — Qt callback
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._text)
        self.copied.emit(self._text)
        super().mousePressEvent(event)


class DockerEmptyState(QWidget):
    """Centered informational card matching :class:`DockerStatus.kind`."""

    recheck_requested = Signal()

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addStretch(1)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)

        self._card = QFrame()
        self._card.setProperty("role", "card")
        self._card.setMaximumWidth(_CARD_MAX_WIDTH)
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(20, 24, 20, 24)
        card_layout.setSpacing(10)

        logo = QLabel()
        logo.setFixedSize(_LOGO_SIZE, _LOGO_SIZE)
        logo.setPixmap(get_icon_pixmap("brand-docker", TEXT_MUTED, _LOGO_SIZE))
        card_layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._title_label = QLabel()
        self._title_label.setProperty("role", "section-title")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self._title_label)

        self._body_label = QLabel()
        self._body_label.setProperty("role", "muted")
        self._body_label.setWordWrap(True)
        self._body_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card_layout.addWidget(self._body_label)

        # Slot for the per-kind action (link button / recheck button / snippet).
        self._action_slot = QWidget()
        self._action_slot_layout = QVBoxLayout(self._action_slot)
        self._action_slot_layout.setContentsMargins(0, 0, 0, 0)
        self._action_slot_layout.setSpacing(6)
        card_layout.addWidget(self._action_slot)

        # Toast feedback for the copy snippet.
        self._toast_label = QLabel("")
        self._toast_label.setProperty("role", "hint")
        self._toast_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self._toast_label)

        row.addWidget(self._card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

        self._current_kind: str = ""
        # Silence unused-token warnings for QSS fallback colours.
        _ = (BG_CARD, BG_WINDOW)

    # ------------------------------------------------------------------ API

    def set_status(self, status: DockerStatus) -> None:
        """Render the variant matching ``status.kind``."""
        kind = status.kind
        if kind == self._current_kind:
            # Refresh body to pick up new `detail` for the unknown case.
            if kind == "unknown":
                self._body_label.setText(self._body_for_unknown(status.detail))
            return
        self._current_kind = kind
        self._clear_action_slot()
        self._toast_label.setText("")

        if kind == "not_installed":
            self._title_label.setText("Docker is not installed")
            self._body_label.setText(
                "Healthsh works fine without it. This screen will appear "
                "automatically when Docker becomes available on this machine."
            )
            self._add_link_button("Install Docker →", _INSTALL_DOCS_URL)
        elif kind == "daemon_down":
            self._title_label.setText("Docker daemon is not running")
            self._body_label.setText(
                "Docker is installed but the daemon is stopped. Start it with:"
            )
            self._add_snippet("sudo systemctl start docker", click_to_copy=True)
            self._add_recheck_button()
        elif kind == "permission_denied":
            self._title_label.setText("Permission denied for the Docker socket")
            self._body_label.setText(
                "Docker is installed but your user can't access /var/run/docker.sock. "
                "Add yourself to the docker group and log out / back in."
            )
            self._add_snippet(_PERMISSION_SNIPPET, click_to_copy=True)
        elif kind == "unknown":
            self._title_label.setText("Docker is unavailable")
            self._body_label.setText(self._body_for_unknown(status.detail))
            self._add_recheck_button()
        else:
            # Fallback — never expected for kind=='ok' because the screen swaps
            # to the cards view in that case.
            self._title_label.setText("Docker is unavailable")
            self._body_label.setText("Healthsh couldn't reach Docker.")

    def current_kind(self) -> str:
        """Return the last :class:`DockerStatus.kind` rendered (used by tests)."""
        return self._current_kind

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _body_for_unknown(detail: str) -> str:
        if detail:
            return f"Healthsh couldn't reach Docker. The latest error was: {detail}"
        return "Healthsh couldn't reach Docker."

    def _clear_action_slot(self) -> None:
        while self._action_slot_layout.count():
            item = self._action_slot_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _add_link_button(self, text: str, url: str) -> None:
        button = QPushButton(text)
        button.setProperty("role", "primary")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setIconSize(QSize(14, 14))
        button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        self._action_slot_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _add_recheck_button(self) -> None:
        button = QPushButton("Re-check now")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(self.recheck_requested)
        self._action_slot_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _add_snippet(self, text: str, *, click_to_copy: bool) -> None:
        snippet = _CopyableSnippet(text=text)
        if click_to_copy:
            snippet.copied.connect(self._on_copied)
        self._action_slot_layout.addWidget(snippet)

    def _on_copied(self, _: str) -> None:
        self._toast_label.setText("copied to clipboard")
        # Schedule the toast to clear; QTimer.singleShot keeps this Qt-native.
        from PySide6.QtCore import QTimer

        QTimer.singleShot(_COPIED_TOAST_MS, lambda: self._toast_label.setText(""))

    # Public seam used by tests to flush the recheck signal without QDesktopServices.
    def emit_recheck(self) -> None:
        """Programmatically emit ``recheck_requested`` (used by tests)."""
        self.recheck_requested.emit()


def install_docs_url() -> str:
    """Return the install docs URL (exposed for tests / docs cross-checks)."""
    return _INSTALL_DOCS_URL


def permission_snippet() -> str:
    """Return the click-to-copy snippet for the permission_denied state."""
    return _PERMISSION_SNIPPET
