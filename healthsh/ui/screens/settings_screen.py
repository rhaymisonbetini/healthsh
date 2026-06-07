"""Settings screen — five live-applying configuration sections (§5.6).

The screen is a pure *writer*: every row reads its initial value from the
injected :class:`SettingsService` and, on user edit, calls ``settings.set(...)``.
The runtime effects (worker retune, gauge recolour, backend swap, autostart)
are produced by :class:`~healthsh.services.settings_controller.SettingsController`
subscribing to ``setting_changed`` — so this module owns no worker references.
"""

from __future__ import annotations

from functools import partial

from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from healthsh.services.settings_service import SettingsService
from healthsh.ui.widgets.form_rows import (
    DropdownRow,
    IntRow,
    SliderRow,
    TextRow,
    ToggleRow,
)
from healthsh.ui.widgets.settings_card import SettingsCard

_SUBTITLE: str = "configuration"

# Backend storage-value ⇆ display-label, and theme value ⇆ label.
_BACKEND_LABELS: dict[str, str] = {"ollama": "Ollama", "anthropic": "Anthropic", "openai": "OpenAI"}
_THEME_LABELS: dict[str, str] = {"tokyo-night": "Tokyo Night"}
_ACCENTS: tuple[str, ...] = ("blue", "purple", "amber", "green")


def _invert(mapping: dict[str, str], label: str, fallback: str) -> str:
    """Return the storage value whose display label is ``label``."""
    for value, shown in mapping.items():
        if shown == label:
            return value
    return fallback


class SettingsScreen(QWidget):
    """Composed Settings screen wired to a :class:`SettingsService`."""

    def __init__(
        self,
        *,
        settings_service: SettingsService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings: SettingsService = settings_service or SettingsService()
        # key → row widget, for the controller wiring tests and introspection.
        self._rows: dict[str, QWidget] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        body = QWidget()
        self._column = QVBoxLayout(body)
        self._column.setContentsMargins(4, 4, 4, 4)
        self._column.setSpacing(12)
        scroll.setWidget(body)

        self._build_collection()
        self._build_ai()
        self._build_thresholds()
        self._build_appearance()
        self._build_system()
        self._column.addStretch(1)

    # ------------------------------------------------------------------ API

    def settings_service(self) -> SettingsService:
        """Expose the backing service (used by the controller and tests)."""
        return self._settings

    def row(self, key: str) -> QWidget:
        """Return the form row bound to ``key`` (``"ai.value"`` for the AI field)."""
        return self._rows[key]

    def header_subtitle(self) -> str:
        """Return the muted subtitle for the application header."""
        return _SUBTITLE

    # ------------------------------------------------------------- sections

    def _build_collection(self) -> None:
        card = SettingsCard("Collection")
        get = self._settings.get
        rows = (
            (
                "collection.metrics_interval_ms",
                IntRow("Metrics interval", minimum=250, maximum=5000, step=250, suffix=" ms"),
            ),
            (
                "collection.slow_interval_ms",
                IntRow(
                    "Docker / Logs interval", minimum=1000, maximum=15000, step=250, suffix=" ms"
                ),
            ),
            (
                "history.retain_days",
                IntRow("History retention", minimum=1, maximum=90, suffix=" d"),
            ),
        )
        for key, row in rows:
            row.set_value(get(key))
            row.changed.connect(partial(self._settings.set, key))
            card.add_row(row)
            self._rows[key] = row
        self._column.addWidget(card)

    def _build_ai(self) -> None:
        card = SettingsCard("AI")
        backend = self._settings.get("ai.backend")
        self._backend_row = DropdownRow("Backend", options=list(_BACKEND_LABELS.values()))
        self._backend_row.set_value(_BACKEND_LABELS.get(backend, "Ollama"))
        self._backend_row.changed.connect(self._on_backend_changed)
        card.add_row(self._backend_row)
        self._rows["ai.backend"] = self._backend_row

        self._ai_value_row = TextRow("Endpoint", placeholder="http://localhost:11434")
        self._sync_ai_value_row(backend)
        self._ai_value_row.changed.connect(self._on_ai_value_changed)
        card.add_row(self._ai_value_row)
        self._rows["ai.value"] = self._ai_value_row

        auto = ToggleRow("Auto insights on Dashboard")
        auto.set_value(self._settings.get("ai.auto_insights"))
        auto.changed.connect(partial(self._settings.set, "ai.auto_insights"))
        card.add_row(auto)
        self._rows["ai.auto_insights"] = auto
        self._column.addWidget(card)

    def _build_thresholds(self) -> None:
        card = SettingsCard("Alerts / thresholds")
        for prefix, label in (
            ("cpu", "CPU"),
            ("ram", "RAM"),
            ("disk", "Disk"),
            ("temp", "Temp"),
        ):
            self._threshold_pair(card, label, prefix)
        self._column.addWidget(card)

    def _threshold_pair(self, card: SettingsCard, label: str, prefix: str) -> None:
        warn_key = f"thresholds.{prefix}_warn"
        crit_key = f"thresholds.{prefix}_crit"
        warn = SliderRow(f"{label} warning", minimum=0, maximum=100)
        crit = SliderRow(f"{label} critical", minimum=0, maximum=100)
        warn.set_value(self._settings.get(warn_key))
        crit.set_value(self._settings.get(crit_key))
        card.add_row(warn)
        card.add_row(crit)
        self._rows[warn_key] = warn
        self._rows[crit_key] = crit
        caption = card.add_caption("")
        update = partial(self._update_threshold_preview, caption, warn, crit, label)
        warn.changed.connect(partial(self._on_threshold, warn_key, update))
        crit.changed.connect(partial(self._on_threshold, crit_key, update))
        update()

    def _build_appearance(self) -> None:
        card = SettingsCard("Appearance")
        theme = DropdownRow("Theme", options=list(_THEME_LABELS.values()))
        theme.set_value(_THEME_LABELS.get(self._settings.get("appearance.theme"), "Tokyo Night"))
        theme.changed.connect(
            lambda shown: self._settings.set(
                "appearance.theme", _invert(_THEME_LABELS, shown, "tokyo-night")
            )
        )
        card.add_row(theme)
        self._rows["appearance.theme"] = theme

        accent = DropdownRow("Accent", options=[a.capitalize() for a in _ACCENTS])
        accent.set_value(self._settings.get("appearance.accent").capitalize())
        accent.changed.connect(lambda shown: self._settings.set("appearance.accent", shown.lower()))
        card.add_row(accent)
        self._rows["appearance.accent"] = accent
        self._column.addWidget(card)

    def _build_system(self) -> None:
        card = SettingsCard("System")
        for key, label in (
            ("system.start_at_login", "Start at login"),
            ("system.minimize_to_tray", "Minimize to tray"),
            ("system.show_tray_icon", "Show tray icon"),
        ):
            row = ToggleRow(label)
            row.set_value(self._settings.get(key))
            row.changed.connect(partial(self._settings.set, key))
            card.add_row(row)
            self._rows[key] = row
        self._column.addWidget(card)

    # --------------------------------------------------------------- handlers

    def _on_backend_changed(self, shown: str) -> None:
        value = _invert(_BACKEND_LABELS, shown, "ollama")
        self._settings.set("ai.backend", value)
        self._sync_ai_value_row(value)

    def _sync_ai_value_row(self, backend: str) -> None:
        """Repoint the shared AI text row at the current backend's key/label."""
        if backend == "anthropic":
            key, label, password = "ai.anthropic_api_key", "API key", True
        elif backend == "openai":
            key, label, password = "ai.openai_api_key", "API key", True
        else:
            key, label, password = "ai.ollama_endpoint", "Endpoint", False
        self._ai_value_key = key
        self._ai_value_row.set_label(label)
        self._ai_value_row.set_password(password)
        self._ai_value_row.set_value(self._settings.get(key))

    def _on_ai_value_changed(self, text: str) -> None:
        self._settings.set(self._ai_value_key, text)

    def _on_threshold(self, key: str, update, value: int) -> None:
        self._settings.set(key, value)
        update()

    @staticmethod
    def _update_threshold_preview(caption, warn: SliderRow, crit: SliderRow, label: str) -> None:
        caption.setText(f"{label} gauges turn amber at {warn.value()} %, red at {crit.value()} %")
