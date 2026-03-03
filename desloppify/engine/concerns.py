"""Concern generators — mechanical issues → subjective review bridge.

Concerns are ephemeral: computed on-demand from current state, never persisted.
Only LLM-confirmed concerns become persistent Issue objects via review import.

Generators focus on cross-cutting synthesis — bundling all signals per file so
the LLM gets a complete picture, and surfacing systemic patterns across files
that no single detector captures.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal, TypedDict, cast

from desloppify.core.registry import JUDGMENT_DETECTORS


@dataclass(frozen=True)
class Concern:
    """A potential design problem surfaced by mechanical signals."""

    type: str  # concern classification
    file: str  # primary file (relative path)
    summary: str  # human-readable 1-liner
    evidence: tuple[str, ...]  # supporting data points
    question: str  # specific question for LLM to evaluate
    fingerprint: str  # stable hash for dismissal tracking
    source_issues: tuple[str, ...]  # issue IDs that triggered this


class ConcernSignals(TypedDict, total=False):
    """Typed signal payload extracted from mechanical issues."""

    max_params: float
    max_nesting: float
    loc: float
    function_count: float
    monster_loc: float
    monster_funcs: list[str]


_NUMERIC_SIGNAL_KEYS = ("max_params", "max_nesting", "loc", "function_count")
SignalKey = Literal["max_params", "max_nesting", "loc", "function_count", "monster_loc"]


def _update_max_signal(signals: ConcernSignals, key: SignalKey, value: object) -> None:
    """Update numeric signal key with max(existing, value) when value is valid."""
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return
    current = float(signals.get(key, 0.0))
    signals[key] = max(current, float(value))


def _fingerprint(concern_type: str, file: str, key_signals: tuple[str, ...]) -> str:
    """Stable hash of (type, file, sorted key signals)."""
    raw = f"{concern_type}::{file}::{','.join(sorted(key_signals))}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _is_dismissed(
    dismissals: dict, fingerprint: str, source_issue_ids: tuple[str, ...]
) -> bool:
    """Check if a concern was previously dismissed and source issues unchanged."""
    entry = dismissals.get(fingerprint)
    if not isinstance(entry, dict):
        return False
    prev_sources = set(entry.get("source_issue_ids", []))
    return prev_sources == set(source_issue_ids)


def _open_issues(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all open issues from state."""
    issues = state.get("issues", {})
    return [
        f for f in issues.values()
        if isinstance(f, dict) and f.get("status") == "open"
    ]


def _group_by_file(state: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Group open issues by file, excluding holistic (file='.')."""
    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in _open_issues(state):
        file = f.get("file", "")
        if file and file != ".":
            by_file[file].append(f)
    return dict(by_file)


# ── Signal extraction ────────────────────────────────────────────────


def _extract_signals(issues: list[dict[str, Any]]) -> ConcernSignals:
    """Extract key quantitative signals from a file's issues."""
    signals: ConcernSignals = {}
    monster_funcs: list[str] = []

    for f in issues:
        det = f.get("detector", "")
        detail_raw = f.get("detail", {})
        detail = detail_raw if isinstance(detail_raw, dict) else {}

        if det == "structural":
            s = detail.get("signals", {})
            if isinstance(s, dict):
                for key in _NUMERIC_SIGNAL_KEYS:
                    _update_max_signal(signals, cast(SignalKey, key), s.get(key, 0))

        if det == "smells" and detail.get("smell_id") == "monster_function":
            _update_max_signal(signals, "monster_loc", detail.get("loc", 0))
            func = detail.get("function", "")
            if isinstance(func, str) and func:
                monster_funcs.append(func)

    if monster_funcs:
        signals["monster_funcs"] = monster_funcs
    return signals


def _has_elevated_signals(issues: list[dict[str, Any]]) -> bool:
    """Does any issue have signals strong enough to flag on its own?"""
    for f in issues:
        det = f.get("detector", "")
        detail = f.get("detail", {})

        if det == "structural":
            s = detail.get("signals", {})
            if isinstance(s, dict):
                if s.get("max_params", 0) >= 8:
                    return True
                if s.get("max_nesting", 0) >= 6:
                    return True
                if s.get("loc", 0) >= 300:
                    return True

        if det == "smells" and detail.get("smell_id") == "monster_function":
            return True

        if det in ("dupes", "boilerplate_duplication", "coupling",
                    "responsibility_cohesion"):
            return True

    return False


# ── Concern classification ───────────────────────────────────────────


def _classify(detectors: set[str], signals: ConcernSignals) -> str:
    """Pick the most specific concern type from what's present."""
    if len(detectors) >= 3:
        return "mixed_responsibilities"
    if "dupes" in detectors or "boilerplate_duplication" in detectors:
        return "duplication_design"
    if signals.get("monster_loc", 0) > 0:
        return "structural_complexity"
    if "coupling" in detectors:
        return "coupling_design"
    if signals.get("max_params", 0) >= 8:
        return "interface_design"
    if signals.get("max_nesting", 0) >= 6:
        return "structural_complexity"
    if "responsibility_cohesion" in detectors:
        return "mixed_responsibilities"
    return "design_concern"


def _build_summary(
    concern_type: str,
    detectors: set[str],
    signals: ConcernSignals,
) -> str:
    """Human-readable one-liner."""
    if concern_type == "mixed_responsibilities":
        return (
            f"Issues from {len(detectors)} detectors — "
            "may have too many responsibilities"
        )
    if concern_type == "structural_complexity":
        parts: list[str] = []
        monster_loc = signals.get("monster_loc", 0)
        if monster_loc:
            funcs = signals.get("monster_funcs", [])
            label = f" ({', '.join(funcs[:3])})" if funcs else ""
            parts.append(f"monster function{label}: {int(monster_loc)} lines")
        nesting = signals.get("max_nesting", 0)
        if nesting >= 6:
            parts.append(f"nesting depth {int(nesting)}")
        params = signals.get("max_params", 0)
        if params >= 8:
            parts.append(f"{int(params)} parameters")
        return f"Structural complexity: {', '.join(parts) or 'elevated signals'}"
    if concern_type == "duplication_design":
        return "Duplication pattern — assess if extraction is warranted"
    if concern_type == "coupling_design":
        return "Coupling pattern — assess if boundaries need adjustment"
    if concern_type == "interface_design":
        return f"Interface complexity: {int(signals.get('max_params', 0))} parameters"
    return f"Design signals from {', '.join(sorted(detectors))}"


def _build_evidence(
    issues: list[dict[str, Any]],
    signals: ConcernSignals,
) -> tuple[str, ...]:
    """Build evidence tuple from all issues and extracted signals."""
    evidence: list[str] = []

    detectors = sorted({f.get("detector", "") for f in issues})
    evidence.append(f"Flagged by: {', '.join(detectors)}")

    loc = signals.get("loc")
    if loc:
        evidence.append(f"File size: {int(loc)} lines")
    params = signals.get("max_params")
    if params and params >= 8:
        evidence.append(f"Max parameters: {int(params)}")
    nesting = signals.get("max_nesting")
    if nesting and nesting >= 6:
        evidence.append(f"Max nesting depth: {int(nesting)}")
    monster_loc = signals.get("monster_loc")
    if monster_loc:
        funcs = signals.get("monster_funcs", [])
        label = f" ({', '.join(funcs[:3])})" if funcs else ""
        evidence.append(f"Monster function{label}: {int(monster_loc)} lines")

    # Individual issue summaries — give LLM the full picture, capped.
    for f in issues[:10]:
        summary = f.get("summary", "")
        if summary:
            evidence.append(f"[{f.get('detector', '')}] {summary}")

    return tuple(evidence)


def _build_question(
    detectors: set[str], signals: ConcernSignals
) -> str:
    """Build targeted question from dominant signals."""
    parts: list[str] = []

    if len(detectors) >= 3:
        parts.append(
            f"This file has issues across {len(detectors)} dimensions "
            f"({', '.join(sorted(detectors))}). Is it trying to do too many "
            "things, or is this complexity inherent to its domain?"
        )

    funcs = signals.get("monster_funcs", [])
    if funcs:
        parts.append(
            f"What are the distinct responsibilities in {funcs[0]}()? "
            "Should it be decomposed into focused functions?"
        )

    if signals.get("max_params", 0) >= 8:
        parts.append(
            "Should the parameters be grouped into a config/context object? "
            "Which ones belong together?"
        )

    if signals.get("max_nesting", 0) >= 6:
        parts.append(
            "Can the nesting be reduced with early returns, guard clauses, "
            "or extraction into helper functions?"
        )

    if "dupes" in detectors or "boilerplate_duplication" in detectors:
        parts.append(
            "Is the duplication worth extracting into a shared utility, "
            "or is it intentional variation?"
        )

    if "coupling" in detectors:
        parts.append(
            "Is the coupling intentional or does it indicate a missing "
            "abstraction boundary?"
        )

    if "orphaned" in detectors:
        parts.append(
            "Is this file truly dead, or is it used via a non-import mechanism "
            "(dynamic import, CLI entry point, plugin)?"
        )

    if "responsibility_cohesion" in detectors:
        parts.append(
            "What are the distinct responsibilities? Should this module be "
            "split along those lines?"
        )

    if not parts:
        parts.append(
            "Review the flagged patterns — are they design problems that "
            "need addressing, or acceptable given the file's role?"
        )

    return " ".join(parts)


# ── Generators ───────────────────────────────────────────────────────


def _file_concerns(state: dict[str, Any], dismissals: dict[str, Any]) -> list[Concern]:
    """Per-file design concerns from aggregated mechanical signals.

    Flags a file if it has 2+ judgment-needed detectors OR a single
    detector with elevated signals (monster function, high params,
    deep nesting, duplication, coupling, mixed responsibilities).
    Bundles ALL issues for that file so the LLM sees the full picture.
    """
    by_file = _group_by_file(state)
    concerns: list[Concern] = []

    for file, all_issues in by_file.items():
        judgment = [
            f for f in all_issues
            if f.get("detector", "") in JUDGMENT_DETECTORS
        ]
        if not judgment:
            continue

        judgment_dets = {f.get("detector", "") for f in judgment}
        elevated = _has_elevated_signals(judgment)

        # Flag if 2+ judgment detectors OR 1 with elevated signals
        # OR 1 judgment detector + 2 mechanical issues from any detector.
        mechanical_count = len(all_issues)
        if len(judgment_dets) < 2 and not elevated:
            if not (len(judgment_dets) >= 1 and mechanical_count >= 3):
                continue

        signals = _extract_signals(judgment)
        concern_type = _classify(judgment_dets, signals)
        evidence = _build_evidence(judgment, signals)
        question = _build_question(judgment_dets, signals)
        summary = _build_summary(concern_type, judgment_dets, signals)

        all_ids = tuple(sorted(f.get("id", "") for f in judgment))
        fp_keys = tuple(sorted(judgment_dets))
        fp = _fingerprint(concern_type, file, fp_keys)

        if _is_dismissed(dismissals, fp, all_ids):
            continue

        concerns.append(
            Concern(
                type=concern_type,
                file=file,
                summary=summary,
                evidence=evidence,
                question=question,
                fingerprint=fp,
                source_issues=all_ids,
            )
        )

    return concerns


def _cross_file_patterns(state: dict[str, Any], dismissals: dict[str, Any]) -> list[Concern]:
    """Systemic patterns: same judgment detector combo across 3+ files.

    When multiple files share the same combination of detector types,
    that's likely a codebase-wide pattern rather than isolated issues.
    """
    by_file = _group_by_file(state)

    # Group files by their judgment detector profile.
    profile_to_files: dict[frozenset[str], list[str]] = defaultdict(list)
    for file, issues in by_file.items():
        dets = frozenset(
            f.get("detector", "") for f in issues
            if f.get("detector", "") in JUDGMENT_DETECTORS
        )
        if len(dets) >= 2:
            profile_to_files[dets].append(file)

    concerns: list[Concern] = []
    for det_combo, files in profile_to_files.items():
        if len(files) < 3:
            continue

        sorted_files = sorted(files)
        combo_names = tuple(sorted(det_combo))
        all_ids = tuple(sorted(
            f.get("id", "")
            for file in sorted_files
            for f in by_file[file]
            if f.get("detector", "") in det_combo
        ))
        # Use first few files in fingerprint so it's stable but bounded.
        fp = _fingerprint(
            "systemic_pattern",
            ",".join(sorted_files[:5]),
            combo_names,
        )

        if _is_dismissed(dismissals, fp, all_ids):
            continue

        concerns.append(
            Concern(
                type="systemic_pattern",
                file=sorted_files[0],
                summary=(
                    f"{len(files)} files share the same problem pattern "
                    f"({', '.join(combo_names)})"
                ),
                evidence=(
                    f"Affected files: {', '.join(sorted_files[:10])}",
                    f"Shared detectors: {', '.join(combo_names)}",
                    f"Total files: {len(files)}",
                ),
                question=(
                    f"These {len(files)} files all have the same combination "
                    f"of issues ({', '.join(combo_names)}). Is this a systemic "
                    "pattern that should be addressed at the architecture level "
                    "(shared base class, framework change, lint rule), or are "
                    "these independent issues that happen to look similar?"
                ),
                fingerprint=fp,
                source_issues=all_ids,
            )
        )

    return concerns


def _systemic_smell_patterns(
    state: dict[str, Any], dismissals: dict[str, Any]
) -> list[Concern]:
    """Systemic concerns: single smell_id appearing across 5+ files.

    Complements _cross_file_patterns which looks at detector-combo profiles.
    This catches pervasive single-smell issues (e.g. broad_except in 12 files).
    """
    smell_files: dict[str, list[str]] = defaultdict(list)
    smell_ids_map: dict[str, list[str]] = defaultdict(list)  # smell_id -> issue IDs

    for f in _open_issues(state):
        if f.get("detector") != "smells":
            continue
        detail = f.get("detail", {})
        smell_id = detail.get("smell_id", "") if isinstance(detail, dict) else ""
        filepath = f.get("file", "")
        if smell_id and filepath and filepath != ".":
            smell_files[smell_id].append(filepath)
            smell_ids_map[smell_id].append(f.get("id", ""))

    concerns: list[Concern] = []
    for smell_id, files in smell_files.items():
        unique_files = sorted(set(files))
        if len(unique_files) < 5:
            continue

        all_ids = tuple(sorted(smell_ids_map[smell_id]))
        fp = _fingerprint("systemic_smell", smell_id, (smell_id,))
        if _is_dismissed(dismissals, fp, all_ids):
            continue

        concerns.append(
            Concern(
                type="systemic_smell",
                file=unique_files[0],
                summary=(
                    f"'{smell_id}' appears in {len(unique_files)} files — "
                    "likely a systemic pattern"
                ),
                evidence=(
                    f"Smell: {smell_id}",
                    f"Affected files ({len(unique_files)}): {', '.join(unique_files[:10])}",
                ),
                question=(
                    f"The smell '{smell_id}' appears across {len(unique_files)} files. "
                    "Is this a codebase-wide convention that should be addressed "
                    "systemically (lint rule, shared utility, architecture change), "
                    "or are these independent occurrences?"
                ),
                fingerprint=fp,
                source_issues=all_ids,
            )
        )

    return concerns


_GENERATORS = [_file_concerns, _cross_file_patterns, _systemic_smell_patterns]


def generate_concerns(
    state: dict[str, Any],
    lang_name: str | None = None,
) -> list[Concern]:
    """Run all concern generators against current state.

    Returns deduplicated list sorted by (type, file).
    lang_name is reserved for future language-specific generators.
    """
    del lang_name  # Reserved for future use.
    dismissals = state.get("concern_dismissals", {})
    concerns: list[Concern] = []
    seen_fps: set[str] = set()

    for gen in _GENERATORS:
        for concern in gen(state, dismissals):
            if concern.fingerprint not in seen_fps:
                seen_fps.add(concern.fingerprint)
                concerns.append(concern)

    concerns.sort(key=lambda c: (c.type, c.file))
    return concerns


def cleanup_stale_dismissals(state: dict[str, Any]) -> int:
    """Remove dismissals whose source issues all disappeared.

    Returns the number of stale entries removed.  Dismissals without
    ``source_issue_ids`` (legacy) are left untouched.
    """
    dismissals = state.get("concern_dismissals", {})
    if not dismissals:
        return 0
    open_ids = {f.get("id", "") for f in _open_issues(state)}
    stale_fps = [
        fp
        for fp, entry in dismissals.items()
        if entry.get("source_issue_ids")
        and not any(sid in open_ids for sid in entry["source_issue_ids"])
    ]
    for fp in stale_fps:
        del dismissals[fp]
    return len(stale_fps)


__all__ = ["Concern", "cleanup_stale_dismissals", "generate_concerns"]
