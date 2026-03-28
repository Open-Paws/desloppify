"""Direct coverage tests for holistic context accessor helpers."""

from __future__ import annotations

from desloppify.intelligence.review.context_holistic.clusters.accessors import (
    _get_detail,
    _get_signals,
    _safe_num,
)


def test_get_detail_handles_missing_and_non_dict_detail() -> None:
    assert _get_detail({"detail": {"x": 1}}, "x") == 1
    assert _get_detail({"detail": {"x": 1}}, "y", default=5) == 5
    assert _get_detail({"detail": "bad"}, "x", default=3) == 3


def test_get_signals_prefers_signals_dict_and_falls_back_to_detail() -> None:
    issue = {"detail": {"signals": {"a": 1}, "b": 2}}
    assert _get_signals(issue) == {"a": 1}

    issue_no_signals = {"detail": {"b": 2}}
    assert _get_signals(issue_no_signals) == {"b": 2}

    assert _get_signals({"detail": "bad"}) == {}


def test_safe_num_accepts_numeric_but_rejects_bool_and_other_types() -> None:
    assert _safe_num(3) == 3.0
    assert _safe_num(2.5) == 2.5
    assert _safe_num(True, default=9.0) == 9.0
    assert _safe_num("3", default=1.5) == 1.5
