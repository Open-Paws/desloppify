"""Test coverage mapping — import resolution, naming conventions, quality analysis."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from desloppify.base.discovery.paths import get_project_root
from desloppify.engine.detectors.coverage.mapping_analysis import (
    analyze_test_quality_core,
    build_test_import_index_core,
    get_test_files_for_prod_core,
    transitive_coverage_core,
)
from desloppify.engine.detectors.test_coverage.io import read_coverage_file
from desloppify.engine.hook_registry import get_lang_hook

logger = logging.getLogger(__name__)


def _load_lang_test_coverage_module(lang_name: str | None):
    """Load language-specific test coverage helpers from ``lang/<name>/test_coverage.py``."""
    return get_lang_hook(lang_name, "test_coverage") or object()


def _infer_lang_name(test_files: set[str], production_files: set[str]) -> str | None:
    """Infer language from known file extensions when explicit lang is unavailable."""
    paths = list(test_files) + list(production_files)
    ext_to_lang = {
        ".py": "python",
        ".pyi": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "typescript",
        ".jsx": "typescript",
        ".cs": "csharp",
    }
    counts: dict[str, int] = {}
    for file_path in paths:
        suffix = Path(file_path).suffix.lower()
        lang_name = ext_to_lang.get(suffix)
        if not lang_name:
            continue
        counts[lang_name] = counts.get(lang_name, 0) + 1
    if counts:
        return max(counts.items(), key=lambda item: item[1])[0]
    return None


def _build_prod_module_index(production_files: set[str]) -> dict[str, str]:
    """Build a mapping from module basename/dotted-path to full file path."""
    prod_by_module: dict[str, str] = {}
    root_str = str(get_project_root()) + os.sep
    for pf in production_files:
        rel_pf = pf[len(root_str) :] if pf.startswith(root_str) else pf
        module_name = rel_pf.replace("/", ".").replace("\\", ".")
        if "." in module_name:
            module_name = module_name.rsplit(".", 1)[0]
        prod_by_module[module_name] = pf

        # __init__.py: also map package path (e.g. "foo.bar" -> __init__.py).
        if module_name.endswith(".__init__"):
            prod_by_module[module_name[: -len(".__init__")]] = pf

        parts = module_name.split(".")
        if parts:
            prod_by_module[parts[-1]] = pf
    return prod_by_module


def _graph_tested_imports(
    graph: dict,
    test_files: set[str],
    production_files: set[str],
    prod_by_module: dict[str, str],
    lang_name: str | None,
) -> set[str]:
    """Follow import graph edges from test files to find directly-tested production files."""
    tested: set[str] = set()
    for tf in test_files:
        entry = graph.get(tf)
        graph_mapped: set[str] = set()
        if entry is not None:
            for imp in entry.get("imports", set()):
                if imp in production_files:
                    graph_mapped.add(imp)
            tested |= graph_mapped

        # Parse source imports as a supplement when graph imports are absent,
        # or always for TypeScript where dynamic import('...') is common in
        # coverage smoke tests and may be missed by static graph building.
        if not graph_mapped or lang_name == "typescript":
            tested |= _parse_test_imports(
                tf, production_files, prod_by_module, lang_name
            )
    return tested


def _expand_barrel_targets(
    *,
    tested: set[str],
    barrel_basenames: set[str],
    production_files: set[str],
    lang_name: str | None,
) -> set[str]:
    """Expand barrel/index file imports to the actual modules they re-export."""
    extra: set[str] = set()
    barrel_files = [f for f in tested if os.path.basename(f) in barrel_basenames]
    for bf in barrel_files:
        extra |= _resolve_barrel_reexports(bf, production_files, lang_name)
    return extra


def _expand_facade_targets(
    *,
    tested: set[str],
    graph: dict,
    production_files: set[str],
    has_logic,
) -> set[str]:
    """Expand facade imports to their underlying implementation files.

    If a directly-tested file has no testable logic (pure re-export facade),
    promote its imports to directly tested.  This prevents false
    "transitive_only" issues for internal modules behind facades like
    scoring.py -> _scoring/policy/core.py.
    """
    facade_targets: set[str] = set()
    for f in list(tested):
        entry = graph.get(f)
        if entry is None:
            continue
        read_result = read_coverage_file(
            f, context="coverage_import_mapping_facade_logic"
        )
        if not read_result.ok:
            continue
        content = read_result.content
        if not has_logic(f, content):
            for imp in entry.get("imports", set()):
                if imp in production_files:
                    facade_targets.add(imp)
    return facade_targets


def import_based_mapping(
    graph: dict,
    test_files: set[str],
    production_files: set[str],
    lang_name: str | None = None,
) -> set[str]:
    """Map test files to production files via import edges."""
    lang_name = lang_name or _infer_lang_name(test_files, production_files)
    mod = _load_lang_test_coverage_module(lang_name)

    prod_by_module = _build_prod_module_index(production_files)
    tested = _graph_tested_imports(
        graph, test_files, production_files, prod_by_module, lang_name
    )

    barrel_basenames = getattr(mod, "BARREL_BASENAMES", set())
    if barrel_basenames:
        tested |= _expand_barrel_targets(
            tested=tested,
            barrel_basenames=barrel_basenames,
            production_files=production_files,
            lang_name=lang_name,
        )

    has_logic = getattr(mod, "has_testable_logic", None)
    if callable(has_logic):
        tested |= _expand_facade_targets(
            tested=tested,
            graph=graph,
            production_files=production_files,
            has_logic=has_logic,
        )

    return tested


def _resolve_import(
    spec: str,
    test_path: str,
    production_files: set[str],
    lang_name: str | None,
) -> str | None:
    mod = _load_lang_test_coverage_module(lang_name)
    resolver = getattr(mod, "resolve_import_spec", None)
    if callable(resolver):
        return resolver(spec, test_path, production_files)
    return None


def _resolve_barrel_reexports(
    filepath: str,
    production_files: set[str],
    lang_name: str | None = None,
) -> set[str]:
    """Resolve one-hop re-exports using language-specific helpers."""
    if lang_name is None:
        lang_name = _infer_lang_name({filepath}, production_files)
    mod = _load_lang_test_coverage_module(lang_name)
    resolver = getattr(mod, "resolve_barrel_reexports", None)
    if callable(resolver):
        return resolver(filepath, production_files)
    return set()


def _parse_test_imports(
    test_path: str,
    production_files: set[str],
    prod_by_module: dict[str, str],
    lang_name: str | None = None,
) -> set[str]:
    """Parse import statements from a test file and resolve production files."""
    tested = set()
    read_result = read_coverage_file(test_path, context="coverage_import_mapping_parse")
    if not read_result.ok:
        return tested
    content = read_result.content

    if lang_name is None:
        lang_name = _infer_lang_name({test_path}, production_files)

    mod = _load_lang_test_coverage_module(lang_name)
    parse_specs = getattr(mod, "parse_test_import_specs", None)
    if not callable(parse_specs):
        return tested

    for spec in parse_specs(content):
        if not spec:
            continue

        resolved = _resolve_import(spec, test_path, production_files, lang_name)
        if resolved:
            tested.add(resolved)
            continue

        # Fallback: module-name lookup with progressively shorter prefixes.
        cleaned = spec.lstrip("./").replace("/", ".")
        parts = cleaned.split(".")
        for i in range(len(parts), 0, -1):
            candidate = ".".join(parts[:i])
            if candidate in prod_by_module:
                tested.add(prod_by_module[candidate])
                break

    return tested


def _map_test_to_source(
    test_path: str,
    production_set: set[str],
    lang_name: str,
) -> str | None:
    """Match a test file to a production file using language conventions."""
    mod = _load_lang_test_coverage_module(lang_name)
    mapper = getattr(mod, "map_test_to_source", None)
    if callable(mapper):
        return mapper(test_path, production_set)
    return None


def naming_based_mapping(
    test_files: set[str],
    production_files: set[str],
    lang_name: str,
) -> set[str]:
    """Map test files to production files by naming conventions."""
    tested = set()

    prod_by_basename: dict[str, list[str]] = {}
    for p in production_files:
        bn = os.path.basename(p)
        prod_by_basename.setdefault(bn, []).append(p)

    for tf in test_files:
        matched = _map_test_to_source(tf, production_files, lang_name)
        if matched:
            tested.add(matched)
            continue

        basename = os.path.basename(tf)
        src_name = _strip_test_markers(basename, lang_name)
        if src_name and src_name in prod_by_basename:
            for p in prod_by_basename[src_name]:
                tested.add(p)

    return tested


def _strip_test_markers(basename: str, lang_name: str) -> str | None:
    """Strip test naming markers from a basename to derive source basename."""
    mod = _load_lang_test_coverage_module(lang_name)
    strip_markers = getattr(mod, "strip_test_markers", None)
    if callable(strip_markers):
        return strip_markers(basename)
    return None


def transitive_coverage(
    directly_tested: set[str],
    graph: dict,
    production_files: set[str],
) -> set[str]:
    """BFS from directly-tested files through dep-graph imports."""
    return transitive_coverage_core(directly_tested, graph, production_files)


def analyze_test_quality(
    test_files: set[str],
    lang_name: str,
) -> dict[str, dict]:
    """Analyze test quality per file."""
    return analyze_test_quality_core(
        test_files,
        lang_name,
        load_lang_module=_load_lang_test_coverage_module,
        read_coverage_file_fn=read_coverage_file,
        logger=logger,
    )


def get_test_files_for_prod(
    prod_file: str,
    test_files: set[str],
    graph: dict,
    lang_name: str,
    parsed_imports_by_test: dict[str, set[str]] | None = None,
) -> list[str]:
    """Find which test files exercise a given production file."""
    return get_test_files_for_prod_core(
        prod_file,
        test_files,
        graph,
        lang_name,
        parsed_imports_by_test,
        parse_test_imports_fn=_parse_test_imports,
        map_test_to_source_fn=_map_test_to_source,
        project_root=str(get_project_root()),
    )


def build_test_import_index(
    test_files: set[str],
    production_files: set[str],
    lang_name: str,
) -> dict[str, set[str]]:
    """Parse test import sources once, producing a test->production import index."""
    return build_test_import_index_core(
        test_files,
        production_files,
        lang_name,
        parse_test_imports_fn=_parse_test_imports,
        project_root=str(get_project_root()),
    )
