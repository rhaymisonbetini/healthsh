"""SettingsController tests — setting_changed drives live runtime effects."""

from __future__ import annotations

from pathlib import Path

import pytest

from healthsh.infra import autostart
from healthsh.infra.settings_store import SettingsStore
from healthsh.services.ai_service import AIService, MockBackend, _BackendTurn
from healthsh.services.collector_service import CollectorService
from healthsh.services.settings_controller import SettingsController
from healthsh.services.settings_service import Settings, SettingsService


@pytest.fixture
def service(tmp_path: Path) -> SettingsService:
    return SettingsService(store=SettingsStore(path=tmp_path / "Healthsh.conf"))


class _FakeDashboard:
    def __init__(self) -> None:
        self.snap: Settings | None = None

    def apply_thresholds(self, snap: Settings) -> None:
        self.snap = snap


class _FakeWindow:
    def __init__(self) -> None:
        self.minimize: bool | None = None

    def set_minimize_to_tray(self, value: bool) -> None:
        self.minimize = value


def test_collection_change_retunes_both_workers(qtbot, service: SettingsService) -> None:
    collector = CollectorService()
    controller = SettingsController(settings=service, collector=collector)
    controller.apply_all()
    service.set("collection.metrics_interval_ms", 2000)
    assert collector.interval_s() == 2.0
    service.set("collection.slow_interval_ms", 6000)
    assert collector.slow_interval_s() == 6.0


def test_threshold_change_reapplies_to_dashboard(qtbot, service: SettingsService) -> None:
    dash = _FakeDashboard()
    controller = SettingsController(settings=service, dashboard=dash)
    controller.apply_all()
    service.set("thresholds.cpu_warn", 50)
    assert dash.snap is not None
    assert dash.snap.thresholds_cpu_warn == 50


def test_minimize_to_tray_toggles_window(qtbot, service: SettingsService) -> None:
    win = _FakeWindow()
    controller = SettingsController(settings=service, window=win)
    controller.apply_all()
    assert win.minimize is True  # default applied by apply_all
    service.set("system.minimize_to_tray", False)
    assert win.minimize is False


def test_ai_backend_swaps_on_change(qtbot, service: SettingsService) -> None:
    ai = AIService(backend=MockBackend(script=[_BackendTurn(text="x")]))
    controller = SettingsController(settings=service, ai_service=ai)
    controller.apply_all()
    service.set("ai.backend", "openai")
    assert ai.current_backend() == "openai"


def test_autostart_reconciles_on_toggle(
    qtbot, service: SettingsService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    controller = SettingsController(settings=service, executable_path="/usr/bin/healthsh")
    controller.apply_all()  # must not touch the filesystem
    assert autostart.is_enabled() is False
    service.set("system.start_at_login", True)
    assert autostart.is_enabled() is True
    service.set("system.start_at_login", False)
    assert autostart.is_enabled() is False


def test_apply_all_pushes_current_snapshot(qtbot, service: SettingsService) -> None:
    collector = CollectorService()
    dash = _FakeDashboard()
    service.set("collection.metrics_interval_ms", 1500)
    controller = SettingsController(settings=service, collector=collector, dashboard=dash)
    controller.apply_all()
    assert collector.interval_s() == 1.5
    assert dash.snap is not None
