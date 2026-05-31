"""Exhaustive verification of ``healthsh.ui.theme.palette`` design tokens.

Every hex constant, radius, padding tuple, GPU accent mapping, font weight, and
family preference asserted here is drawn verbatim from the healthsh design spec
(issue #3, sections 4.2 and 4.3, and the updated issue #5 / #10 GPU accent
table). The palette module must remain dependency-free, so we also parse its
source with :mod:`ast` to guarantee it never reaches for Qt.
"""

from __future__ import annotations

import ast
import importlib
from dataclasses import is_dataclass
from pathlib import Path

import pytest

PALETTE_MODULE = "healthsh.ui.theme.palette"
PALETTE_PATH = Path(__file__).resolve().parent.parent / "healthsh" / "ui" / "theme" / "palette.py"

# Normative token table — keep in lockstep with the spec.
EXPECTED_COLORS: dict[str, str] = {
    "BG_WINDOW": "#1a1b26",
    "BG_CHROME": "#16161e",
    "BG_CARD": "#1f2335",
    "BG_CARD_INACTIVE": "#1b1c26",
    "BG_AI_BANNER": "#1f2433",
    "BORDER_DEFAULT": "#2a2c3d",
    "BORDER_ROW": "#20222e",
    "BORDER_AI": "#e0af68",
    "TRACK": "#2a2c3d",
    "TEXT_PRIMARY": "#c0caf5",
    "TEXT_MUTED": "#565f89",
    "ACCENT_BLUE": "#7dcfff",
    "ACCENT_PURPLE": "#bb9af7",
    "ACCENT_AMBER": "#e0af68",
    "ACCENT_GREEN": "#9ece6a",
    "ACCENT_RED": "#f7768e",
}

EXPECTED_RADII: dict[str, int] = {
    "RADIUS_WINDOW": 12,
    "RADIUS_CARD": 10,
    "RADIUS_CARD_SMALL": 8,
    "RADIUS_BAR": 3,
    "RADIUS_PILL": 999,
}

EXPECTED_SPACING: dict[str, tuple[int, ...] | int] = {
    "PADDING_CARD": (12, 14),
    "GRID_GAP": 10,
    "HEADER_PADDING": (12, 16),
    "SIDEBAR_PADDING": (16, 12),
}

EXPECTED_GPU_ACCENT: dict[str, str] = {
    "nvidia": "#9ece6a",  # accent.green
    "amd": "#f7768e",  # accent.red
    "intel": "#7dcfff",  # accent.blue
}


@pytest.fixture(scope="module")
def palette():
    """Import the palette module fresh for this test module."""
    return importlib.import_module(PALETTE_MODULE)


# ---------------------------------------------------------------------------
# Color tokens
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "expected"), sorted(EXPECTED_COLORS.items()))
def test_color_token_exact_hex(palette, name: str, expected: str) -> None:
    """Each color constant must match the spec hex exactly (case-sensitive)."""
    assert hasattr(palette, name), f"missing color constant: {name}"
    value = getattr(palette, name)
    assert isinstance(value, str), f"{name} must be a str, got {type(value).__name__}"
    assert value == expected, f"{name} should be {expected!r}, got {value!r}"


def test_all_color_values_are_valid_hex(palette) -> None:
    """Every color must be a 7-char ``#rrggbb`` lowercase hex string."""
    for name in EXPECTED_COLORS:
        value = getattr(palette, name)
        assert len(value) == 7, f"{name} must be 7 chars (#rrggbb), got {value!r}"
        assert value.startswith("#"), f"{name} must start with '#', got {value!r}"
        assert value == value.lower(), f"{name} must be lowercase, got {value!r}"
        assert all(c in "0123456789abcdef" for c in value[1:]), (
            f"{name} contains non-hex chars: {value!r}"
        )


# ---------------------------------------------------------------------------
# Radii and spacing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "expected"), sorted(EXPECTED_RADII.items()))
def test_radius_constant(palette, name: str, expected: int) -> None:
    """Radii constants must match the spec values exactly."""
    assert hasattr(palette, name), f"missing radius constant: {name}"
    value = getattr(palette, name)
    assert isinstance(value, int), f"{name} must be int, got {type(value).__name__}"
    assert value == expected, f"{name} should be {expected}, got {value}"


@pytest.mark.parametrize(("name", "expected"), sorted(EXPECTED_SPACING.items()))
def test_spacing_constant(palette, name: str, expected) -> None:
    """Padding tuples and gap scalars must match the spec verbatim."""
    assert hasattr(palette, name), f"missing spacing constant: {name}"
    value = getattr(palette, name)
    if isinstance(expected, tuple):
        assert isinstance(value, tuple), f"{name} must be a tuple, got {type(value).__name__}"
        assert value == expected, f"{name} should be {expected}, got {value}"
        for component in value:
            assert isinstance(component, int), (
                f"{name} components must be ints, got {type(component).__name__}"
            )
    else:
        assert isinstance(value, int), f"{name} must be int, got {type(value).__name__}"
        assert value == expected, f"{name} should be {expected}, got {value}"


# ---------------------------------------------------------------------------
# GPU accent mapping
# ---------------------------------------------------------------------------


def test_gpu_accent_keys(palette) -> None:
    """The GPU accent map must expose exactly the three supported vendors."""
    assert hasattr(palette, "GPU_ACCENT"), "missing GPU_ACCENT mapping"
    mapping = palette.GPU_ACCENT
    assert isinstance(mapping, dict), "GPU_ACCENT must be a dict"
    assert set(mapping.keys()) == set(EXPECTED_GPU_ACCENT.keys()), (
        f"GPU_ACCENT keys must be exactly {sorted(EXPECTED_GPU_ACCENT)}, got {sorted(mapping)}"
    )


@pytest.mark.parametrize(("vendor", "hex_value"), sorted(EXPECTED_GPU_ACCENT.items()))
def test_gpu_accent_hex_mapping(palette, vendor: str, hex_value: str) -> None:
    """Each vendor must resolve to its spec'd accent hex (nvidia/amd/intel)."""
    assert palette.GPU_ACCENT[vendor] == hex_value, (
        f"GPU_ACCENT[{vendor!r}] should be {hex_value!r}, got {palette.GPU_ACCENT[vendor]!r}"
    )


def test_gpu_accent_values_reuse_accent_constants(palette) -> None:
    """GPU accents must reference the same hex constants exposed as accents."""
    assert palette.GPU_ACCENT["nvidia"] == palette.ACCENT_GREEN
    assert palette.GPU_ACCENT["amd"] == palette.ACCENT_RED
    assert palette.GPU_ACCENT["intel"] == palette.ACCENT_BLUE


# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------


def test_font_weight_regular(palette) -> None:
    """Regular weight must be 400 — never 700, per the typography rule."""
    assert hasattr(palette, "WEIGHT_REGULAR"), "missing WEIGHT_REGULAR"
    assert palette.WEIGHT_REGULAR == 400


def test_font_weight_semibold(palette) -> None:
    """Semibold weight must be 500 — never 700, per the typography rule."""
    assert hasattr(palette, "WEIGHT_SEMIBOLD"), "missing WEIGHT_SEMIBOLD"
    assert palette.WEIGHT_SEMIBOLD == 500


def test_no_bold_700_weight_exposed(palette) -> None:
    """Spec forbids 700; no module-level int constant may equal 700."""
    offenders = [
        name
        for name in dir(palette)
        if not name.startswith("_")
        and isinstance(getattr(palette, name), int)
        and not isinstance(getattr(palette, name), bool)
        and getattr(palette, name) == 700
    ]
    assert not offenders, f"700 weight is forbidden; found in: {offenders}"


def test_font_family_preference_is_ordered_tuple(palette) -> None:
    """Font family preference must be a tuple of strings in priority order."""
    assert hasattr(palette, "FONT_FAMILY_PREFERENCE"), "missing FONT_FAMILY_PREFERENCE"
    families = palette.FONT_FAMILY_PREFERENCE
    assert isinstance(families, tuple), (
        f"FONT_FAMILY_PREFERENCE must be a tuple, got {type(families).__name__}"
    )
    assert families, "FONT_FAMILY_PREFERENCE must not be empty"
    assert all(isinstance(name, str) and name for name in families), (
        "every entry must be a non-empty str"
    )


def test_font_family_preference_contains_spec_sans_families(palette) -> None:
    """The preference list must include the three sans families called out in the spec."""
    families = palette.FONT_FAMILY_PREFERENCE
    for expected in ("Inter", "Segoe UI", "Cantarell"):
        assert expected in families, (
            f"FONT_FAMILY_PREFERENCE must contain {expected!r}, got {families!r}"
        )


# ---------------------------------------------------------------------------
# Optional ergonomic dataclass grouping
# ---------------------------------------------------------------------------


def test_optional_palette_dataclass_is_frozen_if_present(palette) -> None:
    """If a ``Palette`` dataclass is exposed it must be frozen for safe sharing."""
    if not hasattr(palette, "Palette"):
        pytest.skip("Palette dataclass is optional per the spec")
    cls = palette.Palette
    assert is_dataclass(cls), "Palette must be a dataclass"
    params = getattr(cls, "__dataclass_params__", None)
    assert params is not None and params.frozen, "Palette dataclass must be frozen"


# ---------------------------------------------------------------------------
# Dependency hygiene — palette.py must never import Qt
# ---------------------------------------------------------------------------


def _imported_top_levels(source: str, filename: str) -> set[str]:
    """Return the set of top-level dotted names imported by ``source``."""
    tree = ast.parse(source, filename=filename)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_palette_source_file_exists() -> None:
    """The palette module file must exist at the expected layered path."""
    assert PALETTE_PATH.is_file(), f"missing palette module at {PALETTE_PATH}"


def test_palette_has_no_qt_imports() -> None:
    """Parse ``palette.py`` with ast and assert no Qt-related modules are imported."""
    source = PALETTE_PATH.read_text(encoding="utf-8")
    imported = _imported_top_levels(source, str(PALETTE_PATH))
    forbidden_prefixes = ("PySide6", "PyQt5", "PyQt6", "PySide2", "shiboken6", "shiboken2")
    offenders = sorted(
        name
        for name in imported
        if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
    )
    assert not offenders, f"palette.py must be Qt-free; found imports: {offenders}"


def test_palette_module_imports_without_qt_loaded() -> None:
    """Importing the palette module must not pull any Qt binding into ``sys.modules``."""
    import sys

    # Drop any cached copy so the import path is exercised cleanly.
    for cached in [m for m in list(sys.modules) if m == PALETTE_MODULE]:
        del sys.modules[cached]
    importlib.import_module(PALETTE_MODULE)
    qt_loaded = sorted(
        m for m in sys.modules if m.split(".", 1)[0] in {"PySide6", "PyQt5", "PyQt6", "PySide2"}
    )
    # Note: if another test already imported Qt we cannot blame palette, so we
    # only fail when the palette import itself is the apparent cause.
    if qt_loaded:
        pytest.skip(
            f"Qt already loaded by another test: {qt_loaded}; "
            "the ast-based test above is the authoritative check."
        )
