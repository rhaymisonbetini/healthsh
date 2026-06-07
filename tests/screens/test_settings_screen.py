"""SettingsScreen tests — rows read from and write back to SettingsService."""

from __future__ import annotations

from pathlib import Path

import pytest

from healthsh.infra.settings_store import SettingsStore
from healthsh.services.settings_service import SettingsService
from healthsh.ui.screens.settings_screen import SettingsScreen


@pytest.fixture
def service(tmp_path: Path) -> SettingsService:
    return SettingsService(store=SettingsStore(path=tmp_path / "Healthsh.conf"))


def _make(qtbot, service: SettingsService) -> SettingsScreen:
    screen = SettingsScreen(settings_service=service)
    qtbot.addWidget(screen)
    return screen


def test_rows_initialize_from_persisted_values(qtbot, service: SettingsService) -> None:
    service.set("collection.metrics_interval_ms", 2000)
    service.set("thresholds.cpu_warn", 60)
    screen = _make(qtbot, service)
    assert screen.row("collection.metrics_interval_ms").value() == 2000
    assert screen.row("thresholds.cpu_warn").value() == 60


def test_int_row_writes_to_service(qtbot, service: SettingsService) -> None:
    screen = _make(qtbot, service)
    screen.row("collection.metrics_interval_ms")._spin.setValue(2000)  # type: ignore[attr-defined]
    assert service.get("collection.metrics_interval_ms") == 2000


def test_threshold_slider_writes_to_service(qtbot, service: SettingsService) -> None:
    screen = _make(qtbot, service)
    screen.row("thresholds.cpu_warn")._slider.setValue(50)  # type: ignore[attr-defined]
    assert service.get("thresholds.cpu_warn") == 50


def test_toggle_writes_bool(qtbot, service: SettingsService) -> None:
    screen = _make(qtbot, service)
    screen.row("system.start_at_login")._check.setChecked(True)  # type: ignore[attr-defined]
    assert service.get("system.start_at_login") is True


def test_api_key_field_masked_by_default_for_key_backend(qtbot, service: SettingsService) -> None:
    screen = _make(qtbot, service)
    # Default backend (ollama) shows the endpoint, unmasked.
    assert screen.row("ai.value").is_masked() is False
    screen.row("ai.backend")._combo.setCurrentText("Anthropic")  # type: ignore[attr-defined]
    assert service.get("ai.backend") == "anthropic"
    # The shared field now targets the API key and is masked.
    assert screen.row("ai.value").is_masked() is True


def test_ai_value_writes_to_current_backend_key(qtbot, service: SettingsService) -> None:
    screen = _make(qtbot, service)
    screen.row("ai.backend")._combo.setCurrentText("OpenAI")  # type: ignore[attr-defined]
    row = screen.row("ai.value")
    row._edit.setText("sk-test")  # type: ignore[attr-defined]
    row._edit.editingFinished.emit()  # type: ignore[attr-defined]
    assert service.get("ai.openai_api_key") == "sk-test"


def test_header_subtitle(qtbot, service: SettingsService) -> None:
    screen = _make(qtbot, service)
    assert screen.header_subtitle() == "configuration"
