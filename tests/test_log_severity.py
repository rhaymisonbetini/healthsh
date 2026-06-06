"""log_severity tests — pure mapping, no Qt needed."""

from __future__ import annotations

from healthsh.core.log_severity import CATEGORIES, priority_to_category


def test_category_ordering_is_stable() -> None:
    assert CATEGORIES == ("err", "warn", "info", "debug")


def test_priority_zero_through_three_is_err() -> None:
    for p in (0, 1, 2, 3):
        assert priority_to_category(p) == "err"


def test_priority_four_is_warn() -> None:
    assert priority_to_category(4) == "warn"


def test_priority_five_and_six_are_info() -> None:
    assert priority_to_category(5) == "info"
    assert priority_to_category(6) == "info"


def test_priority_seven_is_debug() -> None:
    assert priority_to_category(7) == "debug"


def test_out_of_range_defaults_to_debug() -> None:
    assert priority_to_category(99) == "debug"
    assert priority_to_category(-1) == "err"  # negative → covered by ≤ 3 branch
