"""TypeScript detector phase runners."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from desloppify.languages._framework.base.types import LangRuntimeContract
from desloppify.languages.typescript.phases_basic import (
    phase_deprecated as _phase_deprecated,
    phase_exports as _phase_exports,
    phase_logs as _phase_logs,
    phase_unused as _phase_unused,
)
from desloppify.languages.typescript.phases_config import (
    TS_COMPLEXITY_SIGNALS,
    TS_GOD_RULES,
    TS_SKIP_DIRS,
    TS_SKIP_NAMES,
)
from desloppify.languages.typescript.phases_coupling import (
    detect_coupling_violations,
    detect_cross_tool_imports,
    detect_cycles_and_orphans,
    detect_facades,
    detect_naming_inconsistencies,
    detect_pattern_anomalies,
    detect_single_use,
    make_boundary_issues,
    orphaned_detector_mod,
    phase_coupling as _phase_coupling,
)
from desloppify.languages.typescript.phases_smells import phase_smells as _phase_smells
from desloppify.languages.typescript.phases_structural import (
    _detect_flat_dirs,
    _detect_passthrough,
    _detect_props_bloat,
    _detect_structural_signals,
    phase_structural as _phase_structural,
)
from desloppify.state import Issue

PhasePotentialMap = dict[str, int]
PhaseResult = tuple[list[Issue], PhasePotentialMap]
PhaseWrapper = Callable[[Path, LangRuntimeContract], PhaseResult]


def phase_logs(path: Path, lang: LangRuntimeContract) -> tuple[list[Issue], dict[str, int]]:
    """Run the logs phase using the shared typed phase wrapper signature."""
    return _phase_logs(path, lang)


def phase_unused(path: Path, lang: LangRuntimeContract) -> tuple[list[Issue], dict[str, int]]:
    """Run the unused phase using the shared typed phase wrapper signature."""
    return _phase_unused(path, lang)


def phase_exports(path: Path, lang: LangRuntimeContract) -> tuple[list[Issue], dict[str, int]]:
    """Run the dead-exports phase using the shared typed phase wrapper signature."""
    return _phase_exports(path, lang)


def phase_deprecated(path: Path, lang: LangRuntimeContract) -> tuple[list[Issue], dict[str, int]]:
    """Run the deprecated API phase using the shared typed phase wrapper signature."""
    return _phase_deprecated(path, lang)


def phase_structural(path: Path, lang: LangRuntimeContract) -> tuple[list[Issue], dict[str, int]]:
    """Run the structural phase using the shared typed phase wrapper signature."""
    return _phase_structural(path, lang)


def phase_coupling(path: Path, lang: LangRuntimeContract) -> tuple[list[Issue], dict[str, int]]:
    """Run the coupling phase using the shared typed phase wrapper signature."""
    return _phase_coupling(path, lang)


def phase_smells(path: Path, lang: LangRuntimeContract) -> tuple[list[Issue], dict[str, int]]:
    """Run the smells phase using the shared typed phase wrapper signature."""
    return _phase_smells(path, lang)


__all__ = [
    "PhasePotentialMap",
    "PhaseResult",
    "PhaseWrapper",
    "TS_COMPLEXITY_SIGNALS",
    "TS_GOD_RULES",
    "TS_SKIP_DIRS",
    "TS_SKIP_NAMES",
    "detect_coupling_violations",
    "detect_cross_tool_imports",
    "detect_cycles_and_orphans",
    "detect_facades",
    "detect_naming_inconsistencies",
    "detect_pattern_anomalies",
    "detect_single_use",
    "_detect_flat_dirs",
    "_detect_passthrough",
    "_detect_props_bloat",
    "_detect_structural_signals",
    "make_boundary_issues",
    "orphaned_detector_mod",
    "phase_coupling",
    "phase_deprecated",
    "phase_exports",
    "phase_logs",
    "phase_smells",
    "phase_structural",
    "phase_unused",
]
