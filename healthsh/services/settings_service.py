"""Typed settings facade the rest of the app reads and writes configuration from.

:class:`SettingsService` wraps the storage adapter
(:class:`~healthsh.infra.settings_store.SettingsStore`) and adds three things
the raw store does not provide:

* **A schema** — every key, its python type and default value, declared once in
  the :class:`Settings` dataclass. :data:`DEFAULTS` is derived from it so the
  two can never drift.
* **Typed access** — :meth:`get` falls back to the schema default (so callers
  need not repeat it) and :meth:`snapshot` materialises the whole config into a
  frozen :class:`Settings` for read-heavy consumers (workers, gauges).
* **Change notification** — :meth:`set` emits :pyattr:`setting_changed` so
  subscribers (workers, services, UI) reconfigure live without re-reading disk.

Dotted keys map to dataclass attributes by replacing the first ``.`` with ``_``
(``"thresholds.cpu_warn"`` ⇆ ``thresholds_cpu_warn``).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TypeVar

from PySide6.QtCore import QObject, Signal

from healthsh.infra.settings_store import SettingsStore

T = TypeVar("T")


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of every Healthsh setting with its default value.

    Field names mirror the dotted setting keys with the first ``_`` standing in
    for the section separator (``collection_metrics_interval_ms`` ⇆
    ``collection.metrics_interval_ms``).
    """

    # Collection cadence.
    collection_metrics_interval_ms: int = 1000
    collection_slow_interval_ms: int = 3000
    history_retain_days: int = 7

    # AI backend.
    ai_backend: str = "ollama"
    ai_ollama_endpoint: str = "http://localhost:11434"
    ai_anthropic_api_key: str = ""
    ai_openai_api_key: str = ""
    ai_auto_insights: bool = True

    # Alert thresholds (gauge colour flip points, percent).
    thresholds_cpu_warn: int = 75
    thresholds_cpu_crit: int = 90
    thresholds_ram_warn: int = 75
    thresholds_ram_crit: int = 90
    thresholds_disk_warn: int = 75
    thresholds_disk_crit: int = 90
    thresholds_temp_warn: int = 70
    thresholds_temp_crit: int = 85

    # Appearance.
    appearance_theme: str = "tokyo-night"
    appearance_accent: str = "blue"

    # System integration.
    system_start_at_login: bool = False
    system_minimize_to_tray: bool = True
    system_show_tray_icon: bool = True


def _attr_to_key(attr: str) -> str:
    """``collection_metrics_interval_ms`` → ``collection.metrics_interval_ms``."""
    return attr.replace("_", ".", 1)


def _key_to_attr(key: str) -> str:
    """``thresholds.cpu_warn`` → ``thresholds_cpu_warn``."""
    return key.replace(".", "_")


# Single source of truth for "key → default", derived from the dataclass so the
# schema and the snapshot can never disagree.
DEFAULTS: dict[str, object] = {
    _attr_to_key(field.name): getattr(Settings(), field.name)
    for field in dataclasses.fields(Settings)
}

# Sentinel so ``get(key)`` can distinguish "no default passed" from ``None``.
_UNSET: object = object()


class SettingsService(QObject):
    """Typed, signalling configuration service backed by :class:`SettingsStore`."""

    # Emitted with the dotted key whenever :meth:`set` writes a value.
    setting_changed = Signal(str)

    def __init__(
        self,
        *,
        store: SettingsStore | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Create the service.

        Args:
            store: Storage adapter to use. Defaults to the native per-user
                :class:`SettingsStore`; tests inject one pointed at a tmp file.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._store: SettingsStore = store or SettingsStore()

    # ------------------------------------------------------------------ API

    def get(self, key: str, default: T | object = _UNSET) -> T:
        """Return the typed value for ``key``.

        When ``default`` is omitted the schema default is used (and the value is
        coerced to its type). Passing an explicit ``default`` also drives the
        coercion, mirroring :meth:`SettingsStore.get`.
        """
        if default is _UNSET:
            if key not in DEFAULTS:
                raise KeyError(f"unknown setting key: {key!r}")
            default = DEFAULTS[key]
        return self._store.get(key, default)  # type: ignore[arg-type]

    def set(self, key: str, value: object) -> None:
        """Persist ``value`` for ``key`` and emit :pyattr:`setting_changed`.

        Known keys are coerced to their schema type before storage so a UI that
        hands us a stray string still round-trips as the declared type.
        """
        self._store.set(key, _typed(value, DEFAULTS.get(key)))
        self.setting_changed.emit(key)

    def snapshot(self) -> Settings:
        """Materialise every setting into a frozen :class:`Settings`."""
        values = {_key_to_attr(key): self.get(key) for key in DEFAULTS}
        return Settings(**values)  # type: ignore[arg-type]

    def store(self) -> SettingsStore:
        """Expose the underlying store (used by tests and diagnostics)."""
        return self._store


def _typed(value: object, default: object) -> object:
    """Coerce ``value`` to the type of ``default`` for storage symmetry."""
    if default is None:
        return value
    if isinstance(default, bool):
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "on"}
        return bool(value)
    if isinstance(default, int):
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return value
    if isinstance(default, float):
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return value
    if isinstance(default, str):
        return str(value)
    return value
