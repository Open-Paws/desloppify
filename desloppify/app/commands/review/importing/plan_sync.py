"""Post-import plan sync for review importing."""

from __future__ import annotations

from pathlib import Path

import desloppify.engine.plan_queue as plan_queue_mod
from desloppify import state as state_mod
from desloppify.app.commands.helpers.display import short_issue_id
from desloppify.app.commands.review.importing.flags import imported_assessment_keys
from desloppify.base.config import target_strict_score_from_config
from desloppify.base.exception_sets import PLAN_LOAD_EXCEPTIONS
from desloppify.base.output.terminal import colorize
from desloppify.engine.plan_triage import (
    TRIAGE_CMD_RUN_STAGES_CLAUDE,
    TRIAGE_CMD_RUN_STAGES_CODEX,
)


def _has_postflight_review_work(state: dict, *, policy) -> bool:
    issues = state.get("issues", {})
    if any(
        isinstance(issue, dict)
        and issue.get("status") == "open"
        and issue.get("detector") in {"review", "concerns", "subjective_review"}
        for issue in issues.values()
    ):
        return True
    return bool(policy.stale_ids or policy.under_target_ids)


def _sync_lifecycle_phase_after_import(plan: dict, state: dict, *, policy) -> bool:
    return plan_queue_mod.sync_lifecycle_phase(
        plan,
        has_initial_reviews=bool(policy.unscored_ids),
        has_objective_backlog=bool(policy.has_objective_backlog),
        has_postflight_review=_has_postflight_review_work(state, policy=policy),
        has_postflight_workflow=any(
            item_id in plan.get("queue_order", [])
            for item_id in (
                "workflow::import-scores",
                "workflow::communicate-score",
                "workflow::score-checkpoint",
                "workflow::create-plan",
            )
        ),
        has_triage=any(
            isinstance(item_id, str) and item_id.startswith("triage::")
            for item_id in plan.get("queue_order", [])
        ),
        has_deferred=False,
    )[1]


def _print_review_import_sync(
    state: dict,
    result: plan_queue_mod.ReviewImportSyncResult,
    *,
    workflow_injected: bool,
) -> None:
    """Print summary of plan changes after review import sync."""
    new_ids = result.new_ids
    stale_pruned = result.stale_pruned_from_queue
    print()
    _print_new_review_items(state, new_ids)
    _print_stale_review_prunes(stale_pruned)
    _print_review_import_footer(result, workflow_injected=workflow_injected)


def _print_new_review_items(state: dict, new_ids: list[str]) -> None:
    if not new_ids:
        return
    print(colorize(
        f"  Plan updated: {len(new_ids)} new review issue(s) added to queue.",
        "bold",
    ))
    issues = state.get("issues", {})
    for finding_id in sorted(new_ids)[:10]:
        finding = issues.get(finding_id, {})
        print(f"    * [{short_issue_id(finding_id)}] {finding.get('summary', '')}")
    if len(new_ids) > 10:
        print(colorize(f"    ... and {len(new_ids) - 10} more", "dim"))


def _print_stale_review_prunes(stale_pruned: list[str]) -> None:
    if not stale_pruned:
        return
    print(colorize(
        f"  Plan updated: {len(stale_pruned)} stale review issue(s) removed from queue.",
        "bold",
    ))


def _print_review_import_footer(
    result: plan_queue_mod.ReviewImportSyncResult,
    *,
    workflow_injected: bool,
) -> None:
    print()
    print(colorize(
        "  Review queue sync completed. Workflow follow-up may be front-loaded.",
        "dim",
    ))
    print()
    print(colorize("  View execution queue:  desloppify plan queue", "dim"))
    print(colorize("  View newest first:     desloppify plan queue --sort recent", "dim"))
    print(colorize("  View broader backlog:  desloppify backlog", "dim"))
    print()
    print(colorize("  NEXT STEP:", "yellow"))
    print(colorize("    Run:    desloppify next", "yellow"))
    if result.triage_injected and not workflow_injected:
        print(colorize(f"    Codex:  {TRIAGE_CMD_RUN_STAGES_CODEX}", "dim"))
        print(colorize(f"    Claude: {TRIAGE_CMD_RUN_STAGES_CLAUDE}", "dim"))
        print(colorize("    Manual dashboard: desloppify plan triage", "dim"))
    print(colorize(
        "  (Follow the queue in order; score communication and planning come before triage.)",
        "dim",
    ))


def _review_delta_present(diff: dict) -> bool:
    return any(
        int(diff.get(key, 0) or 0) > 0
        for key in ("new", "reopened", "auto_resolved")
    )


def _print_workflow_injected_message(workflow_injected_ids: list[str]) -> None:
    if not workflow_injected_ids:
        return
    injected_parts = [f"`{workflow_id}`" for workflow_id in workflow_injected_ids]
    print(colorize(
        f"  Plan: {' and '.join(injected_parts)} queued. Run `desloppify next`.",
        "cyan",
    ))


def sync_plan_after_import(
    state: dict,
    diff: dict,
    assessment_mode: str,
    *,
    state_file: str | Path | None = None,
    config: dict | None = None,
    import_file: str | None = None,
    import_payload: dict | None = None,
) -> None:
    """Apply issue/workflow syncs after import in one load/save cycle."""
    try:
        plan_path = None
        target_strict = target_strict_score_from_config(config)
        if state_file is not None:
            plan_path = plan_queue_mod.plan_path_for_state(Path(state_file))
        if not plan_queue_mod.has_living_plan(plan_path):
            return

        plan = plan_queue_mod.load_plan(plan_path)
        dirty = False
        workflow_injected_ids: list[str] = []
        policy = plan_queue_mod.compute_subjective_visibility(
            state,
            target_strict=target_strict,
            plan=plan,
        )

        snapshot = state_mod.score_snapshot(state)
        current_scores = plan_queue_mod.ScoreSnapshot(
            strict=snapshot.strict,
            overall=snapshot.overall,
            objective=snapshot.objective,
            verified=snapshot.verified,
        )
        trusted_score_import = assessment_mode in {"trusted_internal", "attested_external"}
        communicate_result = plan_queue_mod.sync_communicate_score_needed(
            plan,
            state,
            policy=policy,
            scores_just_imported=trusted_score_import,
            current_scores=current_scores,
        )
        if communicate_result.changes:
            dirty = True
            workflow_injected_ids.append("workflow::communicate-score")

        has_review_issue_delta = _review_delta_present(diff)
        assessment_keys = (
            imported_assessment_keys(import_payload)
            if isinstance(import_payload, dict)
            else set()
        )
        import_result = None
        covered_ids = [
            f"subjective::{dim_key}"
            for dim_key in sorted(assessment_keys)
        ]
        stale_sync_result = None
        auto_cluster_changes = 0

        import_scores_result = plan_queue_mod.sync_import_scores_needed(
            plan,
            state,
            assessment_mode=assessment_mode,
            import_file=import_file,
            import_payload=import_payload,
        )
        if import_scores_result.changes:
            dirty = True
            if import_scores_result.injected:
                workflow_injected_ids.append("workflow::import-scores")

        create_plan_result = plan_queue_mod.sync_create_plan_needed(
            plan,
            state,
            policy=policy,
        )
        if create_plan_result.changes:
            dirty = True
            workflow_injected_ids.append("workflow::create-plan")

        if has_review_issue_delta:
            import_result = plan_queue_mod.sync_plan_after_review_import(
                plan,
                state,
                policy=policy,
            )
            if import_result is not None:
                dirty = True

        if has_review_issue_delta or assessment_keys:
            # Assessment-bearing imports can change subjective queue semantics
            # even when they add no review findings. Keep queue_order aligned
            # first, then rebuild the derived auto-clusters from that queue.
            cycle_just_completed = not plan.get("plan_start_scores")
            stale_sync_result = plan_queue_mod.sync_subjective_dimensions(
                plan,
                state,
                policy=policy,
                cycle_just_completed=cycle_just_completed,
            )
            if stale_sync_result.changes:
                dirty = True

            auto_cluster_changes = int(plan_queue_mod.auto_cluster_issues(
                plan,
                state,
                target_strict=target_strict,
                policy=policy,
            ))
            if auto_cluster_changes:
                dirty = True

        if dirty:
            if _sync_lifecycle_phase_after_import(plan, state, policy=policy):
                dirty = True
            if communicate_result.changes:
                plan_queue_mod.append_log_entry(
                    plan,
                    "sync_communicate_score",
                    actor="system",
                    detail={"trigger": "review_import", "injected": True},
                )
            if import_scores_result.changes:
                plan_queue_mod.append_log_entry(
                    plan,
                    "sync_import_scores",
                    actor="system",
                    detail={
                        "trigger": "review_import",
                        "injected": bool(import_scores_result.injected),
                        "pruned": list(import_scores_result.pruned),
                    },
                )
            if create_plan_result.changes:
                plan_queue_mod.append_log_entry(
                    plan,
                    "sync_create_plan",
                    actor="system",
                    detail={"trigger": "review_import", "injected": True},
                )
            if import_result is not None or workflow_injected_ids or covered_ids:
                plan_queue_mod.append_log_entry(
                    plan,
                    "review_import_sync",
                    actor="system",
                    detail={
                        "trigger": "review_import",
                        "new_ids": sorted(import_result.new_ids) if import_result is not None else [],
                        "added_to_queue": (
                            import_result.added_to_queue if import_result is not None else []
                        ),
                        "workflow_injected_ids": workflow_injected_ids,
                        "triage_injected": (
                            import_result.triage_injected if import_result is not None else False
                        ),
                        "triage_injected_ids": (
                            import_result.triage_injected_ids if import_result is not None else []
                        ),
                        "triage_deferred": (
                            import_result.triage_deferred if import_result is not None else False
                        ),
                        "diff_new": diff.get("new", 0),
                        "diff_reopened": diff.get("reopened", 0),
                        "diff_auto_resolved": diff.get("auto_resolved", 0),
                        "stale_pruned_from_queue": (
                            import_result.stale_pruned_from_queue if import_result is not None else []
                        ),
                        "covered_subjective": covered_ids,
                        "stale_sync_injected": (
                            sorted(stale_sync_result.injected)
                            if stale_sync_result is not None else []
                        ),
                        "stale_sync_pruned": (
                            sorted(stale_sync_result.pruned)
                            if stale_sync_result is not None else []
                        ),
                        "auto_cluster_changes": auto_cluster_changes,
                    },
                )
            plan_queue_mod.save_plan(plan, plan_path)

        if import_result is not None:
            _print_review_import_sync(
                state,
                import_result,
                workflow_injected=bool(workflow_injected_ids),
            )
        _print_workflow_injected_message(workflow_injected_ids)
    except PLAN_LOAD_EXCEPTIONS as exc:
        print(
            colorize(
                f"  Note: skipped plan sync after review import ({exc}).",
                "dim",
            )
        )


__all__ = ["sync_plan_after_import"]
