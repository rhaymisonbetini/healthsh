"""XDG autostart integration for the "Start at login" setting.

Dropping a ``.desktop`` file in ``$XDG_CONFIG_HOME/autostart`` (default
``~/.config/autostart``) makes a compliant desktop environment launch the app
at every login. This module owns the lifecycle of that single file:
:func:`enable_autostart` writes it, :func:`disable_autostart` removes it and
:func:`is_enabled` reports whether it is present.

Stdlib only — this is a leaf adapter with no Qt or project dependencies, so it
can be unit-tested by pointing ``XDG_CONFIG_HOME`` at a temp directory.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

_LOG = logging.getLogger(__name__)

# Name of the autostart entry we own. Stable so toggling off always finds it.
DESKTOP_FILENAME: str = "healthsh.desktop"

# CLI flag the autostart entry passes so the app boots hidden into the tray.
TRAY_FLAG: str = "--tray"


def _config_home() -> Path:
    """Return ``$XDG_CONFIG_HOME`` or the ``~/.config`` fallback."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


def autostart_dir() -> Path:
    """Return the XDG autostart directory (not guaranteed to exist yet)."""
    return _config_home() / "autostart"


def autostart_file_path() -> Path:
    """Return the absolute path of our ``healthsh.desktop`` autostart entry."""
    return autostart_dir() / DESKTOP_FILENAME


def _desktop_entry(exec_command: str) -> str:
    """Render the ``.desktop`` file body for ``exec_command``."""
    lines = (
        "[Desktop Entry]",
        "Type=Application",
        "Name=Healthsh",
        "Comment=AI-powered Linux system health monitor",
        f"Exec={exec_command}",
        "Icon=healthsh",
        "Terminal=false",
        "Categories=Utility;System;Monitor;",
        "X-GNOME-Autostart-enabled=true",
    )
    return "\n".join(lines) + "\n"


def resolve_executable() -> str | None:
    """Best-effort resolution of the command that should be auto-launched.

    Order of preference:

    1. ``$APPIMAGE`` — set by AppImage runtimes to the bundle's own path.
    2. ``healthsh`` on ``PATH`` (pip/pipx install of the console script).
    3. The current Python interpreter as a last resort.

    Returns ``None`` only if none of these resolve, so callers can surface a
    friendly error instead of writing a broken ``Exec=`` line.
    """
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return appimage
    found = shutil.which("healthsh")
    if found:
        return found
    if sys.executable:
        return sys.executable
    return None


def enable_autostart(executable_path: str | Path) -> Path:
    """Write the autostart entry pointing ``Exec=`` at ``executable_path --tray``.

    Returns the path of the written ``.desktop`` file.
    """
    exec_command = f"{executable_path} {TRAY_FLAG}"
    path = autostart_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_desktop_entry(exec_command), encoding="utf-8")
    _LOG.info("autostart enabled at %s", path)
    return path


def disable_autostart() -> None:
    """Remove the autostart entry. A missing file is treated as success."""
    path = autostart_file_path()
    try:
        path.unlink()
    except FileNotFoundError:
        return
    _LOG.info("autostart disabled (removed %s)", path)


def is_enabled() -> bool:
    """Return whether the autostart ``.desktop`` file currently exists."""
    return autostart_file_path().exists()


def apply_autostart(
    enabled: bool,
    *,
    executable_path: str | Path | None = None,
) -> bool:
    """Reconcile autostart state with ``enabled``.

    When enabling, ``executable_path`` is used if given, otherwise
    :func:`resolve_executable` is consulted. Returns ``True`` on success and
    ``False`` only when enabling was requested but no executable could be
    resolved (the caller should then show a friendly error in Settings).
    """
    if not enabled:
        disable_autostart()
        return True
    exec_path = executable_path or resolve_executable()
    if not exec_path:
        _LOG.warning("autostart requested but no executable could be resolved")
        return False
    enable_autostart(exec_path)
    return True
