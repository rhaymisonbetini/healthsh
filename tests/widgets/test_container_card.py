"""ContainerCard widget tests — running/stopped visuals + action signals."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMessageBox

from healthsh.domain.container import ContainerInfo, ContainerStats
from healthsh.ui.widgets.container_card import ContainerCard


def _running_info() -> ContainerInfo:
    return ContainerInfo(
        id="abc123",
        name="postgres-dev",
        image="postgres:16",
        status="running",
        ports=("5432:5432",),
        uptime_s=3600 * 26,
    )


def _stopped_info() -> ContainerInfo:
    return ContainerInfo(id="def456", name="grafana", image="grafana:11", status="exited")


def _stats(mem_b: int = 500 * 1024**2, cpu: float = 4.0) -> ContainerStats:
    return ContainerStats(cpu_pct=cpu, mem_used_b=mem_b, mem_limit_b=2 * 1024**3)


def test_running_card_shows_active_actions_and_stats(qtbot) -> None:
    card = ContainerCard(info=_running_info(), stats=_stats())
    qtbot.addWidget(card)
    assert card._btn_pause.isHidden() is False  # type: ignore[attr-defined]
    assert card._btn_restart.isHidden() is False  # type: ignore[attr-defined]
    assert card._btn_logs.isHidden() is False  # type: ignore[attr-defined]
    assert card._btn_play.isHidden() is True  # type: ignore[attr-defined]
    assert "CPU 4.0%" in card._cpu_label.text()  # type: ignore[attr-defined]
    assert "MEM" in card._mem_label.text()  # type: ignore[attr-defined]


def test_stopped_card_only_shows_play(qtbot) -> None:
    card = ContainerCard(info=_stopped_info(), stats=None)
    qtbot.addWidget(card)
    assert card._btn_pause.isHidden() is True  # type: ignore[attr-defined]
    assert card._btn_restart.isHidden() is True  # type: ignore[attr-defined]
    assert card._btn_logs.isHidden() is True  # type: ignore[attr-defined]
    assert card._btn_play.isHidden() is False  # type: ignore[attr-defined]
    assert card.property("role") == "card-inactive"


def test_pause_emits_action_without_confirmation(qtbot) -> None:
    card = ContainerCard(info=_running_info(), stats=_stats())
    qtbot.addWidget(card)
    received: list[tuple[str, str]] = []
    card.action_requested.connect(lambda i, a: received.append((i, a)))
    card._btn_pause.click()  # type: ignore[attr-defined]
    assert received == [("abc123", "pause")]


def test_play_emits_start_without_confirmation(qtbot) -> None:
    card = ContainerCard(info=_stopped_info(), stats=None)
    qtbot.addWidget(card)
    received: list[tuple[str, str]] = []
    card.action_requested.connect(lambda i, a: received.append((i, a)))
    card._btn_play.click()  # type: ignore[attr-defined]
    assert received == [("def456", "start")]


def test_restart_requires_confirmation(qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    """No-press path: clicking restart but declining the dialog emits nothing."""
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
    )
    card = ContainerCard(info=_running_info(), stats=_stats())
    qtbot.addWidget(card)
    received: list[tuple[str, str]] = []
    card.action_requested.connect(lambda i, a: received.append((i, a)))
    card._btn_restart.click()  # type: ignore[attr-defined]
    assert received == []


def test_restart_emits_when_confirmation_accepted(qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    card = ContainerCard(info=_running_info(), stats=_stats())
    qtbot.addWidget(card)
    received: list[tuple[str, str]] = []
    card.action_requested.connect(lambda i, a: received.append((i, a)))
    card._btn_restart.click()  # type: ignore[attr-defined]
    assert received == [("abc123", "restart")]


def test_emit_stop_with_confirmation_requires_yes(qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter([QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes])
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: next(answers)))
    card = ContainerCard(info=_running_info(), stats=_stats())
    qtbot.addWidget(card)
    received: list[tuple[str, str]] = []
    card.action_requested.connect(lambda i, a: received.append((i, a)))
    card.emit_stop_with_confirmation()  # declines
    card.emit_stop_with_confirmation()  # accepts
    assert received == [("abc123", "stop")]


def test_update_state_swaps_running_to_stopped(qtbot) -> None:
    card = ContainerCard(info=_running_info(), stats=_stats())
    qtbot.addWidget(card)
    card.update_state(_stopped_info(), None)
    assert card._btn_play.isHidden() is False  # type: ignore[attr-defined]
    assert card._btn_logs.isHidden() is True  # type: ignore[attr-defined]
    assert card.property("role") == "card-inactive"


def test_mem_amber_when_at_least_one_gib(qtbot) -> None:
    card = ContainerCard(
        info=_running_info(),
        stats=_stats(mem_b=int(1.2 * 1024**3)),
    )
    qtbot.addWidget(card)
    assert "e0af68" in card._mem_label.styleSheet().lower()  # type: ignore[attr-defined]


def test_mem_green_below_threshold(qtbot) -> None:
    card = ContainerCard(
        info=_running_info(),
        stats=_stats(mem_b=200 * 1024**2),
    )
    qtbot.addWidget(card)
    assert "9ece6a" in card._mem_label.styleSheet().lower()  # type: ignore[attr-defined]


def test_logs_button_calls_provider(qtbot) -> None:
    captured: list[str] = []

    def provider(container_id: str) -> list[str]:
        captured.append(container_id)
        return ["log line a", "log line b"]

    card = ContainerCard(info=_running_info(), stats=_stats())
    qtbot.addWidget(card)
    card.set_logs_provider(provider)
    # Stub QDialog.exec via monkey-patch on the instance so the modal does not block.
    from healthsh.ui.widgets import container_card as cc

    cc._LogsDialog.exec = lambda self: 0  # type: ignore[assignment]
    card._btn_logs.click()  # type: ignore[attr-defined]
    assert captured == ["abc123"]
