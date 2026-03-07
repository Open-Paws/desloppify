"""Completion/confirm command handlers for triage flow."""

from __future__ import annotations

import argparse

from desloppify.base.output.terminal import colorize
from desloppify.base.output.user_message import print_user_message

from .helpers import (
    apply_completion,
    has_triage_in_queue,
    manual_clusters_with_issues,
    open_review_ids_from_state,
    triage_coverage,
)
from .services import TriageServices, default_triage_services
from ._stage_records import _record_confirm_existing_completion
from ._stage_rendering import _print_complete_summary
from ._stage_validation import (
    _auto_confirm_enrich_for_complete,
    _auto_confirm_organize_for_complete,
    _completion_clusters_valid,
    _completion_strategy_valid,
    _confirm_existing_stages_valid,
    _confirm_note_valid,
    _confirm_strategy_valid,
    _confirmed_text_or_error,
    _note_cites_new_issues_or_error,
    _require_enrich_stage_for_complete,
    _require_organize_stage_for_complete,
    _require_prior_strategy_for_confirm,
    _resolve_completion_strategy,
    _resolve_confirm_existing_strategy,
)


def _cmd_triage_complete(
    args: argparse.Namespace,
    *,
    services: TriageServices | None = None,
) -> None:
    """Complete triage — requires organize stage (or confirm-existing path)."""
    resolved_services = services or default_triage_services()
    strategy: str | None = getattr(args, "strategy", None)
    attestation: str | None = getattr(args, "attestation", None)
    plan = resolved_services.load_plan()

    if not has_triage_in_queue(plan):
        print(colorize("  No planning stages in the queue — nothing to complete.", "yellow"))
        return

    meta = plan.get("epic_triage_meta", {})
    stages = meta.get("triage_stages", {})

    state = resolved_services.command_runtime(args).state
    review_ids = open_review_ids_from_state(state)

    # Require organize stage confirmed
    if not _require_organize_stage_for_complete(
        plan=plan,
        meta=meta,
        stages=stages,
    ):
        return

    # Fold-confirm: auto-confirm organize if attestation provided
    if not _auto_confirm_organize_for_complete(
        plan=plan,
        stages=stages,
        attestation=attestation,
    ):
        return

    # Require enrich stage confirmed
    if not _require_enrich_stage_for_complete(
        plan=plan,
        meta=meta,
        stages=stages,
    ):
        return

    # Fold-confirm: auto-confirm enrich if attestation provided
    if not _auto_confirm_enrich_for_complete(
        plan=plan,
        stages=stages,
        attestation=attestation,
    ):
        return

    # Re-validate cluster enrichment at completion time (prevents bypassing
    # organize gate by editing plan.json directly)
    if not _completion_clusters_valid(plan, state):
        return

    # Verify cluster coverage
    organized, total, _clusters = triage_coverage(plan, open_review_ids=review_ids)

    if total > 0 and organized == 0:
        print(colorize("  Cannot complete: no issues have been organized into clusters.", "red"))
        print(colorize(f"  {total} issues are waiting.", "dim"))
        return

    if total > 0 and organized < total:
        remaining = total - organized
        print(
            colorize(
                f"  Warning: {remaining}/{total} issues are not yet in any cluster.",
                "yellow",
            )
        )

    strategy = _resolve_completion_strategy(strategy, meta=meta)
    if strategy is None:
        return
    if not _completion_strategy_valid(strategy):
        return

    # Show summary
    _print_complete_summary(plan, stages)

    organized, total, _ = triage_coverage(plan, open_review_ids=review_ids)

    # Jump-back guidance before committing
    print()
    print(
        colorize(
            "  To revise an earlier stage: desloppify plan triage --stage <observe|reflect|organize|enrich>",
            "dim",
        )
    )
    print(colorize("  Pass --report to update, or omit to keep existing analysis.", "dim"))

    resolved_services.append_log_entry(
        plan,
        "triage_complete",
        actor="user",
        detail={
            "strategy_len": len(strategy.strip()),
            "coverage": f"{organized}/{total}",
        },
    )

    apply_completion(args, plan, strategy, services=resolved_services)

    print_user_message(
        "Hey — triage is done. Run `desloppify next` and start"
        " executing the plan. Don't stop until you're done —"
        " unless I've told you otherwise, just go."
    )


def _cmd_confirm_existing(
    args: argparse.Namespace,
    *,
    services: TriageServices | None = None,
) -> None:
    """Fast-track: confirm existing plan structure is still valid."""
    resolved_services = services or default_triage_services()
    note: str | None = getattr(args, "note", None)
    strategy: str | None = getattr(args, "strategy", None)
    confirmed: str | None = getattr(args, "confirmed", None)
    plan = resolved_services.load_plan()

    if not has_triage_in_queue(plan):
        print(colorize("  No planning stages in the queue — nothing to confirm.", "yellow"))
        return

    meta = plan.get("epic_triage_meta", {})
    stages = meta.get("triage_stages", {})

    # Require a prior completed triage — can't skip the full flow on first run
    if not _require_prior_strategy_for_confirm(meta):
        return

    # Determine if this is a light-path (additions only) or full ceremony
    runtime = resolved_services.command_runtime(args)
    state = runtime.state
    si = resolved_services.collect_triage_input(plan, state)
    has_only_additions = bool(si.new_since_last) and not si.resolved_since_last

    if not _confirm_existing_stages_valid(
        stages=stages,
        has_only_additions=has_only_additions,
        si=si,
    ):
        return

    # Require existing enriched clusters
    clusters_with_issues = manual_clusters_with_issues(plan)
    if not clusters_with_issues:
        print(colorize("  Cannot confirm existing: no clusters with issues exist.", "red"))
        print(colorize("  Use the full organize flow instead.", "dim"))
        return

    # Require note
    if not _confirm_note_valid(note):
        return

    # Require strategy (default to "same" on light path)
    strategy = _resolve_confirm_existing_strategy(
        strategy,
        has_only_additions=has_only_additions,
        meta=meta,
    )
    if strategy is None:
        return

    # Strategy length check (unless "same")
    if not _confirm_strategy_valid(strategy):
        return

    # Require --confirmed with plan review
    confirmed_text = _confirmed_text_or_error(
        plan=plan,
        state=state,
        confirmed=confirmed,
    )
    if confirmed_text is None:
        return

    # Validate: note cites at least 1 new/changed issue (if there are any)
    if not _note_cites_new_issues_or_error(note, si):
        return

    # Record organize as confirmed-existing and complete
    stages = meta.setdefault("triage_stages", {})
    _record_confirm_existing_completion(
        stages=stages,
        note=note,
        issue_count=len(clusters_with_issues),
        confirmed_text=confirmed_text,
    )

    resolved_services.append_log_entry(
        plan,
        "triage_confirm_existing",
        actor="user",
        detail={"confirmed_text": confirmed_text},
    )

    apply_completion(args, plan, strategy, services=resolved_services)
    print(colorize("  Confirmed existing plan — triage complete.", "green"))


def cmd_triage_complete(
    args: argparse.Namespace,
    *,
    services: TriageServices | None = None,
) -> None:
    """Public entrypoint for triage completion."""
    _cmd_triage_complete(args, services=services)


def cmd_confirm_existing(
    args: argparse.Namespace,
    *,
    services: TriageServices | None = None,
) -> None:
    """Public entrypoint for confirm-existing completion path."""
    _cmd_confirm_existing(args, services=services)


__all__ = [
    "cmd_confirm_existing",
    "cmd_triage_complete",
    "_cmd_confirm_existing",
    "_cmd_triage_complete",
]
