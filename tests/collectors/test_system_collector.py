"""Tests for the temp + system collectors and the load formatter."""

from __future__ import annotations

import psutil
import pytest

from healthsh.core.formatting import format_load
from healthsh.domain.metrics import LoadAverage, SystemMetric, TempReading
from healthsh.infra.collectors import system_collector, temp_collector
from healthsh.infra.collectors.system_collector import collect_system
from healthsh.infra.collectors.temp_collector import collect_temps


class _ShwTemp:
    """Minimal psutil.shwtemp shape used by the fakes below."""

    def __init__(self, label: str, current: float) -> None:
        self.label = label
        self.current = current
        self.high: float | None = None
        self.critical: float | None = None


def test_collect_temps_returns_empty_when_psutil_lacks_sensors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """psutil without ``sensors_temperatures`` (or returning nothing) → empty dict."""
    monkeypatch.setattr(psutil, "sensors_temperatures", lambda: {}, raising=False)
    assert collect_temps() == {}


def test_collect_temps_swallows_collector_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """If sensors_temperatures raises, we report no temps — never propagate."""

    def _boom() -> dict:
        raise RuntimeError("synthetic sensor failure")

    monkeypatch.setattr(psutil, "sensors_temperatures", _boom, raising=False)
    assert collect_temps() == {}


def test_collect_temps_picks_package_id_zero_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``coretemp`` → prefer ``Package id 0`` over individual core entries."""
    fake = {
        "coretemp": [
            _ShwTemp("Core 0", 42.0),
            _ShwTemp("Core 1", 55.0),
            _ShwTemp("Package id 0", 60.0),
        ],
        "acpitz": [_ShwTemp("", 38.0)],
    }
    monkeypatch.setattr(psutil, "sensors_temperatures", lambda: fake, raising=False)
    out = collect_temps()
    assert out == {"coretemp": 60.0, "acpitz": 38.0}


def test_collect_temps_handles_amd_tctl_naming(monkeypatch: pytest.MonkeyPatch) -> None:
    """AMD chips use ``Tctl`` / ``Tdie`` instead of ``Package id 0``."""
    fake = {
        "k10temp": [
            _ShwTemp("Tdie", 50.0),
            _ShwTemp("Tctl", 52.0),
        ],
    }
    monkeypatch.setattr(psutil, "sensors_temperatures", lambda: fake, raising=False)
    out = collect_temps()
    # Tctl appears earlier in the priority list — it wins.
    assert out == {"k10temp": 52.0}


def test_collect_temps_falls_back_to_first_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """No preferred label → take the first non-zero current, then the first overall."""
    fake = {
        "weirdo": [
            _ShwTemp("foo", 0.0),
            _ShwTemp("bar", 47.5),
        ],
        "empty-chip": [],
    }
    monkeypatch.setattr(psutil, "sensors_temperatures", lambda: fake, raising=False)
    out = collect_temps()
    assert out == {"weirdo": 47.5}


def test_collect_system_returns_typed_metric() -> None:
    """Real-machine smoke test — shape and ranges must be sensible."""
    metric = collect_system()
    assert isinstance(metric, SystemMetric)
    assert isinstance(metric.temps, tuple)
    assert all(isinstance(t, TempReading) for t in metric.temps)
    assert metric.swap.total_b >= 0
    assert 0 <= metric.swap.used_b <= max(metric.swap.total_b, metric.swap.used_b)
    assert isinstance(metric.load, LoadAverage)
    assert metric.load.one >= 0.0
    assert metric.load.five >= 0.0
    assert metric.load.fifteen >= 0.0
    # The host is up — uptime should be strictly positive on any CI runner.
    assert metric.uptime_s > 0


def test_collect_system_emits_sorted_temp_readings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The collector serialises the dict into a deterministic, sorted tuple."""
    monkeypatch.setattr(
        temp_collector, "collect_temps", lambda: {"zeta": 30.0, "alpha": 50.0, "mid": 40.0}
    )
    # Re-import inside the test scope so monkeypatch above is honored.
    monkeypatch.setattr(system_collector, "collect_temps", temp_collector.collect_temps)
    metric = collect_system()
    sensors = [t.sensor for t in metric.temps]
    assert sensors == ["alpha", "mid", "zeta"]


def test_collect_system_when_no_loadavg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing ``os.getloadavg`` (Windows path) yields a zero LoadAverage."""
    import os as _os

    monkeypatch.delattr(_os, "getloadavg", raising=False)
    metric = collect_system()
    assert metric.load == LoadAverage(0.0, 0.0, 0.0)


def test_format_load_accepts_load_average() -> None:
    assert format_load(LoadAverage(0.5, 1.0, 2.0)) == "0.50 / 1.00 / 2.00"


def test_format_load_accepts_tuple() -> None:
    assert format_load((0.42, 0.55, 0.61)) == "0.42 / 0.55 / 0.61"


def test_format_load_rejects_negative_values() -> None:
    with pytest.raises(ValueError):
        format_load((-1.0, 0.0, 0.0))
