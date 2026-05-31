"""Design tokens for the Healthsh UI theme system.

This module is intentionally dependency-free. It exposes the normative color,
radius, spacing, typography, and gpu-accent constants described in the
healthsh ui spec (issue #3, sections 4.2 and 4.3) as plain python values so
they can be consumed by qss assembly, tests, and any non-qt tooling without
forcing a qt import at module load time.

Every hex value here is normative and must match the spec table exactly.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Background tokens.
# ---------------------------------------------------------------------------
BG_WINDOW: str = "#1a1b26"
BG_CHROME: str = "#16161e"
BG_CARD: str = "#1f2335"
BG_CARD_INACTIVE: str = "#1b1c26"
BG_AI_BANNER: str = "#1f2433"

# ---------------------------------------------------------------------------
# Border tokens.
# ---------------------------------------------------------------------------
BORDER_DEFAULT: str = "#2a2c3d"
BORDER_ROW: str = "#20222e"
BORDER_AI: str = "#e0af68"

# ---------------------------------------------------------------------------
# Track (progress / slider rails).
# ---------------------------------------------------------------------------
TRACK: str = "#2a2c3d"

# ---------------------------------------------------------------------------
# Text tokens.
# ---------------------------------------------------------------------------
TEXT_PRIMARY: str = "#c0caf5"
TEXT_MUTED: str = "#565f89"

# ---------------------------------------------------------------------------
# Accent tokens.
# ---------------------------------------------------------------------------
ACCENT_BLUE: str = "#7dcfff"
ACCENT_PURPLE: str = "#bb9af7"
ACCENT_AMBER: str = "#e0af68"
ACCENT_GREEN: str = "#9ece6a"
ACCENT_RED: str = "#f7768e"

# ---------------------------------------------------------------------------
# Radii (px). Pill is intentionally large to round any reasonable height.
# ---------------------------------------------------------------------------
RADIUS_WINDOW: int = 12
RADIUS_CARD: int = 10
RADIUS_CARD_SMALL: int = 8
RADIUS_BAR: int = 3
RADIUS_PILL: int = 999

# ---------------------------------------------------------------------------
# Padding and spacing (px). Tuples are (vertical, horizontal) to mirror the
# css shorthand "padding: V H".
# ---------------------------------------------------------------------------
PADDING_CARD: tuple[int, int] = (12, 14)
GRID_GAP: int = 10
HEADER_PADDING: tuple[int, int] = (12, 16)
SIDEBAR_PADDING: tuple[int, int] = (16, 12)

# ---------------------------------------------------------------------------
# Per-vendor gpu accent mapping (issue #5 / #10).
# Keys are lowercase canonical vendor identifiers.
# ---------------------------------------------------------------------------
GPU_ACCENT: dict[str, str] = {
    "nvidia": ACCENT_GREEN,
    "amd": ACCENT_RED,
    "intel": ACCENT_BLUE,
}

# ---------------------------------------------------------------------------
# Typography. System sans only; mono is reserved for pids/ports and lives in
# its own module when needed. Two weights only -- never 700.
# ---------------------------------------------------------------------------
FONT_FAMILY_PREFERENCE: tuple[str, ...] = (
    "Inter",
    "Segoe UI",
    "Cantarell",
    "Noto Sans",
    "DejaVu Sans",
    "Sans Serif",
)

WEIGHT_REGULAR: int = 400
WEIGHT_SEMIBOLD: int = 500


@dataclass(frozen=True)
class Palette:
    """Ergonomic grouping of the design tokens.

    Prefer the module-level constants for direct lookups; this dataclass is
    handy when passing the full token set around (for example, into a qss
    builder or a preview tool) without enumerating every name.
    """

    # Backgrounds.
    bg_window: str = BG_WINDOW
    bg_chrome: str = BG_CHROME
    bg_card: str = BG_CARD
    bg_card_inactive: str = BG_CARD_INACTIVE
    bg_ai_banner: str = BG_AI_BANNER

    # Borders.
    border_default: str = BORDER_DEFAULT
    border_row: str = BORDER_ROW
    border_ai: str = BORDER_AI

    # Track.
    track: str = TRACK

    # Text.
    text_primary: str = TEXT_PRIMARY
    text_muted: str = TEXT_MUTED

    # Accents.
    accent_blue: str = ACCENT_BLUE
    accent_purple: str = ACCENT_PURPLE
    accent_amber: str = ACCENT_AMBER
    accent_green: str = ACCENT_GREEN
    accent_red: str = ACCENT_RED

    # Radii.
    radius_window: int = RADIUS_WINDOW
    radius_card: int = RADIUS_CARD
    radius_card_small: int = RADIUS_CARD_SMALL
    radius_bar: int = RADIUS_BAR
    radius_pill: int = RADIUS_PILL

    # Spacing.
    padding_card: tuple[int, int] = PADDING_CARD
    grid_gap: int = GRID_GAP
    header_padding: tuple[int, int] = HEADER_PADDING
    sidebar_padding: tuple[int, int] = SIDEBAR_PADDING

    # Typography.
    font_family_preference: tuple[str, ...] = FONT_FAMILY_PREFERENCE
    weight_regular: int = WEIGHT_REGULAR
    weight_semibold: int = WEIGHT_SEMIBOLD


PALETTE: Palette = Palette()


__all__ = [
    "ACCENT_AMBER",
    "ACCENT_BLUE",
    "ACCENT_GREEN",
    "ACCENT_PURPLE",
    "ACCENT_RED",
    "BG_AI_BANNER",
    "BG_CARD",
    "BG_CARD_INACTIVE",
    "BG_CHROME",
    "BG_WINDOW",
    "BORDER_AI",
    "BORDER_DEFAULT",
    "BORDER_ROW",
    "FONT_FAMILY_PREFERENCE",
    "GPU_ACCENT",
    "GRID_GAP",
    "HEADER_PADDING",
    "PADDING_CARD",
    "PALETTE",
    "Palette",
    "RADIUS_BAR",
    "RADIUS_CARD",
    "RADIUS_CARD_SMALL",
    "RADIUS_PILL",
    "RADIUS_WINDOW",
    "SIDEBAR_PADDING",
    "TEXT_MUTED",
    "TEXT_PRIMARY",
    "TRACK",
    "WEIGHT_REGULAR",
    "WEIGHT_SEMIBOLD",
]
