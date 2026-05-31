"""Application entry point.

This module is a placeholder for issue #1 — it makes the ``healthsh`` console
script declared in ``pyproject.toml`` resolvable so ``pip install -e .`` produces
a working install. The real Qt bootstrap lands in issue #4.
"""

from __future__ import annotations

import sys


def main() -> int:
    """Console entry point for the ``healthsh`` script.

    Returns:
        Exit status code (0 on success). Always exits with a clear message
        until the Qt bootstrap from issue #4 replaces this stub.
    """
    sys.stderr.write(
        "healthsh: the application bootstrap is not yet implemented.\n"
        "This stub exists so the package installs cleanly.\n"
        "Follow the roadmap — issue #4 wires up the main window.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
