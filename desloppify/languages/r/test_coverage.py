"""R-specific test coverage heuristics and mappings.

Maps testthat convention: tests/testthat/test-*.R -> R/*.R
"""

from __future__ import annotations

import os
import re

ASSERT_PATTERNS = [
    re.compile(p)
    for p in [
        r"\bexpect_\w+\s*\(",
        r"\bverify_output\s*\(",
    ]
]
MOCK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\blocal_mocked_bindings\s*\("),
    re.compile(r"\bwith_mocked_bindings\s*\("),
    re.compile(r"\bwith_mock\s*\("),
]
SNAPSHOT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bexpect_snapshot_value\s*\("),
    re.compile(r"\bexpect_snapshot_file\s*\("),
    re.compile(r"\bexpect_snapshot\s*\("),
    re.compile(r"\bsnapshot_review\s*\("),
]
TEST_FUNCTION_RE = re.compile(r"(?m)^\s*test_that\s*\(")
BARREL_BASENAMES: set[str] = set()

_R_LOGIC_RE = re.compile(r"(?m)^\s*\w+\s*<-\s*function\s*\(")


def has_testable_logic(filepath: str, content: str) -> bool:
    """Return True when an R file contains function declarations."""
    if filepath.endswith(".Rmd"):
        return False
    return bool(_R_LOGIC_RE.search(content))


def resolve_import_spec(
    spec: str, test_path: str, production_files: set[str]
) -> str | None:
    """Best-effort R library()/require() to local file resolution."""
    normalized = spec.strip().strip("\"'`")

    if not normalized or normalized in (
        "base", "stats", "utils", "methods", "graphics",
        "grDevices", "datasets", "tools",
    ):
        return None

    normalized_production = {
        fp.replace("\\", "/").strip("/"): fp for fp in production_files
    }

    candidates: list[str] = [
        f"R/{normalized}.R",
        f"R/{normalized}.r",
        normalized.replace(".", "/") + ".R",
    ]

    test_dir = os.path.dirname(test_path)
    if test_dir:
        candidates.append(f"{test_dir}/R/{normalized}.R")

    for candidate in candidates:
        norm = candidate.replace("\\", "/").strip("/")
        if norm in normalized_production:
            return normalized_production[norm]

    return None


def resolve_barrel_reexports(_filepath: str, _production_files: set[str]) -> set[str]:
    return set()


def parse_test_import_specs(content: str) -> list[str]:
    """Extract library/require names from test file content."""
    specs: list[str] = []
    for match in re.finditer(r"(?<!\w)(?:library|require)\s*\(\s*(\w[\w.]+)", content):
        specs.append(match.group(1))
    return specs


def map_test_to_source(test_path: str, production_set: set[str]) -> str | None:
    """Map a testthat test file to its R/ source counterpart.

    Convention: tests/testthat/test-my_module.R -> R/my_module.R
    """
    basename = os.path.basename(test_path)
    if not basename.startswith("test-") or not basename.endswith((".R", ".r")):
        return None

    stem = basename[5:-2]  # strip "test-" prefix and ".R"/".r" suffix
    candidate = f"R/{stem}.R"

    normalized_production = {
        fp.replace("\\", "/").strip("/"): fp for fp in production_set
    }
    norm_candidate = candidate.replace("\\", "/").strip("/")
    if norm_candidate in normalized_production:
        return normalized_production[norm_candidate]

    candidate_r = f"R/{stem}.r"
    norm_candidate_r = candidate_r.replace("\\", "/").strip("/")
    if norm_candidate_r in normalized_production:
        return normalized_production[norm_candidate_r]

    return None


def strip_test_markers(basename: str) -> str | None:
    """Strip R testthat naming marker to derive source basename."""
    if basename.startswith("test-") and basename.endswith(".R"):
        return basename[5:]
    if basename.startswith("test-") and basename.endswith(".r"):
        return f"{basename[5:-2]}.R"
    return None


def strip_comments(content: str) -> str:
    """Strip R comments (# to end of line) while preserving strings."""
    out: list[str] = []
    in_string: str | None = None
    i = 0
    while i < len(content):
        ch = content[i]
        nxt = content[i + 1] if i + 1 < len(content) else ""

        if in_string is not None:
            out.append(ch)
            if ch == "\\" and i + 1 < len(content):
                out.append(content[i + 1])
                i += 2
                continue
            if ch == in_string:
                in_string = None
            i += 1
            continue

        if ch in ('"', "'"):
            in_string = ch
            out.append(ch)
            i += 1
            continue

        if ch == "#":
            while i < len(content) and content[i] != "\n":
                i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)
