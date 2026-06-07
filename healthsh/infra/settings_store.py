"""Persistent key/value store backed by :class:`QSettings`.

:class:`SettingsStore` is the thin storage adapter the
:class:`~healthsh.services.settings_service.SettingsService` sits on top of.
It hides two awkward facts about ``QSettings``:

* With the INI-style backend used on Linux every value round-trips through
  text, so reads come back as strings (``"75"``, ``"true"``). The store coerces
  each value back to the type of the supplied default before returning it.
* The native constructor scatters arguments (format, scope, org, app). The
  store offers a single ``path=`` shortcut so tests can point it at a temp file.

Default on Linux the backing file is ``~/.config/Healthsh/Healthsh.conf``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from PySide6.QtCore import QSettings

# QSettings organisation / application — keep in lock-step with the values set
# on ``QApplication`` in ``healthsh.app`` so both resolve to the same file.
ORGANIZATION: str = "Healthsh"
APPLICATION: str = "Healthsh"

T = TypeVar("T")

# Strings QSettings/IniFormat may produce for a boolean ``true``.
_TRUTHY: frozenset[str] = frozenset({"true", "1", "yes", "on"})


def _coerce_bool(raw: object) -> bool:
    """Coerce a raw QSettings value into a ``bool``."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    return str(raw).strip().lower() in _TRUTHY


def _coerce(raw: object, default: T) -> T:
    """Coerce a raw QSettings value to the type of ``default``.

    ``bool`` is checked before ``int`` because ``bool`` is an ``int`` subclass.
    On any conversion failure the typed ``default`` is returned so a corrupted
    settings file can never crash a reader.
    """
    # ``bool`` must precede ``int`` — ``isinstance(True, int)`` is ``True``.
    if isinstance(default, bool):
        return _coerce_bool(raw)  # type: ignore[return-value]
    if isinstance(default, int):
        try:
            return int(raw)  # type: ignore[arg-type, return-value]
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        try:
            return float(raw)  # type: ignore[arg-type, return-value]
        except (TypeError, ValueError):
            return default
    if isinstance(default, str):
        return str(raw)  # type: ignore[return-value]
    return raw  # type: ignore[return-value]


class SettingsStore:
    """Typed wrapper over :class:`QSettings` with IniFormat persistence."""

    def __init__(
        self,
        *,
        settings: QSettings | None = None,
        path: str | Path | None = None,
    ) -> None:
        """Create the store.

        Args:
            settings: An existing :class:`QSettings` to wrap (advanced/testing).
            path: A file path to use as an ``IniFormat`` store. Mutually
                exclusive with ``settings``; mainly used by tests pointing at a
                temp directory. When both are ``None`` the native per-user
                location (``~/.config/Healthsh/Healthsh.conf`` on Linux) is used.
        """
        if settings is not None:
            self._settings = settings
        elif path is not None:
            self._settings = QSettings(str(path), QSettings.Format.IniFormat)
        else:
            # NativeFormat on Linux is INI-style and lands at
            # ``~/.config/Healthsh/Healthsh.conf`` — the path the spec calls for.
            self._settings = QSettings(
                QSettings.Format.NativeFormat,
                QSettings.Scope.UserScope,
                ORGANIZATION,
                APPLICATION,
            )

    def get(self, key: str, default: T) -> T:
        """Return ``key`` coerced to the type of ``default``, or ``default``."""
        if not self._settings.contains(key):
            return default
        return _coerce(self._settings.value(key), default)

    def set(self, key: str, value: object) -> None:
        """Persist ``value`` under ``key`` and flush to disk immediately."""
        self._settings.setValue(key, value)
        self._settings.sync()

    def contains(self, key: str) -> bool:
        """Return whether ``key`` has an explicitly stored value."""
        return self._settings.contains(key)

    def remove(self, key: str) -> None:
        """Delete ``key`` so subsequent reads fall back to the default."""
        self._settings.remove(key)
        self._settings.sync()

    def clear(self) -> None:
        """Remove every stored key (used by tests for a clean slate)."""
        self._settings.clear()
        self._settings.sync()

    def file_path(self) -> str:
        """Return the absolute path of the backing ``.conf`` file."""
        return self._settings.fileName()
