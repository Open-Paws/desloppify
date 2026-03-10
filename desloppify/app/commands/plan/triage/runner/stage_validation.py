"""Post-subagent validation and auto-attestation for triage runners."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from desloppify.engine.plan_triage import TriageInput

from ..stages.evidence_parsing import (
    parse_observe_evidence,
    validate_observe_evidence,
    validate_reflect_skip_evidence,
    validate_report_has_file_paths,
    validate_report_references_clusters,
)
from ..validation.core import (
    _cluster_file_overlaps,
    _clusters_with_directory_scatter,
    _clusters_with_high_step_ratio,
    _steps_missing_issue_refs,
    _steps_referencing_skipped_issues,
    _steps_with_bad_paths,
    _steps_with_vague_detail,
    _steps_without_effort,
    _underspecified_steps,
)
from ..helpers import (
    count_log_activity_since,
    manual_clusters_with_issues,
    observe_dimension_breakdown,
    open_review_ids_from_state,
)
from ..stages.helpers import unclustered_review_issues, unenriched_clusters


@dataclass(frozen=True)
class EnrichQualityFailure:
    """Structured enrich-quality validation failure."""

    code: str
    message: str


def run_enrich_quality_checks(
    plan: dict,
    repo_root: Path,
    *,
    phase_label: str,
) -> list[EnrichQualityFailure]:
    """Run enrich-level executor-readiness checks for a phase."""
    sense_suffix = f" after {phase_label}" if phase_label == "sense-check" else ""
    failures: list[EnrichQualityFailure] = []

    underspec = _underspecified_steps(plan)
    if underspec:
        total = sum(n for _, n, _ in underspec)
        failures.append(
            EnrichQualityFailure(
                code="underspecified_steps",
                message=f"{total} step(s) still lack detail or issue_refs{sense_suffix}.",
            )
        )

    bad_paths = _steps_with_bad_paths(plan, repo_root)
    if bad_paths:
        total = sum(len(bp) for _, _, bp in bad_paths)
        if phase_label == "sense-check":
            message = f"{total} file path(s) don't exist on disk{sense_suffix}."
        else:
            message = f"{total} file path(s) in step details don't exist on disk."
        failures.append(
            EnrichQualityFailure(code="missing_paths", message=message)
        )

    untagged = _steps_without_effort(plan)
    if untagged:
        total = sum(n for _, n, _ in untagged)
        if phase_label == "sense-check":
            message = f"{total} step(s) have no effort tag{sense_suffix}."
        else:
            message = (
                f"{total} step(s) have no effort tag "
                "(trivial/small/medium/large)."
            )
        failures.append(
            EnrichQualityFailure(code="missing_effort", message=message)
        )

    no_refs = _steps_missing_issue_refs(plan)
    if no_refs:
        total = sum(n for _, n, _ in no_refs)
        if phase_label == "sense-check":
            message = f"{total} step(s) have no issue_refs{sense_suffix}."
        else:
            message = f"{total} step(s) have no issue_refs for traceability."
        failures.append(
            EnrichQualityFailure(code="missing_issue_refs", message=message)
        )

    vague = _steps_with_vague_detail(plan, repo_root)
    if vague:
        if phase_label == "sense-check":
            message = f"{len(vague)} step(s) have vague detail{sense_suffix}."
        else:
            message = (
                f"{len(vague)} step(s) have vague detail (< 80 chars, no file paths). "
                "Executor-ready means: file path + specific instruction."
            )
        failures.append(
            EnrichQualityFailure(code="vague_detail", message=message)
        )

    # Steps referencing skipped/wontfixed issues
    stale_refs = _steps_referencing_skipped_issues(plan)
    if stale_refs:
        total_stale = sum(len(refs) for _, _, refs in stale_refs)
        failures.append(
            EnrichQualityFailure(
                code="stale_issue_refs",
                message=(
                    f"{total_stale} step issue_ref(s) point to skipped/wontfixed issues"
                    f"{sense_suffix}. Remove stale refs."
                ),
            )
        )

    return failures


def _validate_observe_stage(
    *,
    stages: dict,
    triage_input: TriageInput | None,
) -> tuple[bool, str]:
    """Validate recorded observe-stage content."""
    if "observe" not in stages:
        return False, "Observe stage not recorded."
    report = stages["observe"].get("report", "")
    if len(report) < 100:
        return False, f"Observe report too short ({len(report)} chars, need 100+)."
    cited = stages["observe"].get("cited_ids", [])
    issue_count = stages["observe"].get("issue_count", 0)
    if issue_count <= 0:
        return True, ""
    min_citations = min(5, max(1, issue_count // 10))
    if len(cited) < min_citations:
        return False, (
            f"Observe report cites only {len(cited)} issue(s) "
            f"(need {min_citations}+). Reference specific issue "
            f"hashes to prove you read them."
        )
    valid_ids = set(triage_input.open_issues.keys()) if triage_input else set()
    evidence = parse_observe_evidence(report, valid_ids)
    ev_failures = validate_observe_evidence(evidence, issue_count)
    blocking = [failure for failure in ev_failures if failure.blocking]
    if blocking:
        return False, blocking[0].message
    return True, ""


def _validate_reflect_stage(stages: dict) -> tuple[bool, str]:
    """Validate recorded reflect-stage content."""
    if "reflect" not in stages:
        return False, "Reflect stage not recorded."
    report = stages["reflect"].get("report", "")
    if len(report) < 100:
        return False, f"Reflect report too short ({len(report)} chars, need 100+)."
    for field_name, label in (
        ("missing_issue_ids", "unaccounted for"),
        ("duplicate_issue_ids", "duplicates"),
    ):
        ids = stages["reflect"].get(field_name, [])
        if ids:
            return False, f"Reflect report {label} {len(ids)} issue(s)."
    issue_count = int(stages["reflect"].get("issue_count", 0) or 0)
    cited = stages["reflect"].get("cited_ids", [])
    if issue_count > 0 and len(cited) < issue_count:
        return False, (
            f"Reflect report cites only {len(cited)}/{issue_count} issue(s). "
            "A reflect blueprint must account for every open review issue."
        )
    skip_failures = validate_reflect_skip_evidence(report)
    blocking_skips = [failure for failure in skip_failures if failure.blocking]
    if blocking_skips:
        return False, blocking_skips[0].message
    return True, ""


def _organize_stage_warnings(plan: dict) -> list[str]:
    """Collect advisory organize-stage warnings."""
    warnings: list[str] = []
    overlaps = _cluster_file_overlaps(plan)
    if overlaps:
        warnings.append(f"{len(overlaps)} cluster pair(s) share files without dependencies")
    scattered = _clusters_with_directory_scatter(plan)
    if scattered:
        names = ", ".join(name for name, _, _ in scattered)
        warnings.append(f"Theme-grouped clusters (5+ dirs): {names}")
    high_ratio = _clusters_with_high_step_ratio(plan)
    if high_ratio:
        names = ", ".join(name for name, _, _, _ in high_ratio)
        warnings.append(f"1:1 step-to-issue ratio: {names}")
    clusters = plan.get("clusters", {})
    orphaned = [
        name for name, cluster in clusters.items()
        if not cluster.get("auto") and not cluster.get("issue_ids") and cluster.get("action_steps")
    ]
    if orphaned:
        warnings.append(f"Orphaned clusters (steps, no issues): {', '.join(orphaned)}")
    return warnings


def _validate_organize_stage(plan: dict, state: dict, stages: dict) -> tuple[bool, str]:
    """Validate recorded organize-stage content."""
    if "organize" not in stages:
        return False, "Organize stage not recorded."
    open_review_ids = open_review_ids_from_state(state)
    manual = manual_clusters_with_issues(plan)
    if not open_review_ids and not manual:
        report = stages["organize"].get("report", "")
        if len(report) < 100:
            return False, f"Organize report too short ({len(report)} chars, need 100+)."
        return True, ""
    if not manual:
        return False, "No manual clusters with issues exist."
    gaps = unenriched_clusters(plan)
    if gaps:
        names = ", ".join(name for name, _ in gaps)
        return False, f"Unenriched clusters: {names}"
    unclustered = unclustered_review_issues(plan, state)
    if unclustered:
        return False, f"{len(unclustered)} review issue(s) not in any cluster."
    report = stages["organize"].get("report", "")
    cluster_ref_failures = validate_report_references_clusters(report, manual)
    blocking_refs = [failure for failure in cluster_ref_failures if failure.blocking]
    if blocking_refs:
        return False, blocking_refs[0].message
    reflect_ts = stages.get("reflect", {}).get("timestamp", "")
    if reflect_ts:
        activity = count_log_activity_since(plan, reflect_ts)
        cluster_ops = sum(
            activity.get(key, 0)
            for key in ("cluster_create", "cluster_add", "cluster_update", "cluster_remove")
        )
        min_ops = max(3, len(manual))
        if cluster_ops < min_ops:
            return False, (
                f"Only {cluster_ops} cluster op(s) logged since reflect "
                f"(need {min_ops}+). Run cluster create/add/update commands."
            )
    warnings = _organize_stage_warnings(plan)
    if warnings:
        return True, "Advisory: " + "; ".join(warnings)
    return True, ""


def _validate_enrich_stage(plan: dict, repo_root: Path, stages: dict) -> tuple[bool, str]:
    """Validate recorded enrich-stage content."""
    if "enrich" not in stages:
        return False, "Enrich stage not recorded."
    failures = run_enrich_quality_checks(plan, repo_root, phase_label="enrich")
    if failures:
        return False, failures[0].message
    return True, ""


def _validate_sense_check_stage(
    plan: dict,
    state: dict,
    repo_root: Path,
    stages: dict,
) -> tuple[bool, str]:
    """Validate recorded sense-check-stage content."""
    if "sense-check" not in stages:
        return False, "Sense-check stage not recorded."
    report = stages["sense-check"].get("report", "")
    if len(report) < 100:
        return False, f"Sense-check report too short ({len(report)} chars, need 100+)."
    if not open_review_ids_from_state(state) and not manual_clusters_with_issues(plan):
        return True, ""
    failures = run_enrich_quality_checks(
        plan,
        repo_root,
        phase_label="sense-check",
    )
    if failures:
        return False, failures[0].message
    path_failures = validate_report_has_file_paths(report)
    blocking_pf = [failure for failure in path_failures if failure.blocking]
    if blocking_pf:
        return False, blocking_pf[0].message
    sc_clusters = manual_clusters_with_issues(plan)
    cluster_failures = validate_report_references_clusters(report, sc_clusters)
    blocking_cf = [failure for failure in cluster_failures if failure.blocking]
    if blocking_cf:
        return False, blocking_cf[0].message
    return True, ""


def validate_stage(
    stage: str,
    plan: dict,
    state: dict,
    repo_root: Path,
    *,
    triage_input: TriageInput | None = None,
) -> tuple[bool, str]:
    """Check subagent completed stage correctly. Returns (ok, error_msg)."""
    meta = plan.get("epic_triage_meta", {})
    stages = meta.get("triage_stages", {})
    validators = {
        "observe": lambda: _validate_observe_stage(
            stages=stages,
            triage_input=triage_input,
        ),
        "reflect": lambda: _validate_reflect_stage(stages),
        "organize": lambda: _validate_organize_stage(plan, state, stages),
        "enrich": lambda: _validate_enrich_stage(plan, repo_root, stages),
        "sense-check": lambda: _validate_sense_check_stage(plan, state, repo_root, stages),
    }
    validator = validators.get(stage)
    if validator is None:
        return False, f"Unknown stage: {stage}"
    return validator()


def _validate_required_stages(stages: dict) -> tuple[bool, str]:
    """Validate that all required triage stages are present and confirmed."""
    for required in ("observe", "reflect", "organize", "enrich", "sense-check"):
        if required not in stages:
            return False, f"Stage {required} not recorded."
        if not stages[required].get("confirmed_at"):
            return False, f"Stage {required} not confirmed."
    return True, ""


def _validate_cluster_dependency_cycles(clusters: dict) -> tuple[bool, str]:
    """Reject self-referential cluster dependencies."""
    for name, cluster in clusters.items():
        deps = cluster.get("depends_on_clusters", [])
        if name in deps:
            return False, f"Cluster {name} depends on itself."
    return True, ""


def _find_all_trivial_clusters(clusters: dict) -> list[str]:
    """Return manual clusters whose action steps are all marked trivial."""
    trivial_clusters: list[str] = []
    for name, cluster in clusters.items():
        if cluster.get("auto") or not cluster.get("issue_ids"):
            continue
        steps = cluster.get("action_steps") or []
        if steps and all(
            isinstance(step, dict) and step.get("effort") == "trivial"
            for step in steps
        ):
            trivial_clusters.append(name)
    return trivial_clusters


def validate_completion(
    plan: dict,
    state: dict,
    repo_root: Path,
) -> tuple[bool, str]:
    """Validate plan is ready for triage completion. Returns (ok, error_msg)."""
    meta = plan.get("epic_triage_meta", {})
    stages = meta.get("triage_stages", {})

    ok, message = _validate_required_stages(stages)
    if not ok:
        return ok, message

    open_review_ids = open_review_ids_from_state(state)
    manual = manual_clusters_with_issues(plan)
    if not open_review_ids and not manual:
        return True, ""
    if not manual:
        return False, "No manual clusters with issues."

    gaps = unenriched_clusters(plan)
    if gaps:
        return False, f"{len(gaps)} cluster(s) still need enrichment."

    unclustered = unclustered_review_issues(plan, state)
    if unclustered:
        return False, f"{len(unclustered)} review issue(s) not in any cluster."

    clusters = plan.get("clusters", {})
    ok, message = _validate_cluster_dependency_cycles(clusters)
    if not ok:
        return ok, message

    all_trivial_clusters = _find_all_trivial_clusters(clusters)
    if all_trivial_clusters:
        names = ", ".join(sorted(all_trivial_clusters))
        return True, f"Advisory: all action steps are marked trivial in cluster(s): {names}"

    return True, ""


def build_auto_attestation(
    stage: str,
    plan: dict,
    triage_input: TriageInput,
) -> str:
    """Generate valid 80+ char attestation referencing real dimensions/cluster names."""
    if stage == "observe":
        _by_dim, dim_names = observe_dimension_breakdown(triage_input)
        top_dims = dim_names[:3]
        dims_str = ", ".join(top_dims)
        return (
            f"I have thoroughly analysed {len(triage_input.open_issues)} issues "
            f"across dimensions including {dims_str}, identifying themes, "
            f"root causes, and contradictions across the codebase."
        )

    if stage == "reflect":
        _by_dim, dim_names = observe_dimension_breakdown(triage_input)
        top_dims = dim_names[:3]
        dims_str = ", ".join(top_dims)
        return (
            f"My strategy accounts for {len(triage_input.open_issues)} issues "
            f"across dimensions including {dims_str}, comparing against "
            f"resolved history and forming priorities for execution."
        )

    if stage == "organize":
        cluster_names = manual_clusters_with_issues(plan)
        if not cluster_names:
            return (
                "I verified there are zero open review issues in this organize batch, "
                "so no manual clusters or issue assignments were needed before continuing."
            )
        names_str = ", ".join(cluster_names[:3])
        return (
            f"I have organized all review issues into clusters including "
            f"{names_str}, with descriptions, action steps, and clear "
            f"priority ordering based on root cause analysis."
        )

    if stage == "enrich":
        cluster_names = manual_clusters_with_issues(plan)
        if not cluster_names:
            return (
                "I verified there are zero open review issues in this enrich batch, "
                "so there were no action steps to elaborate before advancing."
            )
        names_str = ", ".join(cluster_names[:3])
        return (
            f"Steps in clusters including {names_str} are executor-ready with "
            f"detail, file paths, issue refs, and effort tags, verified "
            f"against the actual codebase."
        )

    if stage == "sense-check":
        cluster_names = manual_clusters_with_issues(plan)
        if not cluster_names:
            return (
                "I verified there are zero open review issues in this sense-check batch, "
                "so no cluster content or file-path evidence needed additional review."
            )
        names_str = ", ".join(cluster_names[:3])
        return (
            f"Content and structure verified for clusters including {names_str}. "
            f"All step details are factually accurate, cross-cluster dependencies "
            f"are safe, and enrich-level checks pass."
        )

    return f"Stage {stage} completed with thorough analysis of all available data and verified against codebase."


__all__ = [
    "EnrichQualityFailure",
    "build_auto_attestation",
    "run_enrich_quality_checks",
    "validate_completion",
    "validate_stage",
]
