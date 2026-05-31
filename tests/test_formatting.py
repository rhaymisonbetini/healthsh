"""Pure formatter tests — table-driven, deterministic."""

from __future__ import annotations

import pytest

from healthsh.core.formatting import (
    bytes_to_gb,
    format_gpu_label,
    format_pct,
    format_temp_c,
    format_uptime,
)
from healthsh.domain.metrics import GpuMetric


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, 0.0),
        (1024 * 1024 * 1024, 1.0),
        (16 * 1024 * 1024 * 1024, 16.0),
        (1_500_000_000, 1_500_000_000 / (1024**3)),
    ],
)
def test_bytes_to_gb(raw: int, expected: float) -> None:
    assert bytes_to_gb(raw) == pytest.approx(expected)


def test_bytes_to_gb_rejects_negative() -> None:
    with pytest.raises(ValueError):
        bytes_to_gb(-1)


@pytest.mark.parametrize(
    ("value", "decimals", "expected"),
    [(34.0, 0, "34%"), (12.5, 1, "12.5%"), (100.0, 0, "100%"), (0.0, 0, "0%")],
)
def test_format_pct(value: float, decimals: int, expected: str) -> None:
    assert format_pct(value, decimals=decimals) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(48.2, "48°C"), (None, "n/a"), (0.0, "0°C"), (99.9, "100°C")],
)
def test_format_temp_c(value: float | None, expected: str) -> None:
    assert format_temp_c(value) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0m"),
        (59, "0m"),
        (60, "1m"),
        (3599, "59m"),
        (3600, "1h 0m"),
        (3660, "1h 1m"),
        (86_399, "23h 59m"),
        (86_400, "1d 0h"),
        (172_800, "2d 0h"),
    ],
)
def test_format_uptime(seconds: int, expected: str) -> None:
    assert format_uptime(seconds) == expected


def test_format_uptime_rejects_negative() -> None:
    with pytest.raises(ValueError):
        format_uptime(-1)


def test_format_gpu_label_none() -> None:
    """Absent GPU yields an empty string so the UI hides the section."""
    assert format_gpu_label(None) == ""


def test_format_gpu_label_nvidia_with_temp() -> None:
    metric = GpuMetric("nvidia", "RTX 4070", 12.0, None, None, 48.0)
    assert format_gpu_label(metric) == "NVIDIA · 48°C"


def test_format_gpu_label_amd_with_temp() -> None:
    metric = GpuMetric("amd", "Radeon RX 7800 XT", 30.0, None, None, 52.0)
    assert format_gpu_label(metric) == "AMD · 52°C"


def test_format_gpu_label_intel_is_shared() -> None:
    metric = GpuMetric("intel", "Intel iGPU", 22.0, None, None, None)
    assert format_gpu_label(metric) == "Intel · shared"


def test_format_gpu_label_nvidia_without_temp() -> None:
    metric = GpuMetric("nvidia", "RTX 4070", 12.0, None, None, None)
    assert format_gpu_label(metric) == "NVIDIA · n/a"
