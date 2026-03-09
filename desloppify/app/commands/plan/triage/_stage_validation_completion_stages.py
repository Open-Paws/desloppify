"""Stage-gate and fold-confirm helpers for triage completion."""

from __future__ import annotations

from desloppify.engine._plan.triage_playbook import TRIAGE_CMD_ORGANIZE
from desloppify.base.output.terminal import colorize

from .helpers import manual_clusters_with_issues
from .stage_helpers import unenriched_clusters
from ._stage_validation_enrich_checks import _underspecified_steps


def _require_enrich_stage_for_complete(
    *,
    plan: dict,
    meta: dict,
    stages: dict,
) -> bool:
    if "enrich" in stages:
        return True
    if "organize" not in stages:
        return _require_organize_stage_for_complete(plan=plan, meta=meta, stages=stages)

    underspec = _underspecified_steps(plan)
    if underspec:
        print(colorize("  Cannot complete: enrich stage not done.", "red"))
        print(colorize(f"  {len(underspec)} cluster(s) have underspecified steps (missing detail or issue_refs):", "yellow"))
        for name, bare, total in underspec[:5]:
            print(colorize(f"    {name}: {bare}/{total} steps need enrichment", "yellow"))
        print(colorize('  Fix: desloppify plan cluster update <name> --update-step N --detail "sub-details"', "dim"))
        print(colorize('  Then: desloppify plan triage --stage enrich --report "..."', "dim"))
    else:
        print(colorize("  Cannot complete: enrich stage not recorded.", "red"))
        print(colorize("  Steps look enriched. Record the stage:", "dim"))
        print(colorize('    desloppify plan triage --stage enrich --report "..."', "dim"))
    return False


def _auto_confirm_enrich_for_complete(
    *,
    plan: dict,
    stages: dict,
    attestation: str | None,
    save_plan_fn=None,
) -> bool:
    enrich_stage = stages.get("enrich")
    if enrich_stage is None:
        return False

    underspec = _underspecified_steps(plan)
    if underspec:
        total_bare = sum(n for _, n, _ in underspec)
        print(colorize(f"  Cannot auto-confirm enrich: {total_bare} step(s) still lack detail or issue_refs.", "red"))
        for name, bare, total in underspec[:5]:
            print(colorize(f"    {name}: {bare}/{total} steps", "yellow"))
        print(colorize('  Fix: desloppify plan cluster update <name> --update-step N --detail "sub-details"', "dim"))
        return False

    cluster_names = [name for name in plan.get("clusters", {}) if not plan["clusters"][name].get("auto")]
    from . import _stage_validation as host  # noqa: PLC0415

    return host._auto_confirm_stage(
        plan=plan,
        stage_record=enrich_stage,
        stage_name="enrich",
        stage_label="Enrich",
        attestation=attestation,
        blocked_heading="Cannot complete: enrich stage not confirmed.",
        confirm_cmd="desloppify plan triage --confirm enrich",
        inline_hint="Or pass --attestation to auto-confirm enrich inline.",
        cluster_names=cluster_names,
        save_plan_fn=save_plan_fn,
    )


def _require_sense_check_stage_for_complete(
    *,
    plan: dict,
    meta: dict,
    stages: dict,
) -> bool:
    if "sense-check" in stages:
        return True
    if "enrich" not in stages:
        return _require_enrich_stage_for_complete(plan=plan, meta=meta, stages=stages)

    print(colorize("  Cannot complete: sense-check stage not recorded.", "red"))
    print(colorize('  Run: desloppify plan triage --stage sense-check --report "..."', "dim"))
    return False


def _auto_confirm_sense_check_for_complete(
    *,
    plan: dict,
    stages: dict,
    attestation: str | None,
    save_plan_fn=None,
) -> bool:
    sense_check_stage = stages.get("sense-check")
    if sense_check_stage is None:
        return False

    cluster_names = [name for name in plan.get("clusters", {}) if not plan["clusters"][name].get("auto")]
    from . import _stage_validation as host  # noqa: PLC0415

    return host._auto_confirm_stage(
        plan=plan,
        stage_record=sense_check_stage,
        stage_name="sense-check",
        stage_label="Sense-check",
        attestation=attestation,
        blocked_heading="Cannot complete: sense-check stage not confirmed.",
        confirm_cmd="desloppify plan triage --confirm sense-check",
        inline_hint="Or pass --attestation to auto-confirm sense-check inline.",
        cluster_names=cluster_names,
        save_plan_fn=save_plan_fn,
    )


def _require_organize_stage_for_complete(
    *,
    plan: dict,
    meta: dict,
    stages: dict,
) -> bool:
    if "organize" in stages:
        return True
    if "observe" not in stages:
        print(colorize("  Cannot complete: no stages done yet.", "red"))
        print(colorize('  Start with: desloppify plan triage --stage observe --report "..."', "dim"))
        return False

    print(colorize("  Cannot complete: organize stage not done.", "red"))
    gaps = unenriched_clusters(plan)
    if gaps:
        print(colorize(f"  {len(gaps)} cluster(s) still need enrichment:", "yellow"))
        for name, missing in gaps:
            print(colorize(f"    {name}: missing {', '.join(missing)}", "yellow"))
        print(colorize('  Fix: desloppify plan cluster update <name> --description "..." --steps "step1" "step2"', "dim"))
        print(colorize(f"  Then: {TRIAGE_CMD_ORGANIZE}", "dim"))
    else:
        manual = manual_clusters_with_issues(plan)
        if manual:
            print(colorize("  Clusters are enriched. Record the organize stage first:", "dim"))
            print(colorize(f"    {TRIAGE_CMD_ORGANIZE}", "dim"))
        else:
            print(colorize("  Create enriched clusters first, then record organize:", "dim"))
            print(colorize(f"    {TRIAGE_CMD_ORGANIZE}", "dim"))
    if meta.get("strategy_summary"):
        print(colorize('  Or fast-track: --confirm-existing --note "why plan is still valid" --strategy "..."', "dim"))
    return False


def _auto_confirm_organize_for_complete(
    *,
    plan: dict,
    stages: dict,
    attestation: str | None,
    save_plan_fn=None,
) -> bool:
    organize_stage = stages.get("organize")
    if organize_stage is None:
        return False

    organize_clusters = [name for name in plan.get("clusters", {}) if not plan["clusters"][name].get("auto")]
    from . import _stage_validation as host  # noqa: PLC0415

    return host._auto_confirm_stage(
        plan=plan,
        stage_record=organize_stage,
        stage_name="organize",
        stage_label="Organize",
        attestation=attestation,
        blocked_heading="Cannot complete: organize stage not confirmed.",
        confirm_cmd="desloppify plan triage --confirm organize",
        inline_hint="Or pass --attestation to auto-confirm organize inline.",
        cluster_names=organize_clusters,
        save_plan_fn=save_plan_fn,
    )


__all__ = [
    "_auto_confirm_enrich_for_complete",
    "_auto_confirm_organize_for_complete",
    "_auto_confirm_sense_check_for_complete",
    "_require_enrich_stage_for_complete",
    "_require_organize_stage_for_complete",
    "_require_sense_check_stage_for_complete",
]
