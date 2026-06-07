"""Applies live :class:`SettingsService` changes to the running subsystems.

The Settings *screen* only writes values; this controller is the *subscriber*
that turns those writes into runtime effects, keeping the UI decoupled from the
workers, gauges and OS integration it ultimately drives:

* ``collection.*`` → retunes the collector worker cadences,
* ``thresholds.*`` → re-applies gauge colour thresholds on the Dashboard,
* ``system.minimize_to_tray`` → flips the window's hide-to-tray behaviour,
* ``system.start_at_login`` → reconciles the XDG autostart entry (#30),
* ``ai.*`` → hot-swaps the :class:`AIService` backend.

Targets are duck-typed and optional so the controller carries no dependency on
the UI layer and tests can inject only what they assert on.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject

from healthsh.infra import autostart
from healthsh.services.ai_service import AIService, backend_from_settings
from healthsh.services.settings_service import Settings, SettingsService

_LOG = logging.getLogger(__name__)


class SettingsController(QObject):
    """Reconcile running subsystems with the persisted settings."""

    def __init__(
        self,
        *,
        settings: SettingsService,
        collector: Any | None = None,
        dashboard: Any | None = None,
        window: Any | None = None,
        ai_service: AIService | None = None,
        executable_path: str | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._collector = collector
        self._dashboard = dashboard
        self._window = window
        self._ai = ai_service
        self._executable_path = executable_path
        settings.setting_changed.connect(self._on_changed)

    # ------------------------------------------------------------------ API

    def apply_all(self) -> None:
        """Push the current snapshot to every target except autostart.

        Autostart is intentionally excluded — it is filesystem-side-effecting,
        so it is only reconciled in response to an explicit user toggle.
        """
        snap = self._settings.snapshot()
        self._apply_collection(snap)
        self._apply_thresholds(snap)
        self._apply_minimize(snap)
        self._apply_ai(snap)

    # --------------------------------------------------------------- routing

    def _on_changed(self, key: str) -> None:
        snap = self._settings.snapshot()
        if key == "system.start_at_login":
            self._apply_autostart(snap)
        elif key == "system.minimize_to_tray":
            self._apply_minimize(snap)
        elif key.startswith("collection."):
            self._apply_collection(snap)
        elif key.startswith("thresholds."):
            self._apply_thresholds(snap)
        elif key.startswith("ai."):
            self._apply_ai(snap)

    # --------------------------------------------------------------- appliers

    def _apply_collection(self, snap: Settings) -> None:
        if self._collector is None:
            return
        self._collector.set_interval_ms(snap.collection_metrics_interval_ms)
        self._collector.set_slow_interval_ms(snap.collection_slow_interval_ms)

    def _apply_thresholds(self, snap: Settings) -> None:
        if self._dashboard is not None and hasattr(self._dashboard, "apply_thresholds"):
            self._dashboard.apply_thresholds(snap)

    def _apply_minimize(self, snap: Settings) -> None:
        if self._window is not None and hasattr(self._window, "set_minimize_to_tray"):
            self._window.set_minimize_to_tray(snap.system_minimize_to_tray)

    def _apply_autostart(self, snap: Settings) -> bool:
        """Reconcile the autostart entry; return success (False = unresolved exec)."""
        ok = autostart.apply_autostart(
            snap.system_start_at_login, executable_path=self._executable_path
        )
        if not ok:
            _LOG.warning("could not enable autostart: no runnable executable resolved")
        return ok

    def _apply_ai(self, snap: Settings) -> None:
        if self._ai is not None:
            self._ai.set_backend(backend_from_settings(snap))
