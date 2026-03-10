"""Completion strategy/policy validation helpers for triage workflow."""

from __future__ import annotations

from desloppify.engine.plan_triage import TRIAGE_CMD_ORGANIZE
from desloppify.base.output.terminal import colorize
from desloppify.engine.plan_triage import extract_issue_citations

from ..display.dashboard import show_plan_summary
from ..helpers import manual_clusters_with_issues, open_review_ids_from_state
from ..stages.helpers import unclustered_review_issues, unenriched_clusters


def _completion_clusters_valid(plan: dict, state: dict | None = None) -> bool:
    if state is not None and not open_review_ids_from_state(state):
        return True

    manual_clusters = manual_clusters_with_issues(plan)
    if not manual_clusters:
        any_clusters = [name for name, cluster in plan.get("clusters", {}).items() if cluster.get("issue_ids")]
        if not any_clusters:
            print(colorize("  Cannot complete: no clusters with issues exist.", "red"))
            print(colorize('  Create clusters: desloppify plan cluster create <name> --description "..."', "dim"))
            return False

    gaps = unenriched_clusters(plan)
    if gaps:
        print(colorize(f"  Cannot complete: {len(gaps)} cluster(s) still need enrichment.", "red"))
        for name, missing in gaps:
            print(colorize(f"    {name}: missing {', '.join(missing)}", "yellow"))
        print(colorize("  Small clusters (<5 issues) need at least 1 action step per issue.", "dim"))
        print(colorize('  Fix: desloppify plan cluster update <name> --description "..." --steps "step1" "step2"', "dim"))
        return False

    unclustered = unclustered_review_issues(plan, state)
    if unclustered:
        print(colorize(f"  Cannot complete: {len(unclustered)} review issue(s) have no action plan.", "red"))
        for fid in unclustered[:5]:
            short = fid.rsplit("::", 2)[-2] if "::" in fid else fid
            print(colorize(f"    {short}", "yellow"))
        if len(unclustered) > 5:
            print(colorize(f"    ... and {len(unclustered) - 5} more", "yellow"))
        print(colorize("  Add to a cluster or wontfix each unclustered issue.", "dim"))
        return False

    return True


def _resolve_completion_strategy(strategy: str | None, *, meta: dict) -> str | None:
    if strategy:
        return strategy
    print(colorize("  --strategy is required.", "red"))
    existing = meta.get("strategy_summary", "")
    if existing:
        print(colorize(f"  Current strategy: {existing}", "dim"))
        print(colorize('  Use --strategy "same" to keep it, or provide a new summary.', "dim"))
    else:
        print(colorize('  Provide --strategy "execution plan describing priorities, ordering, and verification approach"', "dim"))
    return None


def _completion_strategy_valid(strategy: str) -> bool:
    if strategy.strip().lower() == "same":
        return True
    if len(strategy.strip()) >= 200:
        return True
    print(colorize(f"  Strategy too short: {len(strategy.strip())} chars (minimum 200).", "red"))
    print(colorize("  The strategy should describe:", "dim"))
    print(colorize("    - Execution order and priorities", "dim"))
    print(colorize("    - What each cluster accomplishes", "dim"))
    print(colorize("    - How to verify the work is correct", "dim"))
    return False


def _require_prior_strategy_for_confirm(meta: dict) -> bool:
    if meta.get("strategy_summary", ""):
        return True
    print(colorize("  Cannot confirm existing: no prior triage has been completed.", "red"))
    print(colorize("  The full OBSERVE → REFLECT → ORGANIZE → COMMIT flow is required the first time.", "dim"))
    print(colorize(f"  Create and enrich clusters, then: {TRIAGE_CMD_ORGANIZE}", "dim"))
    return False


def _confirm_existing_stages_valid(*, stages: dict, has_only_additions: bool, si) -> bool:
    if has_only_additions:
        from ..stages.rendering import _print_new_issues_since_last  # noqa: PLC0415

        _print_new_issues_since_last(si)
        return True
    if "observe" not in stages:
        print(colorize("  Cannot confirm existing: observe stage not complete.", "red"))
        print(colorize("  You must read issues first.", "dim"))
        print(colorize('  Run: desloppify plan triage --stage observe --report "..."', "dim"))
        return False
    if "reflect" not in stages:
        print(colorize("  Cannot confirm existing: reflect stage not complete.", "red"))
        print(colorize("  You must compare against completed work first.", "dim"))
        print(colorize('  Run: desloppify plan triage --stage reflect --report "..."', "dim"))
        return False
    return True


def _confirm_note_valid(note: str | None) -> bool:
    if not note:
        print(colorize("  --note is required for confirm-existing.", "red"))
        print(colorize('  Explain why the existing plan is still valid (min 100 chars).', "dim"))
        return False
    if len(note) < 100:
        print(colorize(f"  Note too short: {len(note)} chars (minimum 100).", "red"))
        return False
    return True


def _resolve_confirm_existing_strategy(
    strategy: str | None,
    *,
    has_only_additions: bool,
    meta: dict,
) -> str | None:
    if strategy:
        return strategy
    if has_only_additions:
        return "same"
    print(colorize("  --strategy is required.", "red"))
    existing = meta.get("strategy_summary", "")
    if existing:
        print(colorize('  Use --strategy "same" to keep it, or provide a new summary.', "dim"))
    return None


def _confirm_strategy_valid(strategy: str) -> bool:
    if strategy.strip().lower() == "same":
        return True
    if len(strategy.strip()) >= 200:
        return True
    print(colorize(f"  Strategy too short: {len(strategy.strip())} chars (minimum 200).", "red"))
    return False


def _confirmed_text_or_error(*, plan: dict, state: dict, confirmed: str | None) -> str | None:
    from ..confirmations.basic import MIN_ATTESTATION_LEN  # noqa: PLC0415

    if confirmed and len(confirmed.strip()) >= MIN_ATTESTATION_LEN:
        return confirmed.strip()
    print(colorize("  Current plan:", "bold"))
    show_plan_summary(plan, state)
    if confirmed:
        print(colorize(f"\n  --confirmed text too short ({len(confirmed.strip())} chars, min {MIN_ATTESTATION_LEN}).", "red"))
    print(colorize('\n  Add --confirmed "I validate this plan..." to proceed.', "dim"))
    return None


def _note_cites_new_issues_or_error(note: str, si) -> bool:
    new_ids = si.new_since_last
    if not new_ids:
        return True
    valid_ids = set(si.open_issues.keys())
    cited = extract_issue_citations(note, valid_ids)
    new_cited = cited & new_ids
    if new_cited:
        return True
    print(colorize("  Note must cite at least 1 new/changed issue.", "red"))
    print(colorize(f"  {len(new_ids)} new issue(s) since last triage:", "dim"))
    for fid in sorted(new_ids)[:5]:
        print(colorize(f"    {fid}", "dim"))
    if len(new_ids) > 5:
        print(colorize(f"    ... and {len(new_ids) - 5} more", "dim"))
    return False


__all__ = [
    "_completion_clusters_valid",
    "_completion_strategy_valid",
    "_confirm_existing_stages_valid",
    "_confirm_note_valid",
    "_confirm_strategy_valid",
    "_confirmed_text_or_error",
    "_note_cites_new_issues_or_error",
    "_require_prior_strategy_for_confirm",
    "_resolve_completion_strategy",
    "_resolve_confirm_existing_strategy",
]
