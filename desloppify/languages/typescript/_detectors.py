"""Detector wiring helpers for TypeScript language configuration."""

from __future__ import annotations

from pathlib import Path

from desloppify.base.discovery.source import find_ts_files
from desloppify.engine.detectors.base import FunctionInfo
from desloppify.languages._framework.base.types import DetectorPhase
from desloppify.languages._framework.treesitter.phases import make_cohesion_phase
from desloppify.languages.typescript.extractors_functions import extract_ts_functions


def ts_treesitter_phases() -> list[DetectorPhase]:
    """Cherry-pick tree-sitter phases that complement TS's own detectors."""
    from desloppify.languages._framework.treesitter import get_spec, is_available

    if not is_available():
        return []

    spec = get_spec("typescript")
    if spec is None:
        return []

    return [make_cohesion_phase(spec)]


def ts_extract_functions(path: Path) -> list[FunctionInfo]:
    """Extract all TS functions for duplicate detection."""
    functions = []
    for filepath in find_ts_files(path):
        if "node_modules" in filepath or ".d.ts" in filepath:
            continue
        functions.extend(extract_ts_functions(filepath))
    return functions


__all__ = ["ts_extract_functions", "ts_treesitter_phases"]
