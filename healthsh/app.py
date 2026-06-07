"""Application bootstrap.

Creates the :class:`QApplication`, applies the Tokyo Night theme, instantiates
:class:`healthsh.ui.main_window.MainWindow`, attaches the system tray icon and
runs the Qt event loop until the user quits.

The ``--tray`` flag (used by the XDG autostart entry from #30) boots the app
hidden into the system tray: monitoring starts immediately but the main window
stays out of the way until the user clicks the tray icon.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from healthsh.infra.autostart import TRAY_FLAG
from healthsh.ui.main_window import MainWindow
from healthsh.ui.theme import apply_theme
from healthsh.ui.tray import HealthTray


def tray_mode_requested(argv: list[str]) -> bool:
    """Return whether ``--tray`` is present in ``argv`` (start hidden to tray)."""
    return TRAY_FLAG in argv


def main(argv: list[str] | None = None) -> int:
    """Console entry point for the ``healthsh`` script.

    Args:
        argv: Argument vector; defaults to :data:`sys.argv`.

    Returns:
        Exit status code returned from the Qt event loop.
    """
    args = list(sys.argv if argv is None else argv)
    start_hidden = tray_mode_requested(args)

    QApplication.setApplicationName("Healthsh")
    QApplication.setOrganizationName("Healthsh")
    QApplication.setApplicationDisplayName("Healthsh")
    # Closing the last visible window must NOT quit the app when the tray
    # is the persistent surface — we manage quit explicitly via the tray menu.
    QApplication.setQuitOnLastWindowClosed(False)

    app = QApplication(args)
    apply_theme(app)

    window = MainWindow()

    tray = HealthTray(parent=window)
    window.attach_tray(tray)

    if start_hidden:
        # Autostart launch: keep the window hidden but begin collecting now so
        # the tray is live from boot (the window's showEvent would otherwise be
        # what kicks the collectors off).
        window.collector_service().start()
    else:
        window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
