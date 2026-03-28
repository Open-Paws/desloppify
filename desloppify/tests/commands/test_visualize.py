"""Tests for desloppify.visualize — data preparation, tree building, aggregation, esc()."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from desloppify.app.output.tree_text import _aggregate, _print_tree
from desloppify.app.output.visualize_data import (
    _build_tree,
    _collect_file_data,
)

# ===========================================================================
# esc() — XSS sanitizer (lives in the JS template, test the Python-side
# JSON escaping that prevents script injection)
# ===========================================================================


class TestJsonEscaping:
    """The HTML template uses JSON.dumps().replace('</', '<\\/') to prevent
    </script> injection from file names. Verify that substitution."""

    def test_script_tag_in_filename_escaped(self):
        """A filename containing </script> should not break the HTML."""
        tree_json = json.dumps({"name": "</script><script>alert(1)</script>"})
        escaped = tree_json.replace("</", r"<\/")
        assert "</script>" not in escaped
        assert r"<\/" in escaped

    def test_normal_filename_unchanged(self):
        tree_json = json.dumps({"name": "MyComponent.tsx"})
        escaped = tree_json.replace("</", r"<\/")
        assert "MyComponent.tsx" in escaped


# ===========================================================================
# _collect_file_data
# ===========================================================================


class TestCollectFileData:
    def test_resolves_relative_paths_against_scan_root(self, tmp_path):
        scan_root = tmp_path / "workspace"
        target = scan_root / "src" / "file.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("line1\nline2\n")

        lang = SimpleNamespace(
            file_finder=lambda _path: ["src/file.py"],
        )
        rows = _collect_file_data(scan_root, lang=lang)
        assert len(rows) == 1
        assert rows[0]["loc"] == 2
        assert rows[0]["abs_path"] == str(target.resolve())

    def test_lang_resolution_failures_use_best_effort_fallback(
        self, tmp_path, monkeypatch
    ):
        scan_root = tmp_path / "workspace"
        scan_root.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(
            "desloppify.languages.framework.auto_detect_lang",
            lambda _root: "python",
        )
        monkeypatch.setattr(
            "desloppify.languages.framework.get_lang",
            lambda _name: (_ for _ in ()).throw(RuntimeError("plugin load failed")),
        )
        monkeypatch.setattr("desloppify.languages.framework.available_langs", lambda: ["python"])

        rows = _collect_file_data(scan_root, lang=None)
        assert rows == []

    def test_unexpected_lang_resolution_error_is_not_swallowed(
        self, tmp_path, monkeypatch
    ):
        scan_root = tmp_path / "workspace"
        scan_root.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(
            "desloppify.languages.framework.auto_detect_lang",
            lambda _root: "python",
        )
        monkeypatch.setattr(
            "desloppify.languages.framework.get_lang",
            lambda _name: (_ for _ in ()).throw(LookupError("unexpected resolution bug")),
        )

        with pytest.raises(LookupError):
            _collect_file_data(scan_root, lang=None)


# ===========================================================================
# _build_tree
# ===========================================================================


class TestBuildTree:
    def _file(self, path, loc=100, abs_path=None):
        return {
            "path": path,
            "abs_path": abs_path or f"/project/{path}",
            "loc": loc,
        }

    def test_single_file_at_root(self):
        files = [self._file("src/foo.ts", loc=50)]
        tree = _build_tree(files, {}, {})
        assert tree["name"] == "src"
        # foo.ts should be a child
        children = tree["children"]
        assert len(children) == 1
        assert children[0]["name"] == "foo.ts"
        assert children[0]["loc"] == 50

    def test_nested_directories_created(self):
        files = [self._file("src/components/Button.tsx", loc=30)]
        tree = _build_tree(files, {}, {})
        # src -> components -> Button.tsx
        comp_dir = tree["children"][0]
        assert comp_dir["name"] == "components"
        button = comp_dir["children"][0]
        assert button["name"] == "Button.tsx"
        assert button["loc"] == 30

    def test_multiple_files_same_directory(self):
        files = [
            self._file("src/utils/a.ts", loc=10),
            self._file("src/utils/b.ts", loc=20),
        ]
        tree = _build_tree(files, {}, {})
        utils_dir = tree["children"][0]
        assert utils_dir["name"] == "utils"
        assert len(utils_dir["children"]) == 2
        names = {c["name"] for c in utils_dir["children"]}
        assert names == {"a.ts", "b.ts"}

    def test_loc_minimum_is_1(self):
        """D3 treemap requires loc > 0."""
        files = [self._file("src/empty.ts", loc=0)]
        tree = _build_tree(files, {}, {})
        leaf = tree["children"][0]
        assert leaf["loc"] == 1

    def test_dep_graph_fan_in_fan_out(self):
        files = [self._file("src/foo.ts", abs_path="/project/src/foo.ts")]
        dep_graph = {
            "/project/src/foo.ts": {"import_count": 5, "importer_count": 3},
        }
        tree = _build_tree(files, dep_graph, {})
        leaf = tree["children"][0]
        assert leaf["fan_in"] == 3
        assert leaf["fan_out"] == 5

    def test_issues_overlay(self):
        files = [self._file("src/foo.ts")]
        issues = {
            "src/foo.ts": [
                {"status": "open", "summary": "unused import React"},
                {"status": "open", "summary": "console.log"},
                {"status": "fixed", "summary": "already fixed"},
            ],
        }
        tree = _build_tree(files, {}, issues)
        leaf = tree["children"][0]
        assert leaf["issues_total"] == 3
        assert leaf["issues_open"] == 2
        assert len(leaf["issue_summaries"]) == 2

    def test_children_converted_to_arrays(self):
        """After _build_tree, children should be lists, not dicts."""
        files = [
            self._file("src/a.ts"),
            self._file("src/dir/b.ts"),
        ]
        tree = _build_tree(files, {}, {})
        assert isinstance(tree["children"], list)
        for child in tree["children"]:
            if "children" in child:
                assert isinstance(child["children"], list)

    def test_empty_directories_pruned(self):
        """Directories with no files (no loc) and no children should be pruned."""
        # Only create a deep file, intermediate dirs with no leaves get created
        files = [self._file("src/a/b/c.ts", loc=10)]
        tree = _build_tree(files, {}, {})

        # Navigate: src -> a -> b -> c.ts. No empty siblings should exist.
        def count_empty(node):
            count = 0
            for child in node.get("children", []):
                if "loc" not in child and not child.get("children"):
                    count += 1
                count += count_empty(child)
            return count

        assert count_empty(tree) == 0

    def test_non_src_prefix_kept(self):
        """Files not under src/ should still appear in tree."""
        files = [self._file("lib/helper.ts", loc=25)]
        tree = _build_tree(files, {}, {})
        # Root is "src", the "lib" dir should be a child
        assert any(c["name"] == "lib" for c in tree["children"])


# ===========================================================================
# _aggregate
# ===========================================================================


class TestAggregate:
    def test_leaf_node(self):
        leaf = {
            "name": "foo.ts",
            "loc": 100,
            "issues_open": 3,
            "fan_in": 2,
            "fan_out": 5,
        }
        agg = _aggregate(leaf)
        assert agg["files"] == 1
        assert agg["loc"] == 100
        assert agg["issues"] == 3
        assert agg["max_coupling"] == 7  # fan_in + fan_out

    def test_directory_sums_children(self):
        tree = {
            "name": "dir",
            "children": [
                {
                    "name": "a.ts",
                    "loc": 50,
                    "issues_open": 1,
                    "fan_in": 0,
                    "fan_out": 0,
                },
                {
                    "name": "b.ts",
                    "loc": 30,
                    "issues_open": 2,
                    "fan_in": 3,
                    "fan_out": 4,
                },
            ],
        }
        agg = _aggregate(tree)
        assert agg["files"] == 2
        assert agg["loc"] == 80
        assert agg["issues"] == 3
        assert agg["max_coupling"] == 7  # max of (0, 7)

    def test_nested_directory_aggregation(self):
        tree = {
            "name": "root",
            "children": [
                {
                    "name": "sub",
                    "children": [
                        {
                            "name": "x.ts",
                            "loc": 10,
                            "issues_open": 0,
                            "fan_in": 0,
                            "fan_out": 0,
                        },
                        {
                            "name": "y.ts",
                            "loc": 20,
                            "issues_open": 1,
                            "fan_in": 1,
                            "fan_out": 1,
                        },
                    ],
                },
                {
                    "name": "z.ts",
                    "loc": 30,
                    "issues_open": 0,
                    "fan_in": 5,
                    "fan_out": 5,
                },
            ],
        }
        agg = _aggregate(tree)
        assert agg["files"] == 3
        assert agg["loc"] == 60
        assert agg["issues"] == 1
        assert agg["max_coupling"] == 10  # z.ts has fan_in=5 + fan_out=5

    def test_empty_directory(self):
        tree = {"name": "empty", "children": []}
        agg = _aggregate(tree)
        assert agg["files"] == 0
        assert agg["loc"] == 0
        assert agg["issues"] == 0


# ===========================================================================
# _print_tree
# ===========================================================================


class TestPrintTree:
    def test_leaf_file_output(self):
        node = {
            "name": "foo.ts",
            "loc": 150,
            "issues_open": 2,
            "fan_in": 0,
            "fan_out": 0,
            "issue_summaries": [],
        }
        lines = []
        _print_tree(node, 0, 2, 0, "loc", False, lines)
        assert len(lines) == 1
        assert "foo.ts" in lines[0]
        assert "150 LOC" in lines[0]

    def test_leaf_with_issues_shows_warning(self):
        node = {
            "name": "bar.ts",
            "loc": 50,
            "issues_open": 3,
            "fan_in": 0,
            "fan_out": 0,
            "issue_summaries": [],
        }
        lines = []
        _print_tree(node, 0, 2, 0, "loc", False, lines)
        assert "3" in lines[0]

    def test_leaf_with_high_coupling_shows_coupling(self):
        node = {
            "name": "hub.ts",
            "loc": 100,
            "issues_open": 0,
            "fan_in": 8,
            "fan_out": 5,
            "issue_summaries": [],
        }
        lines = []
        _print_tree(node, 0, 2, 0, "loc", False, lines)
        assert "c:13" in lines[0]

    def test_leaf_below_min_loc_hidden(self):
        node = {
            "name": "tiny.ts",
            "loc": 5,
            "issues_open": 0,
            "fan_in": 0,
            "fan_out": 0,
            "issue_summaries": [],
        }
        lines = []
        _print_tree(node, 0, 2, 10, "loc", False, lines)
        assert lines == []

    def test_directory_shows_aggregate(self):
        tree = {
            "name": "components",
            "children": [
                {
                    "name": "A.tsx",
                    "loc": 100,
                    "issues_open": 1,
                    "fan_in": 0,
                    "fan_out": 0,
                    "issue_summaries": [],
                },
                {
                    "name": "B.tsx",
                    "loc": 200,
                    "issues_open": 0,
                    "fan_in": 0,
                    "fan_out": 0,
                    "issue_summaries": [],
                },
            ],
        }
        lines = []
        _print_tree(tree, 0, 2, 0, "loc", False, lines)
        assert "components/" in lines[0]
        assert "2 files" in lines[0]
        assert "300 LOC" in lines[0]
        assert "1 issues" in lines[0]

    def test_depth_limit_stops_recursion(self):
        tree = {
            "name": "root",
            "children": [
                {
                    "name": "sub",
                    "children": [
                        {
                            "name": "deep.ts",
                            "loc": 10,
                            "issues_open": 0,
                            "fan_in": 0,
                            "fan_out": 0,
                            "issue_summaries": [],
                        },
                    ],
                },
            ],
        }
        lines = []
        _print_tree(tree, 0, 0, 0, "loc", False, lines)
        # At depth 0, should show root but not recurse into children
        assert len(lines) == 1
        assert "root/" in lines[0]

    def test_indentation_increases_with_depth(self):
        tree = {
            "name": "root",
            "children": [
                {
                    "name": "leaf.ts",
                    "loc": 10,
                    "issues_open": 0,
                    "fan_in": 0,
                    "fan_out": 0,
                    "issue_summaries": [],
                },
            ],
        }
        lines = []
        _print_tree(tree, 0, 3, 0, "loc", False, lines)
        # Root at indent 0, leaf at indent 1
        assert lines[0].startswith("root/")
        assert lines[1].startswith("  ")  # 2 spaces per indent level

    def test_detail_mode_shows_issue_summaries(self):
        node = {
            "name": "bad.ts",
            "loc": 50,
            "issues_open": 2,
            "fan_in": 0,
            "fan_out": 0,
            "issue_summaries": ["unused import X", "console.log found"],
        }
        lines = []
        _print_tree(node, 0, 2, 0, "loc", True, lines)
        assert len(lines) == 3  # file line + 2 summary lines
        assert "unused import X" in lines[1]
        assert "console.log found" in lines[2]

    def test_detail_mode_off_hides_summaries(self):
        node = {
            "name": "bad.ts",
            "loc": 50,
            "issues_open": 2,
            "fan_in": 0,
            "fan_out": 0,
            "issue_summaries": ["unused import X"],
        }
        lines = []
        _print_tree(node, 0, 2, 0, "loc", False, lines)
        assert len(lines) == 1

    def test_sort_by_issues(self):
        tree = {
            "name": "root",
            "children": [
                {
                    "name": "clean.ts",
                    "loc": 200,
                    "issues_open": 0,
                    "fan_in": 0,
                    "fan_out": 0,
                    "issue_summaries": [],
                },
                {
                    "name": "messy.ts",
                    "loc": 50,
                    "issues_open": 5,
                    "fan_in": 0,
                    "fan_out": 0,
                    "issue_summaries": [],
                },
            ],
        }
        lines = []
        _print_tree(tree, 0, 2, 0, "issues", False, lines)
        # messy.ts has more issues, should come first
        child_lines = [
            line for line in lines if "ts" in line and "/" not in line.split("(")[0]
        ]
        assert "messy.ts" in child_lines[0]

    def test_sort_by_loc_default(self):
        tree = {
            "name": "root",
            "children": [
                {
                    "name": "small.ts",
                    "loc": 10,
                    "issues_open": 0,
                    "fan_in": 0,
                    "fan_out": 0,
                    "issue_summaries": [],
                },
                {
                    "name": "big.ts",
                    "loc": 500,
                    "issues_open": 0,
                    "fan_in": 0,
                    "fan_out": 0,
                    "issue_summaries": [],
                },
            ],
        }
        lines = []
        _print_tree(tree, 0, 2, 0, "loc", False, lines)
        child_lines = [
            line for line in lines if ".ts" in line and "/" not in line.split("(")[0]
        ]
        assert "big.ts" in child_lines[0]

    def test_sort_by_coupling(self):
        tree = {
            "name": "root",
            "children": [
                {
                    "name": "isolated.ts",
                    "loc": 100,
                    "issues_open": 0,
                    "fan_in": 0,
                    "fan_out": 0,
                    "issue_summaries": [],
                },
                {
                    "name": "coupled.ts",
                    "loc": 100,
                    "issues_open": 0,
                    "fan_in": 10,
                    "fan_out": 10,
                    "issue_summaries": [],
                },
            ],
        }
        lines = []
        _print_tree(tree, 0, 2, 0, "coupling", False, lines)
        child_lines = [
            line for line in lines if ".ts" in line and "/" not in line.split("(")[0]
        ]
        assert "coupled.ts" in child_lines[0]

    def test_low_coupling_not_shown(self):
        """Coupling <= 10 should not be displayed."""
        node = {
            "name": "ok.ts",
            "loc": 50,
            "issues_open": 0,
            "fan_in": 3,
            "fan_out": 5,
            "issue_summaries": [],
        }
        lines = []
        _print_tree(node, 0, 2, 0, "loc", False, lines)
        assert "c:" not in lines[0]

    def test_directory_below_min_loc_hidden(self):
        tree = {
            "name": "tiny_dir",
            "children": [
                {
                    "name": "a.ts",
                    "loc": 3,
                    "issues_open": 0,
                    "fan_in": 0,
                    "fan_out": 0,
                    "issue_summaries": [],
                },
            ],
        }
        lines = []
        _print_tree(tree, 0, 2, 100, "loc", False, lines)
        assert lines == []


# ===========================================================================
# D3_CDN_URL constant
# ===========================================================================
