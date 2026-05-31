"""Dashboard composition tests — adaptive gauge row, snapshot wiring."""

from __future__ import annotations

from datetime import UTC, datetime

from healthsh.domain.metrics import (
    CpuMetric,
    DiskMetric,
    GpuMetric,
    MemMetric,
    MetricsSnapshot,
)
from healthsh.ui.screens import dashboard_screen as ds_mod
from healthsh.ui.screens.dashboard_screen import _GPU_DECISION_TICKS, DashboardScreen


def _snap(
    *,
    cpu_pct: float = 25.0,
    mem_pct: float = 40.0,
    disk_pct: float = 50.0,
    gpu: GpuMetric | None = None,
) -> MetricsSnapshot:
    return MetricsSnapshot(
        cpu=CpuMetric(
            overall_pct=cpu_pct,
            per_core_pct=(cpu_pct,),
            physical_cores=4,
            logical_cores=8,
            freq_mhz=3200.0,
        ),
        mem=MemMetric(
            total_b=16 * 1024**3, used_b=int(mem_pct / 100 * 16 * 1024**3), percent=mem_pct
        ),
        disk=DiskMetric(
            mountpoint="/", total_b=1024**4, used_b=int(disk_pct / 100 * 1024**4), percent=disk_pct
        ),
        gpu=gpu,
        ts=datetime.now(tz=UTC),
    )


def test_subtitle_includes_distro(qtbot, monkeypatch) -> None:
    """Subtitle is 'system health · <PRETTY_NAME>'."""

    def _fake_distro() -> str:
        return "Ubuntu 24.04 LTS"

    monkeypatch.setattr(ds_mod, "_read_distro_pretty_name", _fake_distro)
    s = DashboardScreen()
    qtbot.addWidget(s)
    # Re-run the constructor effect by setting a fresh attribute (private),
    # since DashboardScreen reads the distro at __init__ time.
    s._distro = _fake_distro()
    assert s.header_subtitle() == "system health · Ubuntu 24.04 LTS"


def test_header_right_widget_is_live_chip(qtbot) -> None:
    s = DashboardScreen()
    qtbot.addWidget(s)
    chip = s.header_right_widget()
    assert chip is not None
    # The chip's only child label should contain the live text.
    from PySide6.QtWidgets import QLabel

    labels = chip.findChildren(QLabel)
    assert any("live" in lbl.text() for lbl in labels)


def test_gauge_row_adds_gpu_when_present(qtbot) -> None:
    s = DashboardScreen()
    qtbot.addWidget(s)
    assert not s.has_gpu_gauge()
    gpu = GpuMetric(
        vendor="amd", name="Radeon", util_pct=12.0, mem_used_b=None, mem_total_b=None, temp_c=42.0
    )
    s.on_snapshot(_snap(gpu=gpu))
    assert s.has_gpu_gauge()


def test_gauge_row_stays_three_when_no_gpu_after_decision_ticks(qtbot) -> None:
    s = DashboardScreen()
    qtbot.addWidget(s)
    for _ in range(_GPU_DECISION_TICKS):
        s.on_snapshot(_snap(gpu=None))
    # Even if a GPU appears after the decision threshold, the spec keeps
    # the row at three (decision is final to avoid layout flicker).
    gpu = GpuMetric(
        vendor="amd", name="Radeon", util_pct=12.0, mem_used_b=None, mem_total_b=None, temp_c=None
    )
    s.on_snapshot(_snap(gpu=gpu))
    # Decision was made first → ensure_gpu_gauge skipped because gpu_card is None
    # but the decision flag is True. The gauge should NOT have been built.
    assert not s.has_gpu_gauge()


def test_partial_snapshot_does_not_crash(qtbot) -> None:
    s = DashboardScreen()
    qtbot.addWidget(s)
    snapshot = MetricsSnapshot(cpu=None, mem=None, disk=None, gpu=None, ts=datetime.now(tz=UTC))
    s.on_snapshot(snapshot)  # must not raise
