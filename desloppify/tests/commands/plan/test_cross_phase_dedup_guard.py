"""Guard: shared detectors with dedicated phases must not be called from language-specific phases.

The shared phase factories in phase_builders.py wrap certain detectors
(signature, security, test_coverage, etc.) so they run exactly once per scan.
If a language-specific phase file also imports and calls one of those detectors
directly, issues get duplicated under different namespaces — and because the
IDs differ, wontfix/resolve on one copy leaves the other as a ghost.

This test statically checks that no language-specific phase file imports a
detector module listed in EXCLUSIVE_DETECTOR_MODULES.
"""

from __future__ import annotations

import ast
from pathlib import Path

from desloppify.languages._framework.base.phase_builders import (
    EXCLUSIVE_DETECTOR_MODULES,
)

_LANGUAGES_DIR = Path(__file__).resolve().parents[2] / "languages"


def _detector_imports_in(source: str) -> list[str]:
    """Extract full module paths of engine.detectors imports from source."""
    modules: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return modules
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if "engine.detectors" not in node.module:
            continue
        if node.module.count(".") > 2:
            modules.append(node.module)
        else:
            for alias in node.names:
                modules.append(f"{node.module}.{alias.name}")
    return modules


def test_no_language_phase_imports_shared_detector():
    """Language-specific phase files must not import detectors owned by shared phases.

    If this test fails, a language-specific phase is importing a shared detector
    that already runs via a shared phase factory. Remove the direct detector
    call and ensure the shared phase is registered in the language's phase list.

    The authoritative list lives in phase_builders.EXCLUSIVE_DETECTOR_MODULES.
    """
    phase_files = sorted(
        p for p in _LANGUAGES_DIR.rglob("phases*.py")
        if "_framework" not in p.parts
    )
    violations = []
    for phase_file in phase_files:
        for imp in _detector_imports_in(phase_file.read_text()):
            if any(imp.startswith(m) for m in EXCLUSIVE_DETECTOR_MODULES):
                rel = phase_file.relative_to(_LANGUAGES_DIR.parent)
                violations.append(f"{rel} imports '{imp}'")

    assert violations == [], (
        "Shared detector imported from language-specific phase file(s):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
