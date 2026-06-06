"""DockerScreen integration tests — mode swap, reconciliation, subtitles."""

from __future__ import annotations

from healthsh.domain.container import ContainerInfo, ContainerStats, DockerStatus
from healthsh.ui.screens.docker_screen import DockerScreen


def _running(name: str, cid: str = "") -> ContainerInfo:
    return ContainerInfo(id=cid or name, name=name, image=f"{name}:latest", status="running")


def _stopped(name: str, cid: str = "") -> ContainerInfo:
    return ContainerInfo(id=cid or name, name=name, image=f"{name}:latest", status="exited")


def _stats(mem_b: int = 100 * 1024**2) -> ContainerStats:
    return ContainerStats(cpu_pct=1.0, mem_used_b=mem_b)


def test_ok_status_shows_cards_view_and_subtitle(qtbot) -> None:
    screen = DockerScreen()
    qtbot.addWidget(screen)
    pairs = [(_running("redis"), _stats()), (_stopped("grafana"), None)]
    screen.on_docker(DockerStatus(kind="ok"), pairs)
    assert screen.stack().currentIndex() == 0
    assert screen.header_subtitle() == "1 running · 1 stopped"
    assert set(screen.cards().keys()) == {"redis", "grafana"}


def test_not_installed_swaps_to_empty_state(qtbot) -> None:
    screen = DockerScreen()
    qtbot.addWidget(screen)
    screen.on_docker(DockerStatus(kind="not_installed"), [])
    assert screen.stack().currentIndex() == 1
    assert screen.empty_state().current_kind() == "not_installed"
    assert screen.header_subtitle() == "not installed"


def test_daemon_down_subtitle_and_state(qtbot) -> None:
    screen = DockerScreen()
    qtbot.addWidget(screen)
    screen.on_docker(DockerStatus(kind="daemon_down"), [])
    assert screen.empty_state().current_kind() == "daemon_down"
    assert screen.header_subtitle() == "daemon stopped"


def test_permission_denied_subtitle_and_state(qtbot) -> None:
    screen = DockerScreen()
    qtbot.addWidget(screen)
    screen.on_docker(DockerStatus(kind="permission_denied"), [])
    assert screen.empty_state().current_kind() == "permission_denied"
    assert screen.header_subtitle() == "socket not accessible"


def test_unknown_subtitle_and_state(qtbot) -> None:
    screen = DockerScreen()
    qtbot.addWidget(screen)
    screen.on_docker(DockerStatus(kind="unknown", detail="bad happened"), [])
    assert screen.empty_state().current_kind() == "unknown"
    assert screen.header_subtitle() == "unavailable"


def test_reconciliation_adds_updates_and_removes_cards(qtbot) -> None:
    screen = DockerScreen()
    qtbot.addWidget(screen)
    # Initial snapshot.
    screen.on_docker(
        DockerStatus(kind="ok"),
        [(_running("redis"), _stats(100 * 1024**2)), (_running("postgres-dev"), _stats())],
    )
    assert set(screen.cards().keys()) == {"redis", "postgres-dev"}
    cards_first = screen.cards()
    # New snapshot: postgres-dev gone, grafana arrived. redis updates.
    screen.on_docker(
        DockerStatus(kind="ok"),
        [(_running("redis"), _stats(200 * 1024**2)), (_stopped("grafana"), None)],
    )
    cards_second = screen.cards()
    assert set(cards_second.keys()) == {"redis", "grafana"}
    # redis card is reused (not recreated) so identity persists.
    assert cards_second["redis"] is cards_first["redis"]


def test_running_first_ordering(qtbot) -> None:
    screen = DockerScreen()
    qtbot.addWidget(screen)
    screen.on_docker(
        DockerStatus(kind="ok"),
        [
            (_stopped("alpine"), None),
            (_running("redis"), _stats()),
            (_stopped("grafana"), None),
            (_running("postgres-dev"), _stats()),
        ],
    )
    layout = screen._cards_layout  # type: ignore[attr-defined]
    names_in_order: list[str] = []
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if w is None:
            continue
        from healthsh.ui.widgets.container_card import ContainerCard as _CC

        if isinstance(w, _CC):
            names_in_order.append(w.info().name)
    assert names_in_order == ["postgres-dev", "redis", "alpine", "grafana"]


def test_empty_list_hint_visible_only_when_ok_and_empty(qtbot) -> None:
    screen = DockerScreen()
    qtbot.addWidget(screen)
    screen.on_docker(DockerStatus(kind="ok"), [])
    assert screen._empty_list_label.isHidden() is False  # type: ignore[attr-defined]
    screen.on_docker(DockerStatus(kind="ok"), [(_running("redis"), _stats())])
    assert screen._empty_list_label.isHidden() is True  # type: ignore[attr-defined]


def test_ai_banner_hidden_in_empty_state(qtbot) -> None:
    screen = DockerScreen()
    qtbot.addWidget(screen)
    screen.on_docker(DockerStatus(kind="not_installed"), [])
    assert screen._ai_banner.isHidden() is True  # type: ignore[attr-defined]
    screen.on_docker(DockerStatus(kind="ok"), [])
    assert screen._ai_banner.isHidden() is False  # type: ignore[attr-defined]


def test_status_records_last_emission(qtbot) -> None:
    screen = DockerScreen()
    qtbot.addWidget(screen)
    screen.on_docker(DockerStatus(kind="ok"), [])
    assert screen.status() is not None
    assert screen.status().is_ok  # type: ignore[union-attr]


def test_unknown_detail_threads_through_to_body(qtbot) -> None:
    screen = DockerScreen()
    qtbot.addWidget(screen)
    screen.on_docker(DockerStatus(kind="unknown", detail="upstream broke"), [])
    body = screen._empty_state._body_label.text()  # type: ignore[attr-defined]
    assert "upstream broke" in body
