"""Application entry point.

For Sprint 0 / issue #3 this opens a themed empty window so the Tokyo Night
palette and QSS can be validated end to end. The real chrome (header, sidebar,
screen routing) lands in issue #4.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMainWindow

from healthsh.ui.theme import apply_theme


def main() -> int:
    """Console entry point for the ``healthsh`` script.

    Returns:
        Exit status code returned from the Qt event loop.
    """
    app = QApplication(sys.argv)
    apply_theme(app)

    window = QMainWindow()
    window.setWindowTitle("Healthsh")
    window.resize(600, 400)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
