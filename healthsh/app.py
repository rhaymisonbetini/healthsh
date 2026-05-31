"""Application bootstrap.

Creates the :class:`QApplication`, applies the Tokyo Night theme, instantiates
:class:`healthsh.ui.main_window.MainWindow`, and runs the Qt event loop until
the user quits.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from healthsh.ui.main_window import MainWindow
from healthsh.ui.theme import apply_theme


def main() -> int:
    """Console entry point for the ``healthsh`` script.

    Returns:
        Exit status code returned from the Qt event loop.
    """
    QApplication.setApplicationName("Healthsh")
    QApplication.setOrganizationName("Healthsh")
    QApplication.setApplicationDisplayName("Healthsh")

    app = QApplication(sys.argv)
    apply_theme(app)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
