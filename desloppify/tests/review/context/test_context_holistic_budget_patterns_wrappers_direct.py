"""Direct coverage tests for holistic budget pattern wrapper scanners."""

from __future__ import annotations

import ast

from desloppify.intelligence.review.context_holistic import (
    budget_patterns_wrappers as wrappers_mod,
)


def _parse(content: str) -> ast.Module:
    return ast.parse(content)


def test_budget_patterns_wrappers_exports_expected_symbols() -> None:
    assert set(wrappers_mod.__all__) == {
        "_find_delegation_heavy_classes",
        "_find_facade_modules",
        "_find_python_passthrough_wrappers",
        "_is_delegation_stmt",
        "_python_passthrough_target",
    }


def test_python_passthrough_target_detects_return_call_name() -> None:
    stmt = _parse("def f():\n    return build(x)\n").body[0].body[0]
    assert wrappers_mod._python_passthrough_target(stmt) == "build"

    non_match = _parse("def f():\n    value = build(x)\n").body[0].body[0]
    assert wrappers_mod._python_passthrough_target(non_match) is None


def test_is_delegation_stmt_detects_self_attribute_chain() -> None:
    stmt = _parse("def f(self):\n    return self.inner.service.run()\n").body[0].body[0]
    assert wrappers_mod._is_delegation_stmt(stmt) == "inner"

    non_match = _parse("def f(obj):\n    return obj.inner.run()\n").body[0].body[0]
    assert wrappers_mod._is_delegation_stmt(non_match) is None


def test_find_python_passthrough_wrappers_reports_wrapper_pairs() -> None:
    tree = _parse(
        "def wrap_user(value):\n"
        "    return build_user(value)\n\n"
        "def build_user(value):\n"
        "    return value\n"
    )
    assert wrappers_mod._find_python_passthrough_wrappers(tree) == [
        ("wrap_user", "build_user"),
    ]


def test_find_facade_modules_detects_re_export_heavy_module() -> None:
    tree = _parse(
        "from x import A, B, C\n"
        "from y import D\n"
        "class Local: pass\n"
    )
    result = wrappers_mod._find_facade_modules(tree, loc=3)
    assert result is not None
    assert result["re_export_ratio"] >= 0.7
    assert result["defined_symbols"] == 1
