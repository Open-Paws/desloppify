"""JavaScript-specific test coverage heuristics.

Supports Jest/Vitest/Mocha test naming conventions (.test.js, .spec.js) and
Node.js built-in assert module patterns.
"""

from __future__ import annotations

import os
import re

_IMPORT_RE = re.compile(
    r"""(?:\bfrom\s+|\bimport\s*\(\s*|\bimport\s+)(?:type\s+)?['"]([^'"]+)['"]|"""
    r"""(?:\brequire\s*\(\s*)['"]([^'"]+)['"]""",
    re.MULTILINE,
)

# Patterns for detecting assertion calls in JS test files
ASSERT_PATTERNS = [
    re.compile(p)
    for p in [
        r"expect\(",
        r"assert\.",
        r"\.should\.",
        r"\b(?:getBy|findBy|getAllBy|findAllBy)\w+\(",
        r"\.toBeInTheDocument\(",
        r"\.toBeVisible\(",
        r"\.toHaveTextContent\(",
        r"\.toHaveAttribute\(",
    ]
]

MOCK_PATTERNS = [
    re.compile(p)
    for p in [
        r"jest\.mock\(",
        r"jest\.spyOn\(",
        r"vi\.mock\(",
        r"vi\.spyOn\(",
        r"sinon\.",
    ]
]

SNAPSHOT_PATTERNS: list[re.Pattern[str]] = []

# Detects test('name', ...) or it('name', ...) call patterns
TEST_FUNCTION_RE = re.compile(r"""(?:it|test)\s*\(\s*['"]""")


def parse_test_import_specs(content: str) -> set[str]:
    """Extract import/require specs from a JavaScript test file."""
    return {
        spec
        for m in _IMPORT_RE.finditer(content)
        if (spec := m.group(1) or m.group(2))
    }


def map_test_to_source(test_path: str, production_set: set[str]) -> str | None:
    """Map a JavaScript test file to a production file by naming convention."""
    basename = os.path.basename(test_path)
    dirname = os.path.dirname(test_path)
    parent = os.path.dirname(dirname)

    candidates: list[str] = []

    for pattern in (".test.", ".spec."):
        if pattern in basename:
            src = basename.replace(pattern, ".")
            candidates.append(os.path.join(dirname, src))
            if parent:
                candidates.append(os.path.join(parent, src))

    dir_basename = os.path.basename(dirname)
    if dir_basename == "__tests__" and parent:
        candidates.append(os.path.join(parent, basename))

    # Exact path match takes priority.
    for c in candidates:
        if c in production_set:
            return c

    # Deterministic basename fallback: build a sorted basename → path mapping,
    # then return the first match across sorted candidates to avoid non-determinism
    # when multiple production files share the same basename.
    prod_base_map: dict[str, list[str]] = {}
    for prod in sorted(production_set):
        prod_base_map.setdefault(os.path.basename(prod), []).append(prod)

    for c in sorted(candidates):
        matches = prod_base_map.get(os.path.basename(c), [])
        if matches:
            return matches[0]

    return None


def strip_test_markers(basename: str) -> str | None:
    """Strip JavaScript test naming markers to derive a source basename."""
    for marker in (".test.", ".spec."):
        if marker in basename:
            return basename.replace(marker, ".")
    return None


def resolve_import_spec(
    spec: str, test_path: str, production_files: set[str]
) -> str | None:
    """Resolve a JS import spec to a production file path."""
    if not spec.startswith("."):
        return None

    base = os.path.dirname(test_path)
    candidate = os.path.normpath(os.path.join(base, spec))
    for ext in ("", ".js", ".jsx", ".mjs", ".cjs", "/index.js", "/index.jsx"):
        path = candidate + ext
        if path in production_files:
            return path

    return None
