"""Direct tests for context_holistic budget and import-cache split modules."""

from __future__ import annotations

import ast

import desloppify.intelligence.review.context_holistic.budget.axes as axes_mod
import desloppify.intelligence.review.context_holistic.budget.scan as scan_mod
import desloppify.intelligence.review.context_holistic.budget.patterns_wrappers as wrappers_mod
import desloppify.intelligence.review.importing.cache as cache_mod


def test_budget_abstractions_axes_compute_and_assemble_context() -> None:
    sub_axes = axes_mod._compute_sub_axes(
        wrapper_rate=0.2,
        util_files=[{"file": "src/utils.py", "loc": 120}],
        indirection_hotspots=[{"max_chain_depth": 4, "chain_count": 10}],
        wide_param_bags=[{"wide_functions": 2, "config_bag_mentions": 12}],
        one_impl_interfaces=[{"interface": "IThing"}],
        delegation_classes=[{"delegation_ratio": 0.8}],
        facade_modules=[{"re_export_ratio": 0.9}],
        typed_dict_violation_files={"src/a.py"},
        total_typed_dict_violations=2,
        dict_any_count=1,
        enum_bypass_count=1,
    )
    assert set(sub_axes.keys()) == {
        "abstraction_leverage",
        "indirection_cost",
        "interface_honesty",
        "delegation_density",
        "definition_directness",
        "type_discipline",
    }

    context = axes_mod._assemble_context(
        util_files=[{"file": "src/utils.py", "loc": 120}],
        wrapper_rate=0.2,
        total_wrappers=5,
        total_function_signatures=20,
        wrappers_by_file=[{"file": "src/a.py", "count": 2}],
        one_impl_interfaces=[{"interface": "IThing"}],
        indirection_hotspots=[{"file": "src/a.py", "max_chain_depth": 4, "chain_count": 10}],
        wide_param_bags=[{"file": "src/a.py", "wide_functions": 2, "config_bag_mentions": 12}],
        delegation_classes=[{"class_name": "Facade", "delegation_ratio": 0.8}],
        facade_modules=[{"file": "src/facade.py", "re_export_ratio": 0.9}],
        typed_dict_violations=[{"file": "src/a.py", "count": 2}],
        total_typed_dict_violations=2,
        sub_axes=sub_axes,
        dict_any_annotations=[{"file": "src/a.py"}],
        enum_bypass_patterns=[{"file": "src/a.py"}],
        type_strategy_census={"typed_dict": [{"file": "src/a.py"}]},
    )
    assert "summary" in context
    assert context["summary"]["total_wrappers"] == 5
    assert "sub_axes" in context


def test_budget_scan_and_wrappers_patterns_helpers() -> None:
    code = (
        "def target(x):\n"
        "    return x\n\n"
        "def wrapper(x):\n"
        "    return target(x)\n\n"
        "class Service:\n"
        "    def a(self):\n"
        "        return self.repo.a()\n"
        "    def b(self):\n"
        "        return self.repo.b()\n"
        "    def c(self):\n"
        "        return self.repo.c()\n"
        "    def d(self):\n"
        "        return self.repo.d()\n"
    )
    tree = ast.parse(code)

    passthrough = wrappers_mod._find_python_passthrough_wrappers(tree)
    assert ("wrapper", "target") in passthrough

    delegation = wrappers_mod._find_delegation_heavy_classes(tree)
    assert delegation
    assert delegation[0]["delegate_target"] == "repo"

    facade_tree = ast.parse(
        "from pkg.mod import A, B, C\n"
        "from pkg.more import D\n"
        "X = 1\n"
    )
    facade = wrappers_mod._find_facade_modules(facade_tree, loc=20)
    assert facade is not None

    collector = scan_mod._AbstractionsCollector()
    scan_mod._scan_file(collector, "src/sample.py", code)
    derived = scan_mod._derive_post_scan_results(collector)
    scan_mod._sort_and_trim(collector, derived)
    assert collector.total_function_signatures >= 2

    full_context = scan_mod._abstractions_context({"src/sample.py": code})
    assert "summary" in full_context
    assert "sub_axes" in full_context


def test_import_cache_refresh_helpers(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cache_mod, "get_project_root", lambda: tmp_path)
    resolved_default = cache_mod.resolve_import_project_root(None)
    assert resolved_default == tmp_path

    source_file = tmp_path / "src" / "a.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("print('ok')\n", encoding="utf-8")

    file_cache: dict[str, dict] = {}
    cache_mod.upsert_review_cache_entry(
        file_cache,
        "src/a.py",
        project_root=tmp_path,
        hash_file_fn=lambda _path: "hash123",
        utc_now_fn=lambda: "2026-03-09T00:00:00+00:00",
        issue_count=3,
    )
    assert file_cache["src/a.py"]["content_hash"] == "hash123"
    assert file_cache["src/a.py"]["issue_count"] == 3

    state: dict = {}
    cache_mod.refresh_review_file_cache(
        state,
        reviewed_files=["src/a.py", "src/b.py"],
        issues_by_file={"src/a.py": 2},
        project_root=tmp_path,
        hash_file_fn=lambda _path: "hash456",
        utc_now_fn=lambda: "2026-03-09T00:00:00+00:00",
    )
    files = state["review_cache"]["files"]
    assert "src/a.py" in files
    assert "src/b.py" in files
    assert files["src/a.py"]["issue_count"] == 2
    assert files["src/b.py"]["issue_count"] == 0
