"""AMD Radeon GPU collector via ``/sys`` reads.

Detection: walks ``/sys/class/drm/card*/device/uevent`` looking for
``DRIVER=amdgpu``. For the first match we read utilization, VRAM usage and
the amdgpu hwmon temperature sensor. Like the NVIDIA collector, this never
raises — every failure path returns ``None`` so the chain can move on.
"""

from __future__ import annotations

import logging
from pathlib import Path

from healthsh.domain.metrics import GpuMetric

_LOG = logging.getLogger(__name__)


def _read_text(path: Path) -> str | None:
    """Read ``path`` and return stripped text; ``None`` on any failure."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _device_from_uevent(uevent_path: Path) -> str | None:
    """Extract the ``DRIVER=...`` value from a uevent file."""
    text = _read_text(uevent_path)
    if text is None:
        return None
    for line in text.splitlines():
        if line.startswith("DRIVER="):
            return line.split("=", 1)[1].strip()
    return None


def _gpu_name(card_dir: Path) -> str:
    """Best-effort human-readable name for the AMD card."""
    # ``device/product`` is the SKU string when the kernel exposes it.
    name = _read_text(card_dir / "device" / "product")
    if name:
        return name
    # ``model`` is the underlying friendly model on some kernels.
    name = _read_text(card_dir / "device" / "model")
    if name:
        return name
    return "AMD Radeon"


def _find_amdgpu_card(sysfs_root: Path) -> Path | None:
    """Return the first ``cardN`` directory whose driver is ``amdgpu``."""
    drm_root = sysfs_root / "class" / "drm"
    if not drm_root.is_dir():
        return None
    for card_dir in sorted(drm_root.glob("card[0-9]*")):
        # Skip card subdirectories like card0-DP-1 (connectors).
        if "-" in card_dir.name:
            continue
        if _device_from_uevent(card_dir / "device" / "uevent") == "amdgpu":
            return card_dir
    return None


def _find_amdgpu_hwmon(card_device_dir: Path) -> Path | None:
    """Return the hwmon directory whose ``name`` is ``amdgpu``."""
    hwmon_root = card_device_dir / "hwmon"
    if not hwmon_root.is_dir():
        return None
    for entry in sorted(hwmon_root.iterdir()):
        if _read_text(entry / "name") == "amdgpu":
            return entry
    return None


def collect_amd(*, sysfs_root: Path = Path("/sys")) -> GpuMetric | None:
    """Return a :class:`GpuMetric` for the first AMD Radeon GPU, or ``None``.

    Args:
        sysfs_root: Filesystem root to probe (defaults to ``/sys``). Tests
            inject a temporary directory.
    """
    card_dir = _find_amdgpu_card(sysfs_root)
    if card_dir is None:
        return None

    device_dir = card_dir / "device"

    util_pct = _parse_float(_read_text(device_dir / "gpu_busy_percent"))
    mem_used_b = _parse_int(_read_text(device_dir / "mem_info_vram_used"))
    mem_total_b = _parse_int(_read_text(device_dir / "mem_info_vram_total"))

    temp_c: float | None = None
    hwmon = _find_amdgpu_hwmon(device_dir)
    if hwmon is not None:
        raw_milli_c = _parse_float(_read_text(hwmon / "temp1_input"))
        if raw_milli_c is not None:
            temp_c = raw_milli_c / 1000.0

    return GpuMetric(
        vendor="amd",
        name=_gpu_name(card_dir),
        util_pct=util_pct,
        mem_used_b=mem_used_b,
        mem_total_b=mem_total_b,
        temp_c=temp_c,
    )
