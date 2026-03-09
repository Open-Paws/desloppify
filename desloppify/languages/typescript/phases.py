"""TypeScript detector phase runners."""

from __future__ import annotations

from pathlib import Path

from desloppify.languages._framework.base.types import LangRuntimeContract
from desloppify.languages.typescript.phases_basic import (
    phase_deprecated,
    phase_exports,
    phase_logs,
    phase_unused,
)
from desloppify.languages.typescript.phases_config import (
    TS_COMPLEXITY_SIGNALS,
    TS_GOD_RULES,
    TS_SKIP_DIRS,
    TS_SKIP_NAMES,
)
from desloppify.languages.typescript.phases_coupling import (
    detect_coupling_violations as _detect_coupling_violations_impl,
)
from desloppify.languages.typescript.phases_coupling import (
    detect_cross_tool_imports as _detect_cross_tool_imports_impl,
)
from desloppify.languages.typescript.phases_coupling import (
    detect_cycles_and_orphans as _detect_cycles_and_orphans_impl,
)
from desloppify.languages.typescript.phases_coupling import (
    detect_facades as _detect_facades_impl,
)
from desloppify.languages.typescript.phases_coupling import (
    detect_naming_inconsistencies as _detect_naming_inconsistencies_impl,
)
from desloppify.languages.typescript.phases_coupling import (
    detect_pattern_anomalies as _detect_pattern_anomalies_impl,
)
from desloppify.languages.typescript.phases_coupling import (
    detect_single_use as _detect_single_use_impl,
)
from desloppify.languages.typescript.phases_coupling import (
    make_boundary_issues_impl,
    orphaned_detector_mod,
    phase_coupling_impl,
)
from desloppify.languages.typescript.phases_smells import phase_smells
from desloppify.languages.typescript.phases_structural import (
    _detect_flat_dirs,
    _detect_passthrough,
    _detect_props_bloat,
    _detect_structural_signals,
    phase_structural,
)
from desloppify.state import Issue


def _detect_single_use(path: Path, graph: dict, lang: LangRuntimeContract):
    return _detect_single_use_impl(path, graph, lang)


_detect_coupling_violations = _detect_coupling_violations_impl
_detect_cross_tool_imports = _detect_cross_tool_imports_impl


def _detect_cycles_and_orphans(path: Path, graph: dict, lang: LangRuntimeContract):
    return _detect_cycles_and_orphans_impl(path, graph, lang)


def _detect_facades(graph: dict, lang: LangRuntimeContract):
    return _detect_facades_impl(graph, lang)


def _detect_pattern_anomalies(path: Path):
    return _detect_pattern_anomalies_impl(path)


def _detect_naming_inconsistencies(path: Path, lang: LangRuntimeContract):
    return _detect_naming_inconsistencies_impl(path, lang)


def _make_boundary_issues(
    single_entries: list[dict],
    path: Path,
    graph: dict,
    lang: LangRuntimeContract,
    shared_prefix: str,
    tools_prefix: str,
):
    return make_boundary_issues_impl(
        single_entries,
        path,
        graph,
        lang,
        shared_prefix,
        tools_prefix,
    )


def phase_coupling(path: Path, lang: LangRuntimeContract) -> tuple[list[Issue], dict[str, int]]:
    return phase_coupling_impl(path, lang, make_boundary_issues_fn=_make_boundary_issues)


__all__ = [
    "TS_COMPLEXITY_SIGNALS",
    "TS_GOD_RULES",
    "TS_SKIP_DIRS",
    "TS_SKIP_NAMES",
    "_detect_coupling_violations",
    "_detect_cross_tool_imports",
    "_detect_cycles_and_orphans",
    "_detect_facades",
    "_detect_flat_dirs",
    "_detect_naming_inconsistencies",
    "_detect_passthrough",
    "_detect_pattern_anomalies",
    "_detect_props_bloat",
    "_detect_single_use",
    "_detect_structural_signals",
    "_make_boundary_issues",
    "orphaned_detector_mod",
    "phase_coupling",
    "phase_deprecated",
    "phase_exports",
    "phase_logs",
    "phase_smells",
    "phase_structural",
    "phase_unused",
]
