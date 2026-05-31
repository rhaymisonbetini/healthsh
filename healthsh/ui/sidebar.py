"""Left-rail navigation: six icon buttons that route to top-level screens.

The sidebar is a ~48 px wide column with five primary nav items stacked at the
top and ``settings`` pinned to the bottom. The active item paints in
:data:`healthsh.ui.theme.palette.ACCENT_BLUE`; inactives use
:data:`TEXT_MUTED`. Clicking any item emits :pyattr:`Sidebar.screen_requested`
with the canonical screen name so :class:`healthsh.ui.main_window.MainWindow`
can swap the content :class:`QStackedWidget`.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
)

from healthsh.ui.icons import get_icon
from healthsh.ui.theme.palette import ACCENT_BLUE, TEXT_MUTED

# Width of the rail (px). Matches HEALTHSH_ROADMAP §4.4.
SIDEBAR_WIDTH: int = 48

# Render size of each icon glyph (px). The button itself is taller to give a
# comfortable click target.
ICON_SIZE: int = 22

# Vertical gap between icon buttons inside the primary stack.
ITEM_SPACING: int = 18


@dataclass(frozen=True)
class _NavItem:
    """Static description of one sidebar entry."""

    key: str
    label: str
    icon: str


# Top-stack items (rendered in this order, with ``ITEM_SPACING`` between them).
PRIMARY_ITEMS: tuple[_NavItem, ...] = (
    _NavItem("dashboard", "Dashboard", "layout-dashboard"),
    _NavItem("system", "System", "cpu"),
    _NavItem("docker", "Docker", "brand-docker"),
    _NavItem("logs", "Logs", "file-text"),
    _NavItem("ai", "AI", "sparkles"),
)

# Bottom-pinned item.
FOOTER_ITEM: _NavItem = _NavItem("settings", "Settings", "settings")


class Sidebar(QFrame):
    """Vertical icon-only navigation rail."""

    screen_requested = Signal(str)

    def __init__(self, *, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setProperty("role", "sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._buttons: dict[str, QPushButton] = {}
        self._active_key: str | None = None
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(ITEM_SPACING)

        for item in PRIMARY_ITEMS:
            layout.addWidget(self._build_button(item), alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

        layout.addWidget(self._build_button(FOOTER_ITEM), alignment=Qt.AlignmentFlag.AlignHCenter)

        # Default active item.
        self.set_active("dashboard")

    # ------------------------------------------------------------------ build

    def _build_button(self, item: _NavItem) -> QPushButton:
        btn = QPushButton(parent=self)
        btn.setObjectName(f"nav-{item.key}")
        btn.setProperty("role", "ghost")
        btn.setProperty("nav_key", item.key)
        btn.setProperty("icon_name", item.icon)
        btn.setCheckable(True)
        btn.setAutoExclusive(False)  # we manage exclusivity via QButtonGroup
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(item.label)
        btn.setFixedSize(32, 32)
        btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        btn.setIcon(get_icon(item.icon, TEXT_MUTED, ICON_SIZE))
        btn.clicked.connect(lambda _checked, k=item.key: self._on_click(k))
        self._buttons[item.key] = btn
        self._group.addButton(btn)
        return btn

    # ----------------------------------------------------------------- state

    def set_active(self, key: str) -> None:
        """Mark ``key`` as the active item and recolor icons accordingly.

        Idempotent — calling it with the current active key is a no-op.
        Raises :class:`KeyError` if ``key`` is unknown.
        """
        if key not in self._buttons:
            raise KeyError(f"unknown nav key: {key!r}")
        if key == self._active_key:
            return
        self._active_key = key
        for k, btn in self._buttons.items():
            icon_name = str(btn.property("icon_name"))
            color = ACCENT_BLUE if k == key else TEXT_MUTED
            btn.setIcon(get_icon(icon_name, color, ICON_SIZE))
            btn.setChecked(k == key)

    def active_key(self) -> str | None:
        """Return the currently-active nav key (``None`` only before init completes)."""
        return self._active_key

    # ---------------------------------------------------------------- signals

    def _on_click(self, key: str) -> None:
        self.set_active(key)
        self.screen_requested.emit(key)
