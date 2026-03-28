"""Tests for mutable state detector — UPPER_CASE mutable containers.

Phase 2C: UPPER_CASE names initialized to mutable containers ([], {}, set())
are now included as mutable state. Only UPPER_CASE with Optional annotation
and no mutable initializer are exempt.
"""

from __future__ import annotations

import ast

from desloppify.languages.python.detectors.mutable_state_ast import (
    _collect_module_level_mutables,
)


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


class TestUpperCaseMutableContainersIncluded:
    """The key behavioral change: UPPER_CASE mutable containers are flagged."""

    def test_upper_case_list_literal(self):
        assert "ITEMS" in _collect_module_level_mutables(_parse("ITEMS = []\n"))

    def test_upper_case_dict_literal(self):
        assert "REGISTRY" in _collect_module_level_mutables(_parse("REGISTRY = {}\n"))

    def test_upper_case_set_constructor(self):
        assert "SEEN" in _collect_module_level_mutables(_parse("SEEN = set()\n"))

    def test_upper_case_list_constructor(self):
        assert "BUFFER" in _collect_module_level_mutables(_parse("BUFFER = list()\n"))

    def test_upper_case_immutable_still_excluded(self):
        """Truly constant values don't pass _is_mutable_init — unchanged."""
        mutables = _collect_module_level_mutables(
            _parse('MAX_SIZE = 100\nNAME = "hello"\nITEMS = (1, 2, 3)\n')
        )
        assert not mutables


class TestAnnotatedAssignments:
    """Annotated assignments: mutable init always included, Optional nuance."""

    def test_mutable_init_included_regardless_of_case(self):
        assert "HANDLERS" in _collect_module_level_mutables(
            _parse("HANDLERS: list[str] = []\n")
        )

    def test_no_init_excluded(self):
        assert "HANDLERS" not in _collect_module_level_mutables(
            _parse("HANDLERS: list[str]\n")
        )

    def test_optional_none_upper_case_is_treated_as_constant_sentinel(self):
        """UPPER_CASE Optional[dict] = None is exempt (constant-style sentinel)."""
        mutables = _collect_module_level_mutables(
            _parse("from typing import Optional\nCACHE: Optional[dict] = None\n")
        )
        assert "CACHE" not in mutables

    def test_optional_lower_case_included(self):
        mutables = _collect_module_level_mutables(
            _parse("_cache: Optional[dict] = None\n")
        )
        assert "_cache" in mutables

    def test_union_none_syntax(self):
        """Python 3.10+ X | None syntax."""
        mutables = _collect_module_level_mutables(
            _parse("_state: dict | None = None\n")
        )
        assert "_state" in mutables
