"""SystemScreen integration tests — feed snapshots, assert wiring."""

from __future__ import annotations

from datetime import UTC, datetime

from healthsh.domain.metrics import (
    CpuMetric,
    LoadAverage,
    MetricsSnapshot,
    SwapMetric,
    SystemMetric,
    TempReading,
)
from healthsh.domain.process import ProcessInfo
from healthsh.ui.screens.system_screen import SystemScreen
from healthsh.ui.theme.palette import ACCENT_AMBER, ACCENT_BLUE


def _snapshot(
    *,
    per_core: tuple[float, ...] = (10.0, 90.0, 30.0, 50.0),
    cpu_cores: int = 4,
    temp_c: float = 48.0,
    swap_used_b: int = 500 * 1024 * 1024,
    swap_total_b: int = 4 * 1024**3,
    load: tuple[float, float, float] = (0.42, 0.55, 0.61),
    uptime_s: int = 3600 * 30,
    procs: tuple[ProcessInfo, ...] = (),
    sensors: tuple[TempReading, ...] | None = None,
    system: SystemMetric | None | object = ...,
) -> MetricsSnapshot:
    cpu = CpuMetric(
        overall_pct=sum(per_core) / max(len(per_core), 1),
        per_core_pct=per_core,
        physical_cores=cpu_cores,
        logical_cores=cpu_cores,
        freq_mhz=3200.0,
    )
    if system is ...:
        sensor_readings = (
            sensors if sensors is not None else (TempReading(sensor="coretemp", value_c=temp_c),)
        )
        system_metric: SystemMetric | None = SystemMetric(
            temps=sensor_readings,
            swap=SwapMetric(total_b=swap_total_b, used_b=swap_used_b),
            load=LoadAverage(*load),
            uptime_s=uptime_s,
        )
    else:
        system_metric = system  # type: ignore[assignment]
    return MetricsSnapshot(
        cpu=cpu,
        mem=None,
        disk=None,
        gpu=None,
        ts=datetime.now(tz=UTC),
        system=system_metric,
        processes_full=procs,
    )


def test_subtitle_includes_cores_load_and_uptime(qtbot) -> None:
    screen = SystemScreen()
    qtbot.addWidget(screen)
    screen.on_snapshot(_snapshot(cpu_cores=8))
    text = screen.header_subtitle()
    assert "8 cores" in text
    assert "load 0.42 / 0.55 / 0.61" in text
    assert "1d" in text  # 30 hours → "1d 6h"


def test_core_bars_render_one_cell_per_core(qtbot) -> None:
    screen = SystemScreen()
    qtbot.addWidget(screen)
    screen.on_snapshot(_snapshot(per_core=(1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0)))
    assert screen.core_bars().core_count() == 8


def test_per_core_threshold_flip_at_85_pct(qtbot) -> None:
    screen = SystemScreen()
    qtbot.addWidget(screen)
    screen.on_snapshot(_snapshot(per_core=(70.0, 90.0)))
    bars = screen.core_bars()
    assert bars.cell_color_at(0) == ACCENT_BLUE
    assert bars.cell_color_at(1) == ACCENT_AMBER


def test_temp_card_flips_amber_at_or_above_70(qtbot) -> None:
    screen = SystemScreen()
    qtbot.addWidget(screen)
    screen.on_snapshot(_snapshot(temp_c=72.0))
    style = screen._temp_card._value.styleSheet()  # type: ignore[attr-defined]
    assert ACCENT_AMBER.lower() in style.lower()


def test_temp_card_renders_n_a_without_sensors(qtbot) -> None:
    screen = SystemScreen()
    qtbot.addWidget(screen)
    screen.on_snapshot(_snapshot(sensors=()))
    text = screen._temp_card._value.text()  # type: ignore[attr-defined]
    assert text == "n/a"


def test_swap_card_reports_no_swap_when_total_is_zero(qtbot) -> None:
    screen = SystemScreen()
    qtbot.addWidget(screen)
    screen.on_snapshot(_snapshot(swap_total_b=0, swap_used_b=0))
    text = screen._swap_card._value.text()  # type: ignore[attr-defined]
    assert text == "no swap"


def test_swap_card_formats_used_over_total(qtbot) -> None:
    screen = SystemScreen()
    qtbot.addWidget(screen)
    screen.on_snapshot(_snapshot(swap_used_b=1024**3, swap_total_b=4 * 1024**3))
    text = screen._swap_card._value.text()  # type: ignore[attr-defined]
    assert "1.0" in text and "4.0" in text and "GiB" in text


def test_process_table_receives_processes_full(qtbot) -> None:
    procs = tuple(
        ProcessInfo(pid=i, name=f"p{i}", user="me", cpu_pct=1.0, mem_b=(i + 1) * 1024**2)
        for i in range(20)
    )
    screen = SystemScreen()
    qtbot.addWidget(screen)
    screen.on_snapshot(_snapshot(procs=procs))
    model = screen.process_table().model()
    assert model.rowCount() == 20


def test_process_count_card_shows_count(qtbot) -> None:
    procs = tuple(
        ProcessInfo(pid=i, name=f"p{i}", user="me", cpu_pct=0.0, mem_b=1024**2) for i in range(42)
    )
    screen = SystemScreen()
    qtbot.addWidget(screen)
    screen.on_snapshot(_snapshot(procs=procs))
    text = screen._proc_count_card._value.text()  # type: ignore[attr-defined]
    assert text == "42"


def test_subtitle_falls_back_when_system_missing(qtbot) -> None:
    screen = SystemScreen()
    qtbot.addWidget(screen)
    screen.on_snapshot(_snapshot(cpu_cores=6, system=None))
    text = screen.header_subtitle()
    assert "6 cores" in text
    assert "load —" in text and "up —" in text
