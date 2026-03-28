"""Direct coverage tests for tree-sitter complexity helper modules."""

from __future__ import annotations

from types import SimpleNamespace

import desloppify.languages._framework.treesitter.analysis.complexity_callbacks as callbacks_mod
import desloppify.languages._framework.treesitter.analysis.complexity_shared as shared_mod


class _FakeNode:
    def __init__(self, node_type: str, children: list["_FakeNode"] | None = None) -> None:
        self.type = node_type
        self.children = children or []
        self.child_count = len(self.children)


def test_make_callback_depth_compute_returns_depth_for_nested_closures(monkeypatch) -> None:
    spec = SimpleNamespace(grammar="javascript")

    def _fake_ensure(cache: dict, _spec) -> bool:
        cache["parser"] = object()
        return True

    root = _FakeNode(
        "program",
        [_FakeNode("function_expression", [_FakeNode("arrow_function")])],
    )
    fake_tree = SimpleNamespace(root_node=root)
    monkeypatch.setattr(callbacks_mod, "_ensure_parser", _fake_ensure)
    monkeypatch.setattr(
        callbacks_mod,
        "get_or_parse_tree",
        lambda *_args, **_kwargs: ("src", fake_tree),
    )

    compute = callbacks_mod.make_callback_depth_compute(spec)
    assert compute("", [], _filepath="src/a.ts") == (2, "callback depth 2")


def test_make_callback_depth_compute_returns_none_for_missing_or_shallow(monkeypatch) -> None:
    spec = SimpleNamespace(grammar="javascript")

    def _fake_ensure(cache: dict, _spec) -> bool:
        cache["parser"] = object()
        return True

    shallow_tree = SimpleNamespace(root_node=_FakeNode("program", [_FakeNode("function_expression")]))
    monkeypatch.setattr(callbacks_mod, "_ensure_parser", _fake_ensure)
    monkeypatch.setattr(
        callbacks_mod,
        "get_or_parse_tree",
        lambda *_args, **_kwargs: ("src", shallow_tree),
    )

    compute = callbacks_mod.make_callback_depth_compute(spec)
    assert compute("", [], _filepath="") is None
    assert compute("", [], _filepath="src/a.ts") is None


def test_ensure_parser_initializes_cache_with_optional_query(monkeypatch) -> None:
    cache: dict[str, object] = {}
    spec = SimpleNamespace(grammar="go", function_query="(function_declaration)")
    monkeypatch.setattr(shared_mod, "_get_parser", lambda _grammar: ("parser", "lang"))
    monkeypatch.setattr(shared_mod, "_make_query", lambda _lang, query: f"query:{query}")
    assert shared_mod._ensure_parser(cache, spec, with_query=True) is True
    assert cache["parser"] == "parser"
    assert cache["language"] == "lang"
    assert cache["query"] == "query:(function_declaration)"


def test_ensure_parser_handles_init_failure(monkeypatch) -> None:
    cache: dict[str, object] = {}
    spec = SimpleNamespace(grammar="go", function_query="")
    monkeypatch.setattr(
        shared_mod,
        "_get_parser",
        lambda _grammar: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert shared_mod._ensure_parser(cache, spec) is False
    assert "parser" not in cache
