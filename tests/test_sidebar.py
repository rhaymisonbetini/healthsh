"""Sidebar tests — navigation state, signal emission, footer pinning."""

from __future__ import annotations

import pytest

from healthsh.ui.sidebar import FOOTER_ITEM, PRIMARY_ITEMS, Sidebar


def test_default_active_is_dashboard(qtbot) -> None:
    """The rail boots with Dashboard selected."""
    sidebar = Sidebar()
    qtbot.addWidget(sidebar)
    assert sidebar.active_key() == "dashboard"


def test_click_emits_screen_requested(qtbot) -> None:
    """Clicking any nav button emits ``screen_requested(key)`` exactly once."""
    sidebar = Sidebar()
    qtbot.addWidget(sidebar)

    with qtbot.waitSignal(sidebar.screen_requested, timeout=1000) as blocker:
        sidebar._buttons["system"].click()
    assert blocker.args == ["system"]
    assert sidebar.active_key() == "system"


def test_set_active_unknown_key_raises(qtbot) -> None:
    """Passing an unknown key to :meth:`Sidebar.set_active` raises KeyError."""
    sidebar = Sidebar()
    qtbot.addWidget(sidebar)
    with pytest.raises(KeyError):
        sidebar.set_active("not-a-screen")


def test_repeated_set_active_is_idempotent(qtbot) -> None:
    """Calling :meth:`set_active` with the current key does not emit a signal."""
    sidebar = Sidebar()
    qtbot.addWidget(sidebar)

    emissions: list[str] = []
    sidebar.screen_requested.connect(emissions.append)

    sidebar.set_active("dashboard")  # already the active item
    assert emissions == []


def test_all_specified_items_are_built(qtbot) -> None:
    """Every PRIMARY_ITEMS entry and FOOTER_ITEM must produce a button."""
    sidebar = Sidebar()
    qtbot.addWidget(sidebar)
    for item in PRIMARY_ITEMS:
        assert item.key in sidebar._buttons, f"missing primary nav button: {item.key}"
    assert FOOTER_ITEM.key in sidebar._buttons


def test_settings_is_pinned_to_the_bottom(qtbot) -> None:
    """The Settings button is the last widget in the sidebar layout."""
    sidebar = Sidebar()
    qtbot.addWidget(sidebar)
    layout = sidebar.layout()
    last_widget = None
    # Walk every layout entry and grab the trailing widget (skipping spacers).
    for idx in range(layout.count()):
        widget = layout.itemAt(idx).widget()
        if widget is not None:
            last_widget = widget
    assert last_widget is sidebar._buttons[FOOTER_ITEM.key]
