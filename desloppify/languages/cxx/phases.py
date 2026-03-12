"""C/C++ detector phase runners."""

from __future__ import annotations

from pathlib import Path

from desloppify.base.output.terminal import log
from desloppify.engine.detectors.base import ComplexitySignal
from desloppify.languages._framework.base.shared_phases import run_structural_phase
from desloppify.languages._framework.base.types import LangRuntimeContract
from desloppify.state_io import Issue

CXX_COMPLEXITY_SIGNALS = [
    ComplexitySignal("includes", r"(?m)^\s*#include\s+", weight=1, threshold=20),
    ComplexitySignal("TODOs", r"(?m)//\s*(?:TODO|FIXME|HACK|XXX)", weight=2, threshold=0),
    ComplexitySignal(
        "types",
        r"(?m)^\s*(?:class|struct|enum)\s+[A-Za-z_]\w*",
        weight=2,
        threshold=6,
    ),
    ComplexitySignal("namespaces", r"(?m)^\s*namespace\s+[A-Za-z_]\w*", weight=1, threshold=4),
]


def phase_structural(
    path: Path,
    lang: LangRuntimeContract,
) -> tuple[list[Issue], dict[str, int]]:
    """Run structural analysis for C/C++ files."""
    return run_structural_phase(
        path,
        lang,
        complexity_signals=CXX_COMPLEXITY_SIGNALS,
        log_fn=log,
    )
