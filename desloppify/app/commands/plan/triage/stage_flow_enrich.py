"""Enrich stage command flow."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from desloppify.base.output.terminal import colorize
from desloppify.base.output.user_message import print_user_message

from .stages.records import record_enrich_stage, resolve_reusable_report
from .validation.enrich_checks import (
    _enrich_report_or_error,
    _require_organize_stage_for_enrich,
    _steps_with_bad_paths,
    _steps_without_effort,
    _underspecified_steps,
)
from .helpers import (
    count_log_activity_since,
    has_triage_in_queue,
    open_review_ids_from_state,
    print_cascade_clear_feedback,
)
from .services import TriageServices, default_triage_services

ColorizeFn = Callable[[str, str], str]


@dataclass(frozen=True)
class EnrichStageDeps:
    has_triage_in_queue: Callable[[dict], bool] = has_triage_in_queue
    require_organize_stage_for_enrich: Callable[[dict], bool] = _require_organize_stage_for_enrich
    underspecified_steps: Callable[[dict], list[tuple[str, int, int]]] = _underspecified_steps
    steps_with_bad_paths: Callable[[dict, Path], list[tuple[str, int, list[str]]]] = _steps_with_bad_paths
    steps_without_effort: Callable[[dict], list[tuple[str, int, int]]] = _steps_without_effort
    enrich_report_or_error: Callable[[str | None], str | None] = _enrich_report_or_error
    resolve_reusable_report: Callable[[str | None, dict | None], tuple[str | None, bool]] = (
        resolve_reusable_report
    )
    record_enrich_stage: Callable[..., list[str]] = record_enrich_stage
    count_log_activity_since: Callable[[dict, str], dict[str, int]] = count_log_activity_since
    colorize: ColorizeFn = colorize
    print_user_message: Callable[[str], None] = print_user_message
    print_cascade_clear_feedback: Callable[[list[str], dict], None] = print_cascade_clear_feedback
    default_triage_services: Callable[[], TriageServices] = default_triage_services
    get_project_root: Callable[[], Path] | None = None
    auto_confirm_organize_for_complete: Callable[..., bool] | None = None


def run_stage_enrich(
    args: argparse.Namespace,
    *,
    services: TriageServices | None,
    deps: EnrichStageDeps | None = None,
) -> None:
    """Record the ENRICH stage with validation and optional auto-confirm."""
    resolved_deps = deps or EnrichStageDeps()
    report: str | None = getattr(args, "report", None)
    attestation: str | None = getattr(args, "attestation", None)

    resolved_services = services or resolved_deps.default_triage_services()
    plan = resolved_services.load_plan()
    state = resolved_services.command_runtime(args).state

    if not resolved_deps.has_triage_in_queue(plan):
        print(resolved_deps.colorize("  No planning stages in the queue — nothing to enrich.", "yellow"))
        return

    meta = plan.get("epic_triage_meta", {})
    stages = meta.get("triage_stages", {})

    existing_stage = stages.get("enrich")
    report, is_reuse = resolved_deps.resolve_reusable_report(report, existing_stage)

    if not resolved_deps.require_organize_stage_for_enrich(stages):
        return

    if not stages.get("organize", {}).get("confirmed_at"):
        if attestation:
            auto_confirm_organize_for_complete = resolved_deps.auto_confirm_organize_for_complete
            if auto_confirm_organize_for_complete is None:
                from .validation.completion_stages import _auto_confirm_stage_for_complete

                auto_confirm_organize_for_complete = _auto_confirm_stage_for_complete
            if not auto_confirm_organize_for_complete(
                plan=plan,
                stages=stages,
                stage="organize",
                attestation=attestation,
                save_plan_fn=resolved_services.save_plan,
            ):
                return
        else:
            print(resolved_deps.colorize("  Cannot enrich: organize stage not confirmed.", "red"))
            print(resolved_deps.colorize("  Run: desloppify plan triage --confirm organize", "dim"))
            print(resolved_deps.colorize("  Or pass --attestation to auto-confirm organize inline.", "dim"))
            return

    if not is_reuse:
        organize_ts = stages.get("organize", {}).get("timestamp", "")
        if organize_ts:
            activity = resolved_deps.count_log_activity_since(plan, organize_ts)
            update_ops = activity.get("cluster_update", 0)
            if update_ops == 0 and open_review_ids_from_state(state):
                if attestation and len(attestation.strip()) >= 40:
                    print(resolved_deps.colorize(
                        "  Note: 0 cluster_update ops logged since organize. "
                        "Proceeding with attestation override.",
                        "yellow",
                    ))
                else:
                    print(resolved_deps.colorize(
                        "  Cannot enrich: no cluster_update operations logged since organize.",
                        "red",
                    ))
                    print(resolved_deps.colorize(
                        "  Enriching steps requires running cluster update commands.\n"
                        '  e.g. desloppify plan cluster update <name> --update-step N --detail "..."',
                        "dim",
                    ))
                    print(resolved_deps.colorize(
                        '  Override: pass --attestation "reason why no update ops" (40+ chars).',
                        "dim",
                    ))
                    return

    underspec = resolved_deps.underspecified_steps(plan)
    total_bare = sum(n for _, n, _ in underspec)

    if underspec:
        print(
            resolved_deps.colorize(
                f"  Cannot enrich: {total_bare} step(s) across {len(underspec)} cluster(s) lack detail or issue_refs:",
                "red",
            )
        )
        for name, bare, total in underspec:
            print(resolved_deps.colorize(f"    {name}: {bare}/{total} steps need enrichment", "yellow"))
        print()
        print(
            resolved_deps.colorize(
                "  Every step needs --detail (sub-points) or --issue-refs (for auto-completion).",
                "dim",
            )
        )
        print(resolved_deps.colorize("  Fix:", "dim"))
        print(
            resolved_deps.colorize(
                '    desloppify plan cluster update <name> --update-step N --detail "sub-details"',
                "dim",
            )
        )
        print(
            resolved_deps.colorize(
                "  You can also still reorganize: add/remove clusters, reorder, etc.",
                "dim",
            )
        )
        return

    print(resolved_deps.colorize("  All steps have detail or issue_refs.", "green"))

    get_project_root = resolved_deps.get_project_root
    if get_project_root is None:
        from desloppify.base.discovery.paths import get_project_root

    bad_paths = resolved_deps.steps_with_bad_paths(plan, get_project_root())

    if bad_paths:
        total_bad = sum(len(bp) for _, _, bp in bad_paths)
        print(
            resolved_deps.colorize(
                f"  Warning: {total_bad} file path(s) in step details don't exist on disk:",
                "yellow",
            )
        )
        for name, step_num, paths in bad_paths[:5]:
            print(resolved_deps.colorize(f"    {name} step {step_num}: {', '.join(paths[:3])}", "yellow"))
        print(
            resolved_deps.colorize(
                "  Fix paths before confirming enrich (confirmation will block on bad paths).",
                "dim",
            )
        )

    untagged = resolved_deps.steps_without_effort(plan)
    if untagged:
        total_missing = sum(n for _, n, _ in untagged)
        print(resolved_deps.colorize(f"  Note: {total_missing} step(s) have no effort tag.", "yellow"))
        print(
            resolved_deps.colorize(
                "  Consider: desloppify plan cluster update <name> --update-step N --effort small",
                "dim",
            )
        )

    report = resolved_deps.enrich_report_or_error(report)
    if report is None:
        return

    stages = meta.setdefault("triage_stages", {})
    cleared = resolved_deps.record_enrich_stage(
        stages,
        report=report,
        shallow_count=total_bare,
        existing_stage=existing_stage,
        is_reuse=is_reuse,
    )

    resolved_services.save_plan(plan)

    resolved_services.append_log_entry(
        plan,
        "triage_enrich",
        actor="user",
        detail={"shallow_count": total_bare, "reuse": is_reuse},
    )
    resolved_services.save_plan(plan)

    print(
        resolved_deps.colorize(
            f"  Enrich stage recorded: {total_bare} step(s) still without detail.",
            "green",
        )
    )
    if is_reuse:
        print(resolved_deps.colorize("  Enrich data preserved (no changes).", "dim"))
        if cleared:
            resolved_deps.print_cascade_clear_feedback(cleared, stages)
    else:
        print(resolved_deps.colorize("  Now confirm the enrichment.", "yellow"))
        print(resolved_deps.colorize("    desloppify plan triage --confirm enrich", "dim"))

    resolved_deps.print_user_message(
        "Enrich recorded. Before confirming — check the subagent's"
        " work. Could a developer who has never seen this code"
        " execute every step without asking a question? Every step"
        " needs: file path, specific location, specific action."
        " 'Refactor X' fails. 'Extract lines 45-89 into Y' passes."
    )


__all__ = ["ColorizeFn", "EnrichStageDeps", "run_stage_enrich"]
