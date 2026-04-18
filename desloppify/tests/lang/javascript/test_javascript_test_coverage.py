"""Tests for JavaScript-specific test coverage detection hooks."""

from __future__ import annotations

import os

from desloppify.languages.javascript import test_coverage as js_cov


def test_parse_test_import_specs_handles_esm_and_cjs() -> None:
    content = (
        "import { foo } from './foo.js';\n"
        "import './side-effect.js';\n"
        "const bar = require('./bar');\n"
        "import('./lazy.js');\n"
    )
    specs = js_cov.parse_test_import_specs(content)
    assert isinstance(specs, set)
    assert "./foo.js" in specs
    assert "./side-effect.js" in specs
    assert "./bar" in specs
    assert "./lazy.js" in specs


def test_parse_test_import_specs_deduplicates() -> None:
    content = "require('./util');\nrequire('./util');\n"
    specs = js_cov.parse_test_import_specs(content)
    assert specs == {"./util"}


def test_parse_test_import_specs_returns_empty_set_for_no_imports() -> None:
    assert js_cov.parse_test_import_specs("const x = 1;") == set()


def test_strip_test_markers_removes_test_suffix() -> None:
    assert js_cov.strip_test_markers("server.test.js") == "server.js"
    assert js_cov.strip_test_markers("util.spec.js") == "util.js"
    assert js_cov.strip_test_markers("app.js") is None


def test_map_test_to_source_finds_sibling_file() -> None:
    production_set = {"_ui/server.js", "_ui/github.js", "_ui/public/app.js"}
    result = js_cov.map_test_to_source("_ui/server.test.js", production_set)
    assert result == "_ui/server.js"


def test_map_test_to_source_returns_none_when_no_match() -> None:
    production_set = {"_ui/server.js"}
    result = js_cov.map_test_to_source("_ui/missing.test.js", production_set)
    assert result is None


def test_resolve_import_spec_resolves_relative_js_path() -> None:
    production = {"_ui/server.js", "_ui/github.js"}
    result = js_cov.resolve_import_spec("./server.js", "_ui/server.test.js", production)
    assert result == "_ui/server.js"


def test_resolve_import_spec_adds_js_extension() -> None:
    production = {"_ui/server.js"}
    result = js_cov.resolve_import_spec("./server", "_ui/server.test.js", production)
    assert result == "_ui/server.js"


def test_resolve_import_spec_skips_node_modules() -> None:
    production = {"_ui/server.js"}
    result = js_cov.resolve_import_spec("express", "_ui/server.test.js", production)
    assert result is None


def test_map_test_to_source_is_deterministic_on_basename_collision() -> None:
    # Two production files with the same basename in different directories.
    production = {"a/util.js", "b/util.js"}
    result1 = js_cov.map_test_to_source("test/util.test.js", production)
    # Call twice — result must be stable (no randomness from set iteration).
    result2 = js_cov.map_test_to_source("test/util.test.js", production)
    assert result1 == result2
    # Sorted basename fallback must pick the lexicographically first path.
    assert result1 == "a/util.js"
