"""ContainerList widget tests — placeholder rendering, override, status colors."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

from healthsh.domain.container import ContainerInfo
from healthsh.ui.widgets.container_list import PLACEHOLDER_CONTAINERS, ContainerList


def test_default_render_uses_placeholder_data(qtbot) -> None:
    cl = ContainerList()
    qtbot.addWidget(cl)
    labels = [c.text() for c in cl.findChildren(QLabel)]
    for container, _ in PLACEHOLDER_CONTAINERS:
        assert any(container.name in text for text in labels), (
            f"expected placeholder container {container.name!r} in the rendered labels"
        )


def test_set_containers_replaces_rows(qtbot) -> None:
    cl = ContainerList()
    qtbot.addWidget(cl)
    cl.set_containers(
        [(ContainerInfo(id="x", name="only-container", status="running"), 256 * 1024**2)]
    )
    labels = [c.text() for c in cl.findChildren(QLabel)]
    assert any("only-container" in text for text in labels)
    assert not any("postgres-dev" in text for text in labels)


def test_high_memory_row_uses_amber_role(qtbot) -> None:
    cl = ContainerList()
    qtbot.addWidget(cl)
    cl.set_containers([(ContainerInfo(id="hi", name="hungry", status="running"), 3 * 1024**3)])
    amber_labels = [c for c in cl.findChildren(QLabel) if c.property("role") == "amber"]
    assert amber_labels, "expected an amber-roled label for a >= 1 GiB container"


def test_stopped_container_renders_dash(qtbot) -> None:
    cl = ContainerList()
    qtbot.addWidget(cl)
    cl.set_containers([(ContainerInfo(id="off", name="grafana", status="stopped"), 0)])
    labels = [c.text() for c in cl.findChildren(QLabel)]
    # Memory column for a stopped container is rendered as an em-dash.
    assert any(text == "—" for text in labels)
