"""Direct tests for AST smell dispatch registries and deterministic output."""

from __future__ import annotations

import inspect

import desloppify.languages.python.detectors.smells_ast._dispatch as dispatch_mod
from desloppify.languages.python.detectors.smells_ast._dispatch import (
    NODE_DETECTORS,
    TREE_DETECTORS,
    detect_ast_smells,
)


def test_dispatch_registry_ids_are_unique():
    ids = [spec.smell_id for spec in NODE_DETECTORS] + [
        spec.smell_id for spec in TREE_DETECTORS
    ]
    assert len(ids) == len(set(ids))
    assert "dead_function" in ids
    assert "annotation_quality" in ids


def test_detect_ast_smells_produces_stable_sorted_matches():
    source = """
def zed():
    pass

def alpha():
    pass
"""
    smell_counts: dict[str, list[dict]] = {"dead_function": []}

    detect_ast_smells("file.py", source, smell_counts)

    lines = [match["line"] for match in smell_counts["dead_function"]]
    assert lines == sorted(lines)


def test_dispatch_registry_avoids_inline_lambda_wrappers():
    source = inspect.getsource(dispatch_mod)
    assert "lambda filepath, node, tree" not in source
    assert "lambda filepath, tree, all_nodes" not in source
