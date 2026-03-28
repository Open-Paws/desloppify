"""Direct coverage tests for holistic budget_analysis helpers."""

from __future__ import annotations

import ast

from desloppify.intelligence.review.context_holistic.budget import analysis as analysis_mod


def test_budget_analysis_exports_expected_symbols() -> None:
    assert set(analysis_mod.__all__) == {
        "_count_signature_params",
        "_extract_type_names",
        "_score_clamped",
        "_strip_docstring",
    }


def test_budget_analysis_helpers_are_callable_directly() -> None:
    assert analysis_mod._count_signature_params("self, a, b, cls, this, c") == 3
    assert analysis_mod._extract_type_names("pkg.UserRepo<T>, Service:") == [
        "UserRepo",
        "Service",
    ]
    assert analysis_mod._score_clamped(101.4) == 100


def test_strip_docstring_removes_leading_string_expr_only() -> None:
    fn = ast.parse(
        "def build(x):\n"
        '    """doc"""\n'
        "    y = x + 1\n"
        "    return y\n"
    ).body[0]
    assert isinstance(fn, ast.FunctionDef)

    stripped = analysis_mod._strip_docstring(fn.body)
    assert len(stripped) == 2
    assert isinstance(stripped[0], ast.Assign)
    assert isinstance(stripped[1], ast.Return)


def test_strip_docstring_keeps_body_when_no_docstring() -> None:
    fn = ast.parse(
        "def build(x):\n"
        "    y = x + 1\n"
        "    return y\n"
    ).body[0]
    assert isinstance(fn, ast.FunctionDef)

    stripped = analysis_mod._strip_docstring(fn.body)
    assert len(stripped) == 2
    assert isinstance(stripped[0], ast.Assign)
    assert isinstance(stripped[1], ast.Return)
