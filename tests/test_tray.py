"""Tray + MainWindow integration tests for hide-to-tray behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from healthsh.ui.main_window import MainWindow
from healthsh.ui.tray import HealthTray


class _FakeTray:
    """Pure-Python stand-in for HealthTray used by close-event tests.

    Avoids the real QSystemTrayIcon which is unavailable on the offscreen
    Qt platform used in CI.
    """

    # Use real Qt signals so connect()/emit() works as expected.
    show_requested = Signal()
    quit_requested = Signal()

    def __init__(self, available: bool) -> None:
        self._available = available
        self.toast_calls: list[tuple[str, str]] = []
        self.show_calls = 0

    def is_available(self) -> bool:
        return self._available

    def show(self) -> None:
        self.show_calls += 1

    def post_toast(self, title: str, message: str) -> None:
        self.toast_calls.append((title, message))


def test_tray_construction(qtbot) -> None:
    """The tray can be built without raising even if the platform lacks a tray."""
    tray = HealthTray()
    # is_available may be True or False — both are acceptable. We just need
    # construction to succeed and the menu actions to be present.
    actions = [a.text() for a in tray._menu.actions() if a.text()]
    assert "Show / hide window" in actions
    assert "Quit" in actions


def test_close_without_tray_closes_window(qtbot) -> None:
    """A MainWindow without an attached tray closes normally on closeEvent."""
    window = MainWindow()
    qtbot.addWidget(window)
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()


def test_close_with_unavailable_tray_still_closes(qtbot) -> None:
    """An attached tray that reports as unavailable does not trap the close."""
    window = MainWindow()
    qtbot.addWidget(window)
    fake = MagicMock()
    fake.is_available.return_value = False
    fake.show_requested = MagicMock()
    fake.quit_requested = MagicMock()
    window._tray = fake  # bypass attach_tray for this isolated test
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()


def test_close_hides_to_available_tray(qtbot) -> None:
    """With an available tray and the setting on, closeEvent is ignored and window hides."""
    window = MainWindow()
    qtbot.addWidget(window)
    # Do NOT call window.show() — that would fire showEvent and start the
    # real metrics worker, which would still be running when the test ends.
    fake = MagicMock()
    fake.is_available.return_value = True
    fake.show_requested = MagicMock()
    fake.quit_requested = MagicMock()
    window._tray = fake
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert fake.post_toast.call_count == 1
    # Second close: toast must NOT fire again.
    event2 = QCloseEvent()
    window.closeEvent(event2)
    assert fake.post_toast.call_count == 1


def test_set_minimize_to_tray_disables_hide(qtbot) -> None:
    """Toggling minimize_to_tray off lets the window close even with a tray attached."""
    window = MainWindow()
    qtbot.addWidget(window)
    fake = MagicMock()
    fake.is_available.return_value = True
    window._tray = fake
    window.set_minimize_to_tray(False)
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()


def test_attach_tray_wires_quit_path(qtbot) -> None:
    """attach_tray installs a quit callback that ends the app cleanly."""
    window = MainWindow()
    qtbot.addWidget(window)
    fake_tray = MagicMock()
    fake_tray.is_available.return_value = True
    fake_tray.show_requested = MagicMock()
    fake_tray.quit_requested = MagicMock()
    fake_tray.show = MagicMock()
    window.attach_tray(fake_tray)
    # show_requested connection registered.
    fake_tray.show_requested.connect.assert_called()
    fake_tray.quit_requested.connect.assert_called()
    # show() was invoked to make the icon visible.
    fake_tray.show.assert_called_once()
    # Manually invoke the bound quit handler to make sure it does not crash.
    app = QApplication.instance()
    assert app is not None
    window._on_quit_requested()  # marks _real_quit_requested True; calls app.quit()
    assert window._real_quit_requested
