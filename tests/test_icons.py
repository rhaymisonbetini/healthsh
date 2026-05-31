"""Icon registry tests — all bundled SVGs load, recolor and rasterize."""

from __future__ import annotations

import pytest

from healthsh.ui.icons import AVAILABLE_ICONS, IconNotFoundError, get_icon, get_icon_pixmap
from healthsh.ui.theme.palette import ACCENT_BLUE, TEXT_MUTED


@pytest.mark.parametrize("name", sorted(AVAILABLE_ICONS))
def test_every_icon_loads(qapp, name: str) -> None:  # noqa: ARG001 — qapp is the side effect
    """Every name in AVAILABLE_ICONS must produce a non-null pixmap of the requested size."""
    pixmap = get_icon_pixmap(name, ACCENT_BLUE, 22)
    assert not pixmap.isNull(), f"icon {name!r} produced a null pixmap"
    assert pixmap.size().width() == 22
    assert pixmap.size().height() == 22


def test_get_icon_returns_qicon(qapp) -> None:  # noqa: ARG001
    """The QIcon factory wraps the pixmap so widgets can use it directly."""
    icon = get_icon("layout-dashboard", TEXT_MUTED, 22)
    assert not icon.isNull()


def test_unknown_icon_raises(qapp) -> None:  # noqa: ARG001
    """Asking for an icon name we do not ship raises the typed error."""
    with pytest.raises(IconNotFoundError):
        get_icon_pixmap("not-a-real-icon", ACCENT_BLUE)


def test_invalid_color_raises(qapp) -> None:  # noqa: ARG001
    """A bogus color string is rejected before any rendering happens."""
    with pytest.raises(ValueError):
        get_icon_pixmap("cpu", "not a color")


def test_recolor_produces_different_pixmap(qapp) -> None:  # noqa: ARG001
    """Changing the requested color must yield a visibly different pixmap.

    We compare the raw image buffers — equal images would be a regression that
    means the ``currentColor`` substitution is not happening.
    """
    blue = get_icon_pixmap("cpu", "#7dcfff", 22).toImage()
    red = get_icon_pixmap("cpu", "#f7768e", 22).toImage()
    assert blue != red, "expected different pixel data when recoloring"
