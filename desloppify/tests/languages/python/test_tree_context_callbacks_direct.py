"""Direct tests for callback tree-context smell detector helpers."""

from __future__ import annotations

import ast

import desloppify.languages.python.detectors.smells_ast._tree_context_callbacks as callbacks_mod


def test_count_callback_invocations_matches_only_named_calls() -> None:
    tree = ast.parse(
        """
def worker(log_func, other):
    log_func("a")
    helper()
    log_func("b")
"""
    )
    fn = tree.body[0]
    assert isinstance(fn, ast.FunctionDef)

    assert callbacks_mod._count_callback_invocations(fn, callback_name="log_func") == 2
    assert callbacks_mod._count_callback_invocations(fn, callback_name="other") == 0


def test_detect_callback_logging_reports_only_callback_args_that_are_called() -> None:
    tree = ast.parse(
        """
def sync_worker(log_func):
    log_func("a")

def ignored(custom_logger):
    custom_logger("x")

async def async_worker(*, print_func):
    print_func("x")
    print_func("y")

def declared_not_called(debug_print):
    pass
"""
    )

    results = callbacks_mod._detect_callback_logging("src/workers.py", tree)

    assert len(results) == 2
    assert results[0]["file"] == "src/workers.py"
    assert results[0]["content"] == "sync_worker(log_func=...) — called 1 time(s)"
    assert results[1]["content"] == "async_worker(print_func=...) — called 2 time(s)"
