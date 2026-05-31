"""ProcessList widget tests — replace rows, format memory, elide long names."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

from healthsh.domain.process import ProcessInfo
from healthsh.ui.widgets.process_list import ProcessList


def _processes() -> list[ProcessInfo]:
    return [
        ProcessInfo(pid=1, name="postgres-dev", user="postgres", cpu_pct=4.0, mem_b=4 * 1024**3),
        ProcessInfo(pid=2, name="chrome", user="me", cpu_pct=12.0, mem_b=800 * 1024**2),
        ProcessInfo(pid=3, name="python", user="me", cpu_pct=0.5, mem_b=50 * 1024**2),
    ]


def test_set_processes_renders_rows(qtbot) -> None:
    pl = ProcessList()
    qtbot.addWidget(pl)
    pl.set_processes(_processes())
    labels = [c.text() for c in pl.findChildren(QLabel)]
    # Title + 3 process rows × (name + memory) → expect the names + memory strings.
    assert any("postgres-dev" in text for text in labels)
    assert any("chrome" in text for text in labels)
    assert any("python" in text for text in labels)
    assert any("GiB" in text for text in labels), "expected GiB-formatted memory for big proc"
    assert any("MB" in text for text in labels), "expected MB-formatted memory for small procs"


def test_set_processes_replaces_previous_rows(qtbot) -> None:
    pl = ProcessList()
    qtbot.addWidget(pl)
    pl.set_processes(_processes())
    pl.set_processes(
        [ProcessInfo(pid=99, name="single", user="me", cpu_pct=0.0, mem_b=100 * 1024**2)]
    )
    labels = [c.text() for c in pl.findChildren(QLabel)]
    assert any("single" in text for text in labels)
    assert not any("postgres-dev" in text for text in labels)


def test_long_name_is_elided(qtbot) -> None:
    pl = ProcessList()
    qtbot.addWidget(pl)
    pl.set_processes(
        [
            ProcessInfo(
                pid=1,
                name="very-very-very-long-process-name-that-should-be-truncated",
                user="me",
                cpu_pct=0.0,
                mem_b=1024,
            )
        ]
    )
    labels = [c.text() for c in pl.findChildren(QLabel)]
    matches = [text for text in labels if text.startswith("very-very")]
    assert matches, "expected the long-named row to render"
    # Elision inserts the ellipsis character ('…') somewhere.
    assert any("…" in text for text in matches), "expected the long row to be elided"
