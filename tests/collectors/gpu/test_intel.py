"""Intel iGPU collector tests — fake sysfs trees."""

from __future__ import annotations

from pathlib import Path

from healthsh.infra.collectors.gpu.intel import collect_intel


def _build_intel_sysfs(
    root: Path,
    *,
    driver: str = "i915",
    cur_freq_mhz: str = "700",
    rp0_freq_mhz: str = "1400",
) -> None:
    card = root / "class" / "drm" / "card0"
    device = card / "device"
    card.mkdir(parents=True)
    device.mkdir(parents=True)
    (device / "uevent").write_text(f"DRIVER={driver}\n")
    (card / "gt_cur_freq_mhz").write_text(cur_freq_mhz + "\n")
    (card / "gt_RP0_freq_mhz").write_text(rp0_freq_mhz + "\n")


def test_returns_none_without_intel_card(tmp_path: Path) -> None:
    assert collect_intel(sysfs_root=tmp_path) is None


def test_happy_path_i915(tmp_path: Path) -> None:
    _build_intel_sysfs(tmp_path, driver="i915", cur_freq_mhz="700", rp0_freq_mhz="1400")
    metric = collect_intel(sysfs_root=tmp_path)
    assert metric is not None
    assert metric.vendor == "intel"
    assert metric.name == "Intel integrated GPU"
    assert metric.util_pct == 50.0
    assert metric.mem_used_b is None
    assert metric.mem_total_b is None
    assert metric.temp_c is None


def test_xe_driver_is_also_intel(tmp_path: Path) -> None:
    _build_intel_sysfs(tmp_path, driver="xe", cur_freq_mhz="100", rp0_freq_mhz="1000")
    metric = collect_intel(sysfs_root=tmp_path)
    assert metric is not None
    assert metric.util_pct == 10.0


def test_clamps_to_100(tmp_path: Path) -> None:
    """If the kernel reports cur > rp0 we must not exceed 100%."""
    _build_intel_sysfs(tmp_path, cur_freq_mhz="2000", rp0_freq_mhz="1400")
    metric = collect_intel(sysfs_root=tmp_path)
    assert metric is not None
    assert metric.util_pct == 100.0


def test_unknown_freq_yields_none_util(tmp_path: Path) -> None:
    card = tmp_path / "class" / "drm" / "card0" / "device"
    card.mkdir(parents=True)
    (card / "uevent").write_text("DRIVER=i915\n")
    metric = collect_intel(sysfs_root=tmp_path)
    assert metric is not None
    assert metric.util_pct is None
