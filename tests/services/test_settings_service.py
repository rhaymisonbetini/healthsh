"""SettingsService / SettingsStore tests — persistence, signals, coercion."""

from __future__ import annotations

from pathlib import Path

import pytest

from healthsh.infra.settings_store import SettingsStore
from healthsh.services.settings_service import DEFAULTS, Settings, SettingsService


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    """Return a per-test temp path standing in for ``Healthsh.conf``."""
    return tmp_path / "Healthsh.conf"


def test_defaults_returned_when_unset(qapp, store_path: Path) -> None:
    svc = SettingsService(store=SettingsStore(path=store_path))
    assert svc.get("thresholds.cpu_warn") == 75
    assert svc.get("ai.backend") == "ollama"
    assert svc.get("system.minimize_to_tray") is True


def test_set_then_get_roundtrips(qapp, store_path: Path) -> None:
    svc = SettingsService(store=SettingsStore(path=store_path))
    svc.set("thresholds.cpu_warn", 50)
    assert svc.get("thresholds.cpu_warn") == 50


def test_type_coercion_returns_int_not_str(qapp, store_path: Path) -> None:
    store = SettingsStore(path=store_path)
    # Simulate a stringly-typed value already on disk (IniFormat stores text).
    store.set("thresholds.cpu_warn", "80")
    svc = SettingsService(store=store)
    value = svc.get("thresholds.cpu_warn", 75)
    assert value == 80
    assert isinstance(value, int)


def test_bool_coercion_from_text(qapp, store_path: Path) -> None:
    store = SettingsStore(path=store_path)
    store.set("system.start_at_login", "true")
    svc = SettingsService(store=store)
    assert svc.get("system.start_at_login") is True


def test_persists_across_restart(qapp, store_path: Path) -> None:
    svc = SettingsService(store=SettingsStore(path=store_path))
    svc.set("collection.metrics_interval_ms", 2000)
    # Simulate an app restart: brand-new store + service on the same file.
    reopened = SettingsService(store=SettingsStore(path=store_path))
    assert reopened.get("collection.metrics_interval_ms") == 2000


def test_setting_changed_fires_exactly_once(qapp, store_path: Path) -> None:
    svc = SettingsService(store=SettingsStore(path=store_path))
    seen: list[str] = []
    svc.setting_changed.connect(seen.append)
    svc.set("ai.backend", "openai")
    assert seen == ["ai.backend"]


def test_snapshot_is_fully_typed(qapp, store_path: Path) -> None:
    store = SettingsStore(path=store_path)
    store.set("thresholds.cpu_warn", "55")
    store.set("system.show_tray_icon", "false")
    svc = SettingsService(store=store)
    snap = svc.snapshot()
    assert isinstance(snap, Settings)
    assert snap.thresholds_cpu_warn == 55
    assert snap.system_show_tray_icon is False
    assert snap.ai_backend == "ollama"  # untouched key falls back to default


def test_unknown_key_without_default_raises(qapp, store_path: Path) -> None:
    svc = SettingsService(store=SettingsStore(path=store_path))
    with pytest.raises(KeyError):
        svc.get("does.not.exist")


def test_native_store_file_path_is_conf(qapp) -> None:
    store = SettingsStore()
    assert store.file_path().endswith("Healthsh/Healthsh.conf")


def test_schema_and_snapshot_stay_in_lockstep() -> None:
    assert len(DEFAULTS) == len(Settings.__dataclass_fields__)
