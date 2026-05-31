"""Icon registry and color-aware loader for the healthsh UI.

Icons live in :mod:`healthsh.assets.icons` as SVG files using ``currentColor``
as a placeholder stroke. :func:`get_icon` substitutes the requested color into
the SVG source and rasterizes it through :class:`PySide6.QtSvg.QSvgRenderer`,
returning a sharp :class:`PySide6.QtGui.QIcon` of the requested size.

All Tabler outline icons bundled here are MIT licensed (https://tabler.io/icons).
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# Canonical icon names — kept in lockstep with the SVG files under
# ``healthsh/assets/icons/``. Update this set when adding an asset so the
# accidental-name guard in :func:`get_icon` and tests stay honest.
AVAILABLE_ICONS: frozenset[str] = frozenset(
    {
        "layout-dashboard",
        "cpu",
        "brand-docker",
        "file-text",
        "sparkles",
        "settings",
        "activity-heartbeat",
        "flame",
    }
)

_PACKAGE = "healthsh.assets.icons"


class IconNotFoundError(KeyError):
    """Raised when :func:`get_icon` is called with an unknown icon name."""


@lru_cache(maxsize=64)
def _load_svg_text(name: str) -> str:
    """Return the raw SVG source for ``name`` (cached)."""
    if name not in AVAILABLE_ICONS:
        raise IconNotFoundError(f"unknown icon {name!r}; available: {sorted(AVAILABLE_ICONS)}")
    resource = resources.files(_PACKAGE) / f"{name}.svg"
    return resource.read_text(encoding="utf-8")


def _normalize_color(color: str) -> str:
    """Return ``color`` as a ``#rrggbb`` hex string, raising on invalid input."""
    qc = QColor(color)
    if not qc.isValid():
        raise ValueError(f"invalid color string: {color!r}")
    return qc.name()  # always lowercase #rrggbb


@lru_cache(maxsize=256)
def get_icon_pixmap(name: str, color: str, size: int = 22) -> QPixmap:
    """Render ``name`` as a transparent-background QPixmap of ``size`` x ``size``.

    Args:
        name: One of :data:`AVAILABLE_ICONS`.
        color: Any string ``QColor`` accepts (``#rrggbb`` recommended).
        size: Output pixmap edge length in device-independent pixels.

    Returns:
        A square QPixmap ready to set on a button or label.
    """
    hex_color = _normalize_color(color)
    svg_text = _load_svg_text(name).replace("currentColor", hex_color)

    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    return pixmap


def get_icon(name: str, color: str, size: int = 22) -> QIcon:
    """Return a QIcon for ``name`` colored with ``color``.

    Thin wrapper around :func:`get_icon_pixmap`. Suitable for QPushButton,
    QSystemTrayIcon, QListWidgetItem, etc.
    """
    return QIcon(get_icon_pixmap(name, color, size))
