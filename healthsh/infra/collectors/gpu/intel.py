"""Intel integrated GPU collector via ``/sys`` reads.

Detection: walks ``/sys/class/drm/card*/device/uevent`` looking for
``DRIVER=i915`` or ``DRIVER=xe``. Utilization is approximated as the ratio of
current to maximum render-engine frequency (Intel sysfs does not expose a
direct ``gpu_busy_percent`` knob). VRAM and temperature are reported as
``None`` because integrated GPUs share system RAM and the package thermal
sensor is already surfaced by the CPU collector.
"""

from __future__ import annotations

import logging
from pathlib import Path

from healthsh.domain.metrics import GpuMetric

_LOG = logging.getLogger(__name__)

_INTEL_DRIVERS: frozenset[str] = frozenset({"i915", "xe"})


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _device_driver(uevent_path: Path) -> str | None:
    text = _read_text(uevent_path)
    if text is None:
        return None
    for line in text.splitlines():
        if line.startswith("DRIVER="):
            return line.split("=", 1)[1].strip()
    return None


def _find_intel_card(sysfs_root: Path) -> Path | None:
    drm_root = sysfs_root / "class" / "drm"
    if not drm_root.is_dir():
        return None
    for card_dir in sorted(drm_root.glob("card[0-9]*")):
        if "-" in card_dir.name:
            continue
        driver = _device_driver(card_dir / "device" / "uevent")
        if driver in _INTEL_DRIVERS:
            return card_dir
    return None


def _read_first_existing(*candidates: Path) -> str | None:
    """Return the contents of the first existing file in ``candidates``."""
    for path in candidates:
        if path.exists():
            return _read_text(path)
    return None


def collect_intel(*, sysfs_root: Path = Path("/sys")) -> GpuMetric | None:
    """Return a :class:`GpuMetric` for the first Intel GPU, or ``None``.

    Args:
        sysfs_root: Filesystem root to probe (defaults to ``/sys``). Tests
            inject a temporary directory.
    """
    card_dir = _find_intel_card(sysfs_root)
    if card_dir is None:
        return None

    # Utilization proxy via render-engine frequency ratio.
    cur = _parse_float(
        _read_first_existing(
            card_dir / "gt_cur_freq_mhz",
            card_dir / "gt_act_freq_mhz",
            card_dir / "device" / "drm" / card_dir.name / "gt_cur_freq_mhz",
        )
    )
    rp0 = _parse_float(
        _read_first_existing(
            card_dir / "gt_RP0_freq_mhz",
            card_dir / "gt_max_freq_mhz",
        )
    )

    util_pct: float | None
    if cur is not None and rp0 is not None and rp0 > 0:
        util_pct = max(0.0, min(100.0, (cur / rp0) * 100.0))
    else:
        util_pct = None

    return GpuMetric(
        vendor="intel",
        name="Intel integrated GPU",
        util_pct=util_pct,
        mem_used_b=None,
        mem_total_b=None,
        temp_c=None,
    )
