"""Application chrome: header + sidebar + stacked content area.

:class:`MainWindow` wires the rail (:mod:`healthsh.ui.sidebar`) to a
:class:`QStackedWidget` containing the six top-level screens and updates the
header chrome (title, icon, subtitle) on every route change. The header
reserves a 200 px right-side slot for the ``live · 1s`` indicator that ships
with the Dashboard screen in issue #10.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from healthsh.services.collector_service import CollectorService
from healthsh.ui.icons import get_icon_pixmap
from healthsh.ui.screens.ai_screen import AIScreen
from healthsh.ui.screens.dashboard_screen import DashboardScreen
from healthsh.ui.screens.docker_screen import DockerScreen
from healthsh.ui.screens.logs_screen import LogsScreen
from healthsh.ui.screens.settings_screen import SettingsScreen
from healthsh.ui.screens.system_screen import SystemScreen
from healthsh.ui.sidebar import Sidebar
from healthsh.ui.theme.palette import (
    ACCENT_AMBER,
    ACCENT_GREEN,
    ACCENT_RED,
    TEXT_PRIMARY,
)

# Window sizing (px).
MIN_WIDTH: int = 1100
MIN_HEIGHT: int = 680
HEADER_HEIGHT: int = 44

# Right-side slot reserved for the Dashboard's "live · 1s" indicator (#10).
RIGHT_SLOT_WIDTH: int = 200

# Decorative traffic-light circle diameter (px).
TRAFFIC_LIGHT_DIAMETER: int = 11

# Header icon size (px).
HEADER_ICON_SIZE: int = 18


@dataclass(frozen=True)
class _ScreenSpec:
    """Static metadata for one top-level screen."""

    key: str
    title: str
    icon: str
    default_subtitle: str


# Default chrome strings per screen. Each screen may override its own subtitle
# at runtime; this is just the "first paint" content.
SCREEN_SPECS: tuple[_ScreenSpec, ...] = (
    _ScreenSpec("dashboard", "Dashboard", "layout-dashboard", "system health"),
    _ScreenSpec("system", "System", "cpu", "processes and sensors"),
    _ScreenSpec("docker", "Docker", "brand-docker", "containers"),
    _ScreenSpec("logs", "Logs", "file-text", "journald"),
    _ScreenSpec("ai", "AI", "sparkles", "assistant"),
    _ScreenSpec("settings", "Settings", "settings", "configuration"),
)


def _make_traffic_light(color_hex: str) -> QFrame:
    """Build a decorative circle in ``color_hex`` of :data:`TRAFFIC_LIGHT_DIAMETER`."""
    dot = QFrame()
    dot.setFixedSize(TRAFFIC_LIGHT_DIAMETER, TRAFFIC_LIGHT_DIAMETER)
    dot.setStyleSheet(
        f"background-color: {color_hex}; border-radius: {TRAFFIC_LIGHT_DIAMETER // 2}px;"
    )
    return dot


class Header(QFrame):
    """Top chrome strip: traffic lights, section icon + title, subtitle, right slot."""

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "header")
        self.setFixedHeight(HEADER_HEIGHT)
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)

        # Traffic lights (decorative).
        for color in (ACCENT_RED, ACCENT_AMBER, ACCENT_GREEN):
            layout.addWidget(_make_traffic_light(color), alignment=Qt.AlignmentFlag.AlignVCenter)

        # Small gap after the lights.
        layout.addSpacing(8)

        # Section icon.
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(HEADER_ICON_SIZE, HEADER_ICON_SIZE)
        layout.addWidget(self._icon_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Title (sentence case, 500 weight).
        self._title_label = QLabel()
        self._title_label.setProperty("role", "section-title")
        layout.addWidget(self._title_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Subtitle (muted).
        layout.addSpacing(8)
        self._subtitle_label = QLabel()
        self._subtitle_label.setProperty("role", "muted")
        layout.addWidget(self._subtitle_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Stretch to push the right slot to the edge.
        layout.addStretch(1)

        # Right-side reserved slot (Dashboard #10 fills it with "live · 1s").
        self._right_slot = QWidget()
        self._right_slot.setObjectName("header-right-slot")
        self._right_slot.setFixedWidth(RIGHT_SLOT_WIDTH)
        slot_layout = QHBoxLayout(self._right_slot)
        slot_layout.setContentsMargins(0, 0, 0, 0)
        slot_layout.setSpacing(6)
        slot_layout.addStretch(1)
        layout.addWidget(self._right_slot, alignment=Qt.AlignmentFlag.AlignVCenter)

    def set_section(self, title: str, icon_name: str) -> None:
        """Update the section icon + title."""
        self._title_label.setText(title)
        pixmap = get_icon_pixmap(icon_name, TEXT_PRIMARY, HEADER_ICON_SIZE)
        self._icon_label.setPixmap(pixmap)
        self._icon_label.setFixedSize(HEADER_ICON_SIZE, HEADER_ICON_SIZE)

    def set_subtitle(self, text: str) -> None:
        """Update the muted subtitle text."""
        self._subtitle_label.setText(text)

    def right_slot(self) -> QWidget:
        """Return the right-side container for screen-specific chrome (Dashboard #10)."""
        return self._right_slot


class MainWindow(QMainWindow):
    """Top-level chrome window with sidebar + stacked content."""

    def __init__(self, *, collector_service: CollectorService | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Healthsh")
        self.setMinimumSize(QSize(MIN_WIDTH, MIN_HEIGHT))

        # Service is created if none is injected — tests pass a stub.
        self._collector_service: CollectorService = collector_service or CollectorService(
            parent=self
        )
        self._collector_service.metrics_ready.connect(self._on_metrics_ready)
        self._started: bool = False
        # Track the widget currently mounted in the header's right slot so we
        # can remove it cleanly when switching screens.
        self._mounted_right_widget: QWidget | None = None
        # Tray hookup happens after construction via attach_tray(); these
        # defaults let MainWindow run standalone in tests with no tray.
        self._tray: object | None = (
            None  # actually a HealthTray, kept opaque to dodge a circular import
        )
        self._minimize_to_tray: bool = True
        self._tray_toast_shown: bool = False
        self._real_quit_requested: bool = False

        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Left rail.
        self._sidebar = Sidebar(parent=central)
        outer.addWidget(self._sidebar)

        # Right column = header (top) + content stack (fills remainder).
        right_column = QWidget()
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._header = Header(parent=right_column)
        right_layout.addWidget(self._header)

        self._stack = QStackedWidget(parent=right_column)
        self._stack.setContentsMargins(16, 16, 16, 16)
        right_layout.addWidget(self._stack, stretch=1)

        outer.addWidget(right_column, stretch=1)
        self.setCentralWidget(central)

        # Build screen instances and register them in the stack in the order
        # defined by SCREEN_SPECS so indices line up with the spec.
        self._screens: dict[str, QWidget] = {
            "dashboard": DashboardScreen(),
            "system": SystemScreen(),
            "docker": DockerScreen(),
            "logs": LogsScreen(),
            "ai": AIScreen(),
            "settings": SettingsScreen(),
        }
        self._spec_by_key: dict[str, _ScreenSpec] = {s.key: s for s in SCREEN_SPECS}

        for spec in SCREEN_SPECS:
            self._stack.addWidget(self._screens[spec.key])

        # Wire navigation.
        self._sidebar.screen_requested.connect(self.set_screen)

        # Boot with Dashboard active.
        self.set_screen("dashboard")

    # ---------------------------------------------------------------- routing

    def set_screen(self, key: str) -> None:
        """Switch the visible screen + update the header chrome.

        Also reparents any screen-supplied widget into the header's reserved
        right slot (currently only the Dashboard's ``live · 1s`` indicator).
        """
        if key not in self._screens:
            raise KeyError(f"unknown screen key: {key!r}")
        widget = self._screens[key]
        self._stack.setCurrentWidget(widget)
        spec = self._spec_by_key[key]
        self._header.set_section(spec.title, spec.icon)
        subtitle = getattr(widget, "header_subtitle", lambda: spec.default_subtitle)()
        self._header.set_subtitle(subtitle)
        self._sidebar.set_active(key)
        self._mount_header_right(widget)

    def _mount_header_right(self, screen: QWidget) -> None:
        """Reparent the screen's optional right-slot widget into the header."""
        slot = self._header.right_slot()
        # Remove anything we previously mounted (without destroying the widget,
        # the screen still owns it).
        if self._mounted_right_widget is not None:
            slot.layout().removeWidget(self._mounted_right_widget)
            self._mounted_right_widget.setParent(None)
            self._mounted_right_widget = None
        getter = getattr(screen, "header_right_widget", None)
        if getter is None:
            return
        chrome = getter()
        if chrome is None:
            return
        slot.layout().addWidget(chrome)
        self._mounted_right_widget = chrome

    # --------------------------------------------------------- lifecycle

    def showEvent(self, event) -> None:  # noqa: D401 — Qt callback name
        """Start the collector service the first time the window becomes visible."""
        super().showEvent(event)
        if not self._started:
            self._collector_service.start()
            self._started = True

    def closeEvent(self, event) -> None:  # noqa: D401 — Qt callback name
        """Hide to tray (when available + enabled), else stop service and close."""
        # Hide-to-tray path: tray attached, tray available, setting enabled,
        # and we did not get here via an explicit Quit menu click.
        if (
            self._tray is not None
            and self._minimize_to_tray
            and not self._real_quit_requested
            and getattr(self._tray, "is_available", lambda: False)()
        ):
            event.ignore()
            self.hide()
            if not self._tray_toast_shown:
                self._tray.post_toast(  # type: ignore[union-attr]
                    "Healthsh", "Still running in the tray. Right-click the icon to quit."
                )
                self._tray_toast_shown = True
            return
        self._collector_service.stop()
        super().closeEvent(event)

    # ---------------------------------------------------------------- tray

    def attach_tray(self, tray) -> None:
        """Wire the application's :class:`HealthTray` to this window.

        Calling this enables the hide-to-tray behavior. The window restores
        on ``show_requested`` and quits cleanly on ``quit_requested``.
        """
        from PySide6.QtWidgets import QApplication

        self._tray = tray
        tray.show_requested.connect(self._restore_from_tray)
        tray.quit_requested.connect(self._on_quit_requested)
        # Make the tray icon visible.
        getattr(tray, "show", lambda: None)()

        def _quit() -> None:
            self._real_quit_requested = True
            self._collector_service.stop()
            app = QApplication.instance()
            if app is not None:
                app.quit()

        # Stash the bound quit callback so _on_quit_requested can call it.
        self._do_quit = _quit  # type: ignore[attr-defined]

    def set_minimize_to_tray(self, enabled: bool) -> None:
        """Toggle hide-to-tray behavior at runtime (Settings will use this)."""
        self._minimize_to_tray = bool(enabled)

    def _restore_from_tray(self) -> None:
        if self.isVisible():
            # Toggle: if already visible, the menu item acts as 'hide'.
            self.hide()
            return
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_quit_requested(self) -> None:
        # Defer to the bound quit callback installed by attach_tray.
        quit_callable = getattr(self, "_do_quit", None)
        if quit_callable is not None:
            quit_callable()

    def collector_service(self) -> CollectorService:
        """Expose the underlying CollectorService (used by tests)."""
        return self._collector_service

    def _on_metrics_ready(self, snapshot) -> None:
        """Route a snapshot to every screen that wants one."""
        for screen in self._screens.values():
            handler = getattr(screen, "on_snapshot", None)
            if handler is not None:
                handler(snapshot)

    # ---------------------------------------------------------------- access

    def header(self) -> Header:
        """Expose the header for screens that want to mount widgets in the right slot."""
        return self._header

    def sidebar(self) -> Sidebar:
        """Expose the sidebar (used by tests and integration code)."""
        return self._sidebar

    def stack(self) -> QStackedWidget:
        """Expose the content stack (used by tests and integration code)."""
        return self._stack

    def current_screen_key(self) -> str:
        """Return the key of the currently visible screen."""
        widget = self._stack.currentWidget()
        for key, w in self._screens.items():
            if w is widget:
                return key
        # Should be unreachable — stack only contains widgets we registered.
        raise RuntimeError("current widget is not a registered screen")
