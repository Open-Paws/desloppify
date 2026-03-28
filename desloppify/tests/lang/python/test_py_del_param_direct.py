"""Tests for _detect_del_param smell detector.

Phase 5B: Flag functions that `del` a parameter in the first 3 body statements.
"""

from __future__ import annotations

import ast

from desloppify.languages.python.detectors.smells_ast._tree_quality_detectors import (
    _detect_del_param,
)


def _detect(src: str) -> list[dict]:
    return _detect_del_param("file.py", ast.parse(src))


class TestDetectDelParam:

    def test_del_param_in_first_stmt(self):
        results = _detect(
            "def process(data, unused):\n"
            "    del unused\n"
            "    return data\n"
        )
        assert len(results) == 1
        assert "unused" in results[0]["content"]

    def test_del_param_at_boundary_third_stmt(self):
        results = _detect(
            "def process(data, unused):\n"
            "    x = 1\n"
            "    y = 2\n"
            "    del unused\n"
            "    return data\n"
        )
        assert len(results) == 1

    def test_del_param_beyond_third_stmt_ignored(self):
        results = _detect(
            "def process(data, unused):\n"
            "    x = 1\n"
            "    y = 2\n"
            "    z = 3\n"
            "    del unused\n"
            "    return data\n"
        )
        assert results == []

    def test_del_local_variable_ignored(self):
        results = _detect(
            "def process(data):\n"
            "    temp = compute(data)\n"
            "    del temp\n"
            "    return data\n"
        )
        assert results == []

    def test_no_del_no_results(self):
        assert _detect("def f(x):\n    return x\n") == []

    def test_multiple_del_params(self):
        results = _detect(
            "def process(a, b, c):\n"
            "    del a\n"
            "    del b\n"
            "    return c\n"
        )
        assert len(results) == 2

    def test_kwonly_param(self):
        results = _detect(
            "def f(data, *, unused=None):\n"
            "    del unused\n"
            "    return data\n"
        )
        assert len(results) == 1

    def test_async_function(self):
        results = _detect(
            "async def f(data, unused):\n"
            "    del unused\n"
            "    return data\n"
        )
        assert len(results) == 1

    def test_no_params_no_crash(self):
        assert _detect("def f():\n    del something\n") == []

    def test_docstring_then_del_at_third_stmt_detected(self):
        """Docstring is stripped; del on real 3rd statement is within window."""
        results = _detect(
            "def process(data, unused):\n"
            '    """Process data."""\n'
            "    x = 1\n"
            "    y = 2\n"
            "    del unused\n"
            "    return data\n"
        )
        assert len(results) == 1

    def test_docstring_then_del_beyond_third_stmt_ignored(self):
        """Docstring is stripped; del on real 4th statement is outside window."""
        results = _detect(
            "def process(data, unused):\n"
            '    """Process data."""\n'
            "    x = 1\n"
            "    y = 2\n"
            "    z = 3\n"
            "    del unused\n"
            "    return data\n"
        )
        assert results == []

    def test_del_self_attribute_ignored(self):
        """del self.x is not a parameter deletion."""
        results = _detect(
            "def method(self, x):\n"
            "    del self.x\n"
            "    return x\n"
        )
        assert results == []
