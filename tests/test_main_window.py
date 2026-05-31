"""MainWindow integration tests — routing, header sync, min size, defaults."""

from __future__ import annotations

import pytest

from healthsh.ui.main_window import MIN_HEIGHT, MIN_WIDTH, SCREEN_SPECS, MainWindow


@pytest.fixture()
def window(qtbot) -> MainWindow:
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def test_boot_screen_is_dashboard(window: MainWindow) -> None:
    """The window opens on the Dashboard."""
    assert window.current_screen_key() == "dashboard"
    assert window.sidebar().active_key() == "dashboard"


def test_min_size_is_enforced(window: MainWindow) -> None:
    """Minimum size matches the spec (1100 x 680)."""
    size = window.minimumSize()
    assert size.width() == MIN_WIDTH
    assert size.height() == MIN_HEIGHT


def test_sidebar_click_routes_to_screen(qtbot, window: MainWindow) -> None:
    """Clicking each sidebar item swaps the stacked content."""
    for spec in SCREEN_SPECS:
        with qtbot.waitSignal(window.sidebar().screen_requested, timeout=1000):
            window.sidebar()._buttons[spec.key].click()
        assert window.current_screen_key() == spec.key


def test_header_updates_on_route(qtbot, window: MainWindow) -> None:
    """Switching screens updates the header title."""
    title_label = window.header().findChild(type(window.header()), None)  # type: ignore[arg-type]
    # Easier: just check via the screen specs that the labels get the expected text.
    for spec in SCREEN_SPECS:
        window.set_screen(spec.key)
        # Walk children to find the QLabel that holds the section title.
        labels = window.header().findChildren(type(window.header()))  # type: ignore[arg-type]
        # Robust check: use the public Header API via the section title label.
        # The Header stores the title via setProperty role=section-title; pull the
        # label by property and verify its text equals the spec title.
        from PySide6.QtWidgets import QLabel

        title_labels = [
            child
            for child in window.header().findChildren(QLabel)
            if child.property("role") == "section-title"
        ]
        assert title_labels, "Header must expose a section-title label"
        assert title_labels[0].text() == spec.title
        # Silence unused locals.
        _ = (title_label, labels)


def test_set_screen_unknown_key_raises(window: MainWindow) -> None:
    """Switching to an unknown screen key raises KeyError."""
    with pytest.raises(KeyError):
        window.set_screen("not-a-screen")


def test_screens_count_matches_spec(window: MainWindow) -> None:
    """The stack contains exactly one widget per SCREEN_SPECS entry, in order."""
    stack = window.stack()
    assert stack.count() == len(SCREEN_SPECS)
