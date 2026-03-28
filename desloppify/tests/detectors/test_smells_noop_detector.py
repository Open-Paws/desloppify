"""Unit tests for noop-function smell detection filters."""

from __future__ import annotations

import ast
import textwrap

from desloppify.languages.python.detectors.smells_ast._tree_quality_detectors import (
    _detect_noop_function,
)


def _module(source: str) -> ast.Module:
    return ast.parse(textwrap.dedent(source))


def test_noop_detector_flags_regular_trivial_function() -> None:
    tree = _module(
        """
        def trivial():
            print("one")
            print("two")
            print("three")
        """
    )
    results = _detect_noop_function("desloppify/engine/example.py", tree)
    assert len(results) == 1
    assert "trivial()" in results[0]["content"]


def test_noop_detector_skips_cli_display_helpers() -> None:
    tree = _module(
        """
        def _print_header():
            print("one")
            print("two")
            print("three")
        """
    )
    results = _detect_noop_function(
        "desloppify/app/commands/status/render.py",
        tree,
    )
    assert results == []


def test_noop_detector_skips_cli_show_helpers() -> None:
    tree = _module(
        """
        def _show_visibility():
            print("one")
            print("two")
            print("three")
        """
    )
    results = _detect_noop_function(
        "desloppify/app/commands/scan/cmd.py",
        tree,
    )
    assert results == []


def test_noop_detector_keeps_non_display_functions_in_commands() -> None:
    tree = _module(
        """
        def trivial():
            print("one")
            print("two")
            print("three")
        """
    )
    results = _detect_noop_function(
        "desloppify/app/commands/status/render.py",
        tree,
    )
    assert len(results) == 1
