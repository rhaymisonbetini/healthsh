"""AMD GPU collector tests — fake sysfs trees."""

from __future__ import annotations

from pathlib import Path

from healthsh.infra.collectors.gpu.amd import collect_amd


def _build_amd_sysfs(
    root: Path,
    *,
    util: str = "37",
    mem_used: str = "536870912",
    mem_total: str = "8589934592",
    temp_milli_c: str | None = "55000",
    product: str = "Radeon RX 7800 XT",
) -> None:
    """Write a minimal /sys layout for a single amdgpu card."""
    card = root / "class" / "drm" / "card0"
    device = card / "device"
    device.mkdir(parents=True)
    (device / "uevent").write_text("DRIVER=amdgpu\nPCI_ID=1002:744C\n")
    (device / "gpu_busy_percent").write_text(util + "\n")
    (device / "mem_info_vram_used").write_text(mem_used + "\n")
    (device / "mem_info_vram_total").write_text(mem_total + "\n")
    (device / "product").write_text(product + "\n")
    if temp_milli_c is not None:
        hwmon = device / "hwmon" / "hwmon3"
        hwmon.mkdir(parents=True)
        (hwmon / "name").write_text("amdgpu\n")
        (hwmon / "temp1_input").write_text(temp_milli_c + "\n")


def test_returns_none_without_sysfs(tmp_path: Path) -> None:
    """Empty sysfs root → no card → None."""
    (tmp_path / "class").mkdir()
    assert collect_amd(sysfs_root=tmp_path) is None


def test_happy_path(tmp_path: Path) -> None:
    _build_amd_sysfs(tmp_path)
    metric = collect_amd(sysfs_root=tmp_path)
    assert metric is not None
    assert metric.vendor == "amd"
    assert metric.name == "Radeon RX 7800 XT"
    assert metric.util_pct == 37.0
    assert metric.mem_used_b == 536_870_912
    assert metric.mem_total_b == 8_589_934_592
    assert metric.temp_c == 55.0


def test_skips_non_amd_driver(tmp_path: Path) -> None:
    """A card with a different driver must be ignored."""
    card = tmp_path / "class" / "drm" / "card0" / "device"
    card.mkdir(parents=True)
    (card / "uevent").write_text("DRIVER=i915\n")
    assert collect_amd(sysfs_root=tmp_path) is None


def test_missing_temp_sensor_returns_none_temp(tmp_path: Path) -> None:
    _build_amd_sysfs(tmp_path, temp_milli_c=None)
    metric = collect_amd(sysfs_root=tmp_path)
    assert metric is not None
    assert metric.temp_c is None


def test_skips_connector_subdirs(tmp_path: Path) -> None:
    """Names like ``card0-DP-1`` are DRM connectors, not cards — skip them."""
    drm = tmp_path / "class" / "drm"
    drm.mkdir(parents=True)
    connector = drm / "card0-DP-1" / "device"
    connector.mkdir(parents=True)
    (connector / "uevent").write_text("DRIVER=amdgpu\n")
    # And no real card0 with amdgpu driver.
    assert collect_amd(sysfs_root=tmp_path) is None
