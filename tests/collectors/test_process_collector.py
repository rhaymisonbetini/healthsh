"""Process collector smoke tests."""

from __future__ import annotations

import pytest

from healthsh.domain.process import ProcessInfo
from healthsh.infra.collectors.process_collector import list_all, top_n_by_memory


def test_top_n_returns_at_most_n() -> None:
    result = top_n_by_memory(3)
    assert isinstance(result, list)
    assert len(result) <= 3
    assert all(isinstance(p, ProcessInfo) for p in result)


def test_top_n_sorted_desc_by_memory() -> None:
    result = top_n_by_memory(10)
    if len(result) < 2:
        pytest.skip("not enough processes to compare")
    for prev, nxt in zip(result, result[1:], strict=False):
        assert prev.mem_b >= nxt.mem_b


def test_top_n_rejects_non_positive() -> None:
    with pytest.raises(ValueError):
        top_n_by_memory(0)
    with pytest.raises(ValueError):
        top_n_by_memory(-1)


def test_list_all_includes_current_python_process() -> None:
    """Our own pytest process must appear in the unsorted listing."""
    import os

    pids = {p.pid for p in list_all()}
    assert os.getpid() in pids
