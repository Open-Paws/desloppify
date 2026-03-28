"""Tests for internal numeric coercion helpers."""

from __future__ import annotations

from desloppify.base.coercions import (
    coerce_non_negative_float,
    coerce_non_negative_int,
    coerce_positive_float,
    coerce_positive_int,
)


def test_coerce_positive_int() -> None:
    assert coerce_positive_int("7", default=3) == 7
    assert coerce_positive_int(-1, default=3) == 3
    assert coerce_positive_int(None, default=3) == 3
    assert coerce_positive_int("bad", default=3) == 3


def test_coerce_positive_float() -> None:
    assert coerce_positive_float("2.5", default=1.0) == 2.5
    assert coerce_positive_float(0.05, default=1.0) == 1.0
    assert coerce_positive_float({}, default=1.0) == 1.0


def test_coerce_non_negative_float() -> None:
    assert coerce_non_negative_float("0.0", default=1.0) == 0.0
    assert coerce_non_negative_float(-0.1, default=1.0) == 1.0
    assert coerce_non_negative_float("bad", default=1.0) == 1.0


def test_coerce_non_negative_int() -> None:
    assert coerce_non_negative_int("0", default=2) == 0
    assert coerce_non_negative_int(5.9, default=2) == 5
    assert coerce_non_negative_int(-1, default=2) == 2
    assert coerce_non_negative_int([], default=2) == 2

