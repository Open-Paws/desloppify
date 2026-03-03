"""Prompt template helpers for holistic review batch subagents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from desloppify.intelligence.review.feedback_contract import (
    DIMENSION_NOTE_ISSUES_KEY,
    HIGH_SCORE_ISSUES_NOTE_THRESHOLD,
    LOW_SCORE_ISSUE_THRESHOLD,
    max_batch_issues_for_dimension_count,
)


@dataclass(frozen=True)
class _PromptBatchContext:
    name: str
    dimensions: tuple[str, ...]
    rationale: str
    seed_files: tuple[str, ...]
    issues_cap: int

    @property
    def dimension_set(self) -> set[str]:
        return set(self.dimensions)

    @property
    def dimensions_text(self) -> str:
        return ", ".join(self.dimensions) if self.dimensions else "(none)"

    @property
    def seed_files_text(self) -> str:
        return "\n".join(f"- {path}" for path in self.seed_files) if self.seed_files else "- (none)"


def _coerce_string_list(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list | tuple):
        return ()
    return tuple(str(item) for item in raw if isinstance(item, str) and item)


def _build_context(batch: dict[str, object], batch_index: int) -> _PromptBatchContext:
    dimensions = _coerce_string_list(batch.get("dimensions", []))
    return _PromptBatchContext(
        name=str(batch.get("name", f"Batch {batch_index + 1}")),
        dimensions=dimensions,
        rationale=str(batch.get("why", "")).strip(),
        seed_files=_coerce_string_list(batch.get("files_to_read", [])),
        issues_cap=max_batch_issues_for_dimension_count(len(dimensions)),
    )


_SCAN_EVIDENCE_FOCUS_BY_DIMENSION = {
    "initialization_coupling": (
        "9e. For initialization_coupling, use evidence from "
        "`holistic_context.scan_evidence.mutable_globals` and "
        "`holistic_context.errors.mutable_globals`. Investigate initialization ordering "
        "dependencies, coupling through shared mutable state, and whether state should "
        "be encapsulated behind a proper registry/context manager.\n"
    ),
    "design_coherence": (
        "9f. For design_coherence, use evidence from "
        "`holistic_context.scan_evidence.signal_density` — files where "
        "multiple mechanical detectors fired. Investigate what design change would address "
        "multiple signals simultaneously. Check `scan_evidence.complexity_hotspots` for "
        "files with high responsibility cluster counts.\n"
    ),
    "error_consistency": (
        "9g. For error_consistency, use evidence from "
        "`holistic_context.errors.exception_hotspots` — files with "
        "concentrated exception handling issues. Investigate whether error handling is "
        "designed or accidental. Check for broad catches masking specific failure modes.\n"
    ),
    "cross_module_architecture": (
        "9h. For cross_module_architecture, also consult "
        "`holistic_context.coupling.boundary_violations` for import paths that "
        "cross architectural boundaries, and `holistic_context.dependencies.deferred_import_density` "
        "for files with many function-level imports (proxy for cycle pressure).\n"
    ),
    "convention_outlier": (
        "9i. For convention_outlier, also consult "
        "`holistic_context.conventions.duplicate_clusters` for cross-file "
        "function duplication and `conventions.naming_drift` for directory-level naming "
        "inconsistency.\n"
    ),
}


def _render_scan_evidence_focus(dim_set: set[str]) -> str:
    """Render dimension-specific scan_evidence guidance."""
    return "".join(
        text
        for dim, text in _SCAN_EVIDENCE_FOCUS_BY_DIMENSION.items()
        if dim in dim_set
    )


def _render_historical_focus(batch: dict[str, object]) -> str:
    focus = batch.get("historical_issue_focus")
    if not isinstance(focus, dict):
        return ""

    selected_raw = focus.get("selected_count", 0)
    try:
        selected_count = max(0, int(selected_raw))
    except (TypeError, ValueError):
        selected_count = 0

    issues = focus.get("issues", [])
    if not isinstance(issues, list):
        issues = []

    if selected_count <= 0 or not issues:
        return ""

    lines: list[str] = []
    lines.append(
        "Previously flagged issues (from past reviews of these dimensions):"
    )
    lines.append(
        "Check whether each issue still exists in the current code. Do not re-report"
        " issues that have been fixed or marked wontfix — focus on what remains or"
        " what is new. If several past issues share a root cause, call that out."
    )

    for entry in issues:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status", "")).strip()
        summary = str(entry.get("summary", "")).strip()
        note = str(entry.get("note", "")).strip()

        line = f"  - [{status}] {summary}"
        if note:
            line += f" (note: {note})"
        lines.append(line)
    return "\n".join(lines) + "\n\n"


def _render_mechanical_concern_signals(batch: dict[str, object]) -> str:
    """Render mechanically-generated concern hypotheses for this batch."""
    signals = batch.get("concern_signals")
    if not isinstance(signals, list) or not signals:
        return ""

    lines: list[str] = []
    lines.append("Mechanical concern signals (detector synthesis hypotheses):")
    lines.append(
        "Treat each as a hypothesis: confirm or refute with direct code evidence."
    )

    shown = 0
    for entry in signals:
        if not isinstance(entry, dict):
            continue
        file = str(entry.get("file", "")).strip() or "(unknown file)"
        concern_type = str(entry.get("type", "")).strip() or "design_concern"
        summary = str(entry.get("summary", "")).strip()
        question = str(entry.get("question", "")).strip()
        evidence_raw = entry.get("evidence", [])
        evidence = (
            [str(item).strip() for item in evidence_raw if isinstance(item, str) and item.strip()]
            if isinstance(evidence_raw, list)
            else []
        )

        lines.append(f"  - [{concern_type}] {file}")
        if summary:
            lines.append(f"    summary: {summary}")
        if question:
            lines.append(f"    question: {question}")
        for snippet in evidence[:2]:
            lines.append(f"    evidence: {snippet}")
        shown += 1
        if shown >= 8:
            break

    extra = max(0, len(signals) - shown)
    if extra:
        lines.append(f"  - (+{extra} more concern signals)")
    return "\n".join(lines) + "\n\n"


def _render_workflow_integrity_focus(dim_set: set[str]) -> str:
    """Render workflow integrity checks for architecture/integration dimensions."""
    if not dim_set.intersection(
        {
            "cross_module_architecture",
            "high_level_elegance",
            "mid_level_elegance",
            "design_coherence",
            "initialization_coupling",
        }
    ):
        return ""
    return (
        "9j. Workflow integrity checks: when reviewing orchestration/queue/review flows,\n"
        "    explicitly look for loop-prone patterns and blind spots:\n"
        "    - repeated stale/reopen churn without clear exit criteria or gating,\n"
        "    - packet/batch data being generated but dropped before prompt execution,\n"
        "    - ranking/triage logic that can starve target-improving work,\n"
        "    - reruns happening before existing open review work is drained.\n"
        "    If found, propose concrete guardrails and where to implement them.\n"
    )


def _render_package_org_focus(dim_set: set[str]) -> str:
    if "package_organization" not in dim_set:
        return ""
    return (
        "9a. For package_organization, ground scoring in objective structure signals from "
        "`holistic_context.structure` (root_files fan_in/fan_out roles, directory_profiles, "
        "coupling_matrix). Prefer thresholded evidence (for example: fan_in < 5 for root "
        "stragglers, import-affinity > 60%, directories > 10 files with mixed concerns).\n"
        "9b. Suggestions must include a staged reorg plan (target folders, move order, "
        "and import-update/validation commands).\n"
        "9c. Also consult `holistic_context.structure.flat_dir_issues` for directories "
        "flagged as overloaded, fragmented, or thin-wrapper patterns.\n"
    )


def _render_abstraction_focus(dim_set: set[str]) -> str:
    if "abstraction_fitness" not in dim_set:
        return ""
    return (
        "9d. For abstraction_fitness, use evidence from `holistic_context.abstractions`:\n"
        "  - `delegation_heavy_classes`: classes where most methods forward to an inner "
        "object — entries include class_name, delegate_target, sample_methods, and line number.\n"
        "  - `facade_modules`: re-export-only modules with high re_export_ratio — entries "
        "include samples (re-exported names) and loc.\n"
        "  - `typed_dict_violations`: TypedDict fields accessed via .get()/.setdefault()/.pop() "
        "— entries include typed_dict_name, violation_type, field, and line number.\n"
        "  - `complexity_hotspots`: files where mechanical analysis found extreme parameter "
        "counts, deep nesting, or disconnected responsibility clusters.\n"
        "  Include `delegation_density`, `definition_directness`, and `type_discipline` "
        "alongside existing sub-axes in dimension_notes when evidence supports it.\n"
    )


def _render_dimension_focus(context: _PromptBatchContext) -> str:
    dim_set = context.dimension_set
    return (
        _render_package_org_focus(dim_set)
        + _render_abstraction_focus(dim_set)
        + _render_scan_evidence_focus(dim_set)
        + _render_workflow_integrity_focus(dim_set)
    )


def _render_metadata_block(
    *,
    repo_root: Path,
    packet_path: Path,
    batch_index: int,
    context: _PromptBatchContext,
) -> str:
    return (
        "You are a focused subagent reviewer for a single holistic investigation batch.\n\n"
        f"Repository root: {repo_root}\n"
        f"Blind packet: {packet_path}\n"
        f"Batch index: {batch_index + 1}\n"
        f"Batch name: {context.name}\n"
        f"Batch dimensions: {context.dimensions_text}\n"
        f"Batch rationale: {context.rationale}\n\n"
    )


def _render_scan_evidence_note() -> str:
    return (
        "Mechanical scan evidence: The blind packet contains `holistic_context.scan_evidence` "
        "with aggregated signals from all mechanical detectors — including complexity hotspots, "
        "error hotspots, signal density index (files flagged by multiple detectors), boundary "
        "violations, and systemic patterns. Consult this section for investigative leads beyond "
        "the seed files.\n\n"
    )


def _render_seed_files_block(context: _PromptBatchContext) -> str:
    return f"Seed files (start here):\n{context.seed_files_text}\n\n"


def _render_task_requirements(context: _PromptBatchContext) -> str:
    return (
        "Task requirements:\n"
        "1. Read the blind packet and follow `system_prompt` constraints exactly.\n"
        "1a. If previously flagged issues are listed above, use them as context for your review.\n"
        "    Verify whether each still applies to the current code. Do not re-report fixed or\n"
        "    wontfix issues. Use them as starting points to look deeper — inspect adjacent code\n"
        "    and related modules for defects the prior review may have missed.\n"
        "1b. If mechanical concern signals are listed above, explicitly confirm or refute them.\n"
        "    Report confirmed defects under the most impacted batch dimension.\n"
        "    If refuting, include clear counter-evidence in `dimension_notes`.\n"
        "1c. Think structurally: when you spot multiple individual issues that share a common\n"
        "    root cause (missing abstraction, duplicated pattern, inconsistent convention),\n"
        "    explain the deeper structural issue in the issue, not just the surface symptom.\n"
        "    If the pattern is significant enough, report the structural issue as its own issue\n"
        "    with appropriate fix_scope ('multi_file_refactor' or 'architectural_change') and\n"
        "    use `root_cause_cluster` to connect related symptom issues together.\n"
        "2. Start with the seed files, then freely explore additional repository files likely to surface material issues.\n"
        "2a. Prioritize high-signal leads: unexplored/lightly reviewed files, historical issue areas, and hotspot neighbors "
        "(high coupling, god modules, large files, churn seams).\n"
        "2b. Keep exploration targeted — follow strongest evidence paths first instead of attempting exhaustive coverage.\n"
        "2c. Keep issues and scoring scoped to this batch's listed dimensions.\n"
        "2d. Respect scope controls in the blind packet config: do not include files/directories marked by "
        "`exclude`, `suppress`, or zone overrides that classify files as non-production (test/config/generated/vendor).\n"
        f"3. Return 0-{context.issues_cap} high-quality issues for this batch (empty array allowed).\n"
        "3a. Do not suppress real defects to keep scores high; report every material issue you can support with evidence.\n"
        "3b. Do not default to 100. Reserve 100 for genuinely exemplary evidence in this batch.\n"
        "4. Score/issue consistency is required: broader or more severe issues MUST lower dimension scores.\n"
        f"4a. Any dimension scored below {LOW_SCORE_ISSUE_THRESHOLD:.1f} MUST include explicit feedback: add at least one "
        "issue with the same `dimension` and a non-empty actionable `suggestion`.\n"
        "5. Every issue must include `related_files` with at least 2 files when possible.\n"
        "6. Every issue must include `dimension`, `identifier`, `summary`, `evidence`, `suggestion`, and `confidence`.\n"
        "7. Every issue must include `impact_scope` and `fix_scope`.\n"
        "8. Every scored dimension MUST include dimension_notes with concrete evidence.\n"
        f"9. If a dimension score is >{HIGH_SCORE_ISSUES_NOTE_THRESHOLD:.1f}, include `{DIMENSION_NOTE_ISSUES_KEY}` in dimension_notes.\n"
        "10. Use exactly one decimal place for every assessment and abstraction sub-axis score.\n"
        f"{_render_dimension_focus(context)}"
        "11. Ignore prior chat context and any target-threshold assumptions.\n"
        "12. Do not edit repository files.\n"
        "13. Return ONLY valid JSON, no markdown fences.\n\n"
    )


def _render_scope_enums() -> str:
    return (
        "Scope enums:\n"
        '- impact_scope: "local" | "module" | "subsystem" | "codebase"\n'
        '- fix_scope: "single_edit" | "multi_file_refactor" | "architectural_change"\n\n'
    )


def _render_output_schema(context: _PromptBatchContext, batch_index: int) -> str:
    return (
        "Output schema:\n"
        "{\n"
        f'  "batch": "{context.name}",\n'
        f'  "batch_index": {batch_index + 1},\n'
        '  "assessments": {"<dimension>": <0-100 with one decimal place>},\n'
        '  "dimension_notes": {\n'
        '    "<dimension>": {\n'
        '      "evidence": ["specific code observations"],\n'
        '      "impact_scope": "local|module|subsystem|codebase",\n'
        '      "fix_scope": "single_edit|multi_file_refactor|architectural_change",\n'
        '      "confidence": "high|medium|low",\n'
        f'      "{DIMENSION_NOTE_ISSUES_KEY}": "required when score >{HIGH_SCORE_ISSUES_NOTE_THRESHOLD:.1f}",\n'
        '      "sub_axes": {"abstraction_leverage": 0-100, "indirection_cost": 0-100, "interface_honesty": 0-100, "delegation_density": 0-100, "definition_directness": 0-100, "type_discipline": 0-100}  // required for abstraction_fitness when evidence supports it; all one decimal place\n'
        "    }\n"
        "  },\n"
        '  "issues": [{\n'
        '    "dimension": "<dimension>",\n'
        '    "identifier": "short_id",\n'
        '    "summary": "one-line defect summary",\n'
        '    "related_files": ["relative/path.py"],\n'
        '    "evidence": ["specific code observation"],\n'
        '    "suggestion": "concrete fix recommendation",\n'
        '    "confidence": "high|medium|low",\n'
        '    "impact_scope": "local|module|subsystem|codebase",\n'
        '    "fix_scope": "single_edit|multi_file_refactor|architectural_change",\n'
        '    "root_cause_cluster": "optional_cluster_name_when_supported_by_history"\n'
        "  }],\n"
        '  "retrospective": {\n'
        '    "root_causes": ["optional: concise root-cause hypotheses"],\n'
        '    "likely_symptoms": ["optional: identifiers that look symptom-level"],\n'
        '    "possible_false_positives": ["optional: prior concept keys likely mis-scoped"]\n'
        "  }\n"
        "}\n"
    )


def _join_non_empty_sections(*sections: str) -> str:
    return "".join(section for section in sections if section)


def render_batch_prompt(
    *,
    repo_root: Path,
    packet_path: Path,
    batch_index: int,
    batch: dict[str, object],
) -> str:
    """Render one subagent prompt for a holistic investigation batch."""
    context = _build_context(batch, batch_index)
    return _join_non_empty_sections(
        _render_metadata_block(
            repo_root=repo_root,
            packet_path=packet_path,
            batch_index=batch_index,
            context=context,
        ),
        _render_scan_evidence_note(),
        _render_seed_files_block(context),
        _render_historical_focus(batch),
        _render_mechanical_concern_signals(batch),
        _render_task_requirements(context),
        _render_scope_enums(),
        _render_output_schema(context, batch_index),
    )


__all__ = ["render_batch_prompt"]
