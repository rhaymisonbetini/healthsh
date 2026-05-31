"""System tray icon and menu.

:class:`HealthTray` exposes typed signals so :class:`healthsh.ui.main_window.MainWindow`
can wire its own slots without the tray reaching back into the window. The
tray is created unconditionally; ``is_available()`` reports whether the
host actually has a system tray slot we can paint into.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from healthsh.ui.icons import get_icon
from healthsh.ui.theme.palette import ACCENT_GREEN


class HealthTray(QObject):
    """Lightweight wrapper around :class:`QSystemTrayIcon`."""

    show_requested = Signal()
    quit_requested = Signal()

    def __init__(self, *, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tray = QSystemTrayIcon(parent=parent)
        self._tray.setIcon(get_icon("activity-heartbeat", ACCENT_GREEN, 22))
        self._tray.setToolTip("Healthsh")

        # Build the context menu.
        self._menu = QMenu()
        self._action_show = QAction("Show / hide window", self._menu)
        self._action_show.triggered.connect(self.show_requested.emit)
        self._action_quit = QAction("Quit", self._menu)
        self._action_quit.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(self._action_show)
        self._menu.addSeparator()
        self._menu.addAction(self._action_quit)
        self._tray.setContextMenu(self._menu)

        # Single-click on the tray icon also restores the window.
        self._tray.activated.connect(self._on_activated)

    # ----------------------------------------------------------- public API

    def is_available(self) -> bool:
        """Return whether the current platform exposes a usable system tray."""
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show(self) -> None:
        """Make the tray icon visible (no-op if the platform has no tray)."""
        if not self.is_available():
            return
        self._tray.show()

    def hide(self) -> None:
        """Hide the tray icon."""
        self._tray.hide()

    def post_toast(self, title: str, message: str) -> None:
        """Display a balloon notification near the tray icon (best effort)."""
        if not self.is_available():
            return
        self._tray.showMessage(title, message, self._tray.icon())

    # ----------------------------------------------------------- internals

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Restore the window on a primary click on the tray icon."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_requested.emit()
