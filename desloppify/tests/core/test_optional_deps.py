"""Tests for optional dependency availability helpers."""

from __future__ import annotations

from desloppify.base.optional_deps import has_module


def test_has_module_handles_blank_name() -> None:
    assert has_module("") is False


def test_has_module_detects_stdlib_module() -> None:
    assert has_module("json") is True

