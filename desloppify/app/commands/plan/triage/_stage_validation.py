"""Validation and guardrail helpers for triage stage workflow."""

from __future__ import annotations

import argparse

from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.app.commands.plan.triage_playbook import TRIAGE_CMD_ORGANIZE
from desloppify.base.output.terminal import colorize
from desloppify.engine.plan import collect_triage_input, detect_recurring_patterns, save_plan
from desloppify.state import utc_now

from .confirmations import _MIN_ATTESTATION_LEN, _validate_attestation
from .helpers import manual_clusters_with_issues, observe_dimension_breakdown
from .stage_helpers import unclustered_review_issues, unenriched_clusters
from ._stage_validation_completion_policy import _completion_clusters_valid
from ._stage_validation_completion_policy import _completion_strategy_valid
from ._stage_validation_completion_policy import _confirm_existing_stages_valid
from ._stage_validation_completion_policy import _confirm_note_valid
from ._stage_validation_completion_policy import _confirm_strategy_valid
from ._stage_validation_completion_policy import _confirmed_text_or_error
from ._stage_validation_completion_policy import _note_cites_new_issues_or_error
from ._stage_validation_completion_policy import _require_prior_strategy_for_confirm
from ._stage_validation_completion_policy import _resolve_completion_strategy
from ._stage_validation_completion_policy import _resolve_confirm_existing_strategy
from ._stage_validation_completion_stages import _auto_confirm_enrich_for_complete
from ._stage_validation_completion_stages import _auto_confirm_organize_for_complete
from ._stage_validation_completion_stages import _auto_confirm_sense_check_for_complete
from ._stage_validation_completion_stages import _require_enrich_stage_for_complete
from ._stage_validation_completion_stages import _require_organize_stage_for_complete
from ._stage_validation_completion_stages import _require_sense_check_stage_for_complete
from ._stage_validation_enrich_checks import _cluster_file_overlaps
from ._stage_validation_enrich_checks import _clusters_with_directory_scatter
from ._stage_validation_enrich_checks import _clusters_with_high_step_ratio
from ._stage_validation_enrich_checks import _enrich_report_or_error
from ._stage_validation_enrich_checks import _require_organize_stage_for_enrich
from ._stage_validation_enrich_checks import _steps_missing_issue_refs
from ._stage_validation_enrich_checks import _steps_referencing_skipped_issues
from ._stage_validation_enrich_checks import _steps_with_bad_paths
from ._stage_validation_enrich_checks import _steps_with_vague_detail
from ._stage_validation_enrich_checks import _steps_without_effort
from ._stage_validation_enrich_checks import _underspecified_steps


def _auto_confirm_stage(
    *,
    plan: dict,
    stage_record: dict,
    stage_name: str,
    stage_label: str,
    attestation: str | None,
    blocked_heading: str,
    confirm_cmd: str,
    inline_hint: str,
    dimensions: list[str] | None = None,
    cluster_names: list[str] | None = None,
    save_plan_fn=None,
) -> bool:
    """Shared auto-confirm flow for stage fold-confirm operations."""
    if save_plan_fn is None:
        save_plan_fn = save_plan
    if stage_record.get("confirmed_at"):
        return True
    if not attestation or len(attestation.strip()) < _MIN_ATTESTATION_LEN:
        print(colorize(f"  {blocked_heading}", "red"))
        print(colorize(f"  Run: {confirm_cmd}", "dim"))
        print(colorize(f"  {inline_hint}", "dim"))
        return False

    confirmed_text = attestation.strip()
    validation_err = _validate_attestation(
        confirmed_text,
        stage_name,
        dimensions=dimensions,
        cluster_names=cluster_names,
    )
    if validation_err:
        print(colorize(f"  {validation_err}", "red"))
        return False

    stage_record["confirmed_at"] = utc_now()
    stage_record["confirmed_text"] = confirmed_text
    save_plan_fn(plan)
    print(colorize(f"  ✓ {stage_label} auto-confirmed via --attestation.", "green"))
    return True


def _auto_confirm_observe_if_attested(
    *,
    plan: dict,
    stages: dict,
    attestation: str | None,
    triage_input,
    save_plan_fn=None,
) -> bool:
    observe_stage = stages.get("observe")
    if observe_stage is None:
        return False
    _by_dim, dim_names = observe_dimension_breakdown(triage_input)
    return _auto_confirm_stage(
        plan=plan,
        stage_record=observe_stage,
        stage_name="observe",
        stage_label="Observe",
        attestation=attestation,
        blocked_heading="Cannot reflect: observe stage not confirmed.",
        confirm_cmd="desloppify plan triage --confirm observe",
        inline_hint="Or pass --attestation to auto-confirm observe inline.",
        dimensions=dim_names,
        save_plan_fn=save_plan_fn,
    )


def _validate_recurring_dimension_mentions(
    *,
    report: str,
    recurring_dims: list[str],
    recurring: dict,
) -> bool:
    if not recurring_dims:
        return True
    report_lower = report.lower()
    mentioned = [dim for dim in recurring_dims if dim.lower() in report_lower]
    if mentioned:
        return True
    print(colorize("  Recurring patterns detected but not addressed in report:", "red"))
    for dim in recurring_dims:
        info = recurring[dim]
        print(
            colorize(
                f"    {dim}: {len(info['resolved'])} resolved, "
                f"{len(info['open'])} still open — potential loop",
                "yellow",
            )
        )
    print(colorize("  Your report must mention at least one recurring dimension name.", "dim"))
    return False


def _require_reflect_stage_for_organize(stages: dict) -> bool:
    if "reflect" in stages:
        return True
    if "observe" not in stages:
        print(colorize("  Cannot organize: observe stage not complete.", "red"))
        print(colorize('  Run: desloppify plan triage --stage observe --report "..."', "dim"))
        return False
    print(colorize("  Cannot organize: reflect stage not complete.", "red"))
    print(colorize('  Run: desloppify plan triage --stage reflect --report "..."', "dim"))
    return False


def _auto_confirm_reflect_for_organize(
    *,
    args: argparse.Namespace,
    plan: dict,
    stages: dict,
    attestation: str | None,
    triage_input=None,
    command_runtime_fn=None,
    collect_triage_input_fn=collect_triage_input,
    detect_recurring_patterns_fn=detect_recurring_patterns,
    save_plan_fn=None,
) -> bool:
    reflect_stage = stages.get("reflect")
    if reflect_stage is None:
        return False

    resolved_triage_input = triage_input
    if resolved_triage_input is None:
        runtime_factory = command_runtime_fn or command_runtime
        runtime = runtime_factory(args)
        resolved_triage_input = collect_triage_input_fn(plan, runtime.state)

    recurring = detect_recurring_patterns_fn(
        resolved_triage_input.open_issues,
        resolved_triage_input.resolved_issues,
    )
    _by_dim, observe_dims = observe_dimension_breakdown(resolved_triage_input)
    reflect_dims = sorted(set((list(recurring.keys()) if recurring else []) + observe_dims))
    reflect_clusters = [name for name in plan.get("clusters", {}) if not plan["clusters"][name].get("auto")]
    return _auto_confirm_stage(
        plan=plan,
        stage_record=reflect_stage,
        stage_name="reflect",
        stage_label="Reflect",
        attestation=attestation,
        blocked_heading="Cannot organize: reflect stage not confirmed.",
        confirm_cmd="desloppify plan triage --confirm reflect",
        inline_hint="Or pass --attestation to auto-confirm reflect inline.",
        dimensions=reflect_dims,
        cluster_names=reflect_clusters,
        save_plan_fn=save_plan_fn,
    )


def _manual_clusters_or_error(plan: dict) -> list[str] | None:
    manual_clusters = manual_clusters_with_issues(plan)
    if manual_clusters:
        return manual_clusters
    any_clusters = [name for name, cluster in plan.get("clusters", {}).items() if cluster.get("issue_ids")]
    if any_clusters:
        print(colorize("  Cannot organize: only auto-clusters exist.", "red"))
        print(colorize("  Create manual clusters that group issues by root cause:", "dim"))
    else:
        print(colorize("  Cannot organize: no clusters with issues exist.", "red"))
    print(colorize('    desloppify plan cluster create <name> --description "..."', "dim"))
    print(colorize("    desloppify plan cluster add <name> <issue-patterns>", "dim"))
    return None


def _clusters_enriched_or_error(plan: dict) -> bool:
    gaps = unenriched_clusters(plan)
    if not gaps:
        return True
    print(colorize(f"  Cannot organize: {len(gaps)} cluster(s) need enrichment.", "red"))
    for name, missing in gaps:
        print(colorize(f"    {name}: missing {', '.join(missing)}", "yellow"))
    print()
    print(colorize("  Each cluster needs a description and action steps:", "dim"))
    print(colorize('    desloppify plan cluster update <name> --description "what this cluster addresses" --steps "step 1" "step 2"', "dim"))
    return False


def _unclustered_review_issues_or_error(plan: dict, state: dict) -> bool:
    """Block if open review issues aren't in any manual cluster. Return True if OK."""
    unclustered = unclustered_review_issues(plan, state)
    if not unclustered:
        return True
    print(colorize(f"  Cannot organize: {len(unclustered)} review issue(s) have no cluster.", "red"))
    for fid in unclustered[:10]:
        short = fid.rsplit("::", 2)[-2] if "::" in fid else fid
        print(colorize(f"    {short}", "yellow"))
    if len(unclustered) > 10:
        print(colorize(f"    ... and {len(unclustered) - 10} more", "yellow"))
    print()
    print(colorize("  Every review issue needs an action plan. Either:", "dim"))
    print(colorize("    1. Add to a cluster: desloppify plan cluster add <name> <pattern>", "dim"))
    print(colorize('    2. Wontfix it: desloppify plan skip --permanent <pattern> --note "reason" --attest "..."', "dim"))
    return False


def _organize_report_or_error(report: str | None) -> str | None:
    if not report:
        print(colorize("  --report is required for --stage organize.", "red"))
        print(colorize("  Summarize your prioritized organization:", "dim"))
        print(colorize("  - Did you defer contradictory issues before clustering?", "dim"))
        print(colorize("  - What clusters did you create and why?", "dim"))
        print(colorize("  - Explicit priority ordering: which cluster 1st, 2nd, 3rd and why?", "dim"))
        print(colorize("  - What depends on what? What unblocks the most?", "dim"))
        return None
    if len(report) < 100:
        print(colorize(f"  Report too short: {len(report)} chars (minimum 100).", "red"))
        print(colorize("  Explain what you organized, your priorities, and focus order.", "dim"))
        return None
    return report


__all__ = [
    "_auto_confirm_enrich_for_complete",
    "_auto_confirm_observe_if_attested",
    "_auto_confirm_organize_for_complete",
    "_auto_confirm_reflect_for_organize",
    "_cluster_file_overlaps",
    "_clusters_with_directory_scatter",
    "_clusters_with_high_step_ratio",
    "_clusters_enriched_or_error",
    "_enrich_report_or_error",
    "_unclustered_review_issues_or_error",
    "_completion_clusters_valid",
    "_completion_strategy_valid",
    "_confirm_existing_stages_valid",
    "_confirm_note_valid",
    "_confirm_strategy_valid",
    "_confirmed_text_or_error",
    "_manual_clusters_or_error",
    "_note_cites_new_issues_or_error",
    "_organize_report_or_error",
    "_require_enrich_stage_for_complete",
    "_require_organize_stage_for_complete",
    "_require_organize_stage_for_enrich",
    "_require_prior_strategy_for_confirm",
    "_require_reflect_stage_for_organize",
    "_require_sense_check_stage_for_complete",
    "_resolve_completion_strategy",
    "_resolve_confirm_existing_strategy",
    "_underspecified_steps",
    "_steps_missing_issue_refs",
    "_steps_referencing_skipped_issues",
    "_steps_with_bad_paths",
    "_steps_with_vague_detail",
    "_steps_without_effort",
    "_validate_recurring_dimension_mentions",
]
