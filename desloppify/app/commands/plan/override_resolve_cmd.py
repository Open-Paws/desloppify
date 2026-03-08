"""Resolve command handler for plan overrides."""

from __future__ import annotations

import argparse
import logging

from desloppify import state as state_mod
from desloppify.app.commands.helpers.attestation import (
    show_attestation_requirement,
    show_note_length_requirement,
    validate_attestation,
    validate_note_length,
)
from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.app.commands.helpers.state import state_path
from desloppify.app.commands.plan.triage.helpers import has_triage_in_queue, inject_triage_stages
from desloppify.app.commands.resolve.cmd import cmd_resolve
from desloppify.base.exception_sets import PLAN_LOAD_EXCEPTIONS
from desloppify.base.output.fallbacks import log_best_effort_failure
from desloppify.base.output.terminal import colorize
from desloppify.engine._work_queue.core import ATTEST_EXAMPLE
from desloppify.engine.plan import (
    WORKFLOW_CREATE_PLAN_ID,
    WORKFLOW_SCORE_CHECKPOINT_ID,
    append_log_entry,
    auto_complete_steps,
    load_plan,
    purge_ids,
    save_plan,
)

from .override_resolve_helpers import blocked_triage_stages
from .override_resolve_helpers import check_cluster_guard
from .override_resolve_helpers import resolve_synthetic_ids

logger = logging.getLogger(__name__)


def cmd_plan_resolve(args: argparse.Namespace) -> None:
    """Mark issues as fixed — delegates to cmd_resolve for rich UX."""
    patterns: list[str] = getattr(args, "patterns", [])
    attestation: str | None = getattr(args, "attest", None)
    note: str | None = getattr(args, "note", None)

    if getattr(args, "confirm", False):
        if not note:
            print(colorize("  --confirm requires --note to describe what you did.", "red"))
            return
        attestation = f"I have actually {note} and I am not gaming the score."
        args.attest = attestation

    synthetic_ids, real_patterns = resolve_synthetic_ids(patterns)
    if synthetic_ids:
        plan = load_plan()

        blocked_map = blocked_triage_stages(plan)
        for sid in synthetic_ids:
            if sid in blocked_map:
                deps = ", ".join(dep.replace("triage::", "") for dep in blocked_map[sid])
                print(colorize(f"  Cannot resolve {sid} — blocked by: {deps}", "red"))
                print(colorize("  Complete those stages first, or use --force-resolve to override.", "dim"))
                if not getattr(args, "force_resolve", False):
                    return

        gated_ids = [
            sid
            for sid in synthetic_ids
            if sid in {WORKFLOW_SCORE_CHECKPOINT_ID, WORKFLOW_CREATE_PLAN_ID}
        ]
        if gated_ids:
            force = getattr(args, "force_resolve", False)
            meta = plan.get("epic_triage_meta", {})
            triage_ever_completed = bool(meta.get("last_completed_at"))
            if triage_ever_completed:
                missing: set[str] = set()
            else:
                confirmed_stages = set(meta.get("triage_stages", {}).keys())
                required_stages = {"observe", "reflect", "organize", "enrich", "commit"}
                missing = required_stages - confirmed_stages

            if missing and not force:
                if not has_triage_in_queue(plan):
                    inject_triage_stages(plan)
                    meta.setdefault("triage_stages", {})
                    plan["epic_triage_meta"] = meta
                    save_plan(plan)

                stage_order = ["observe", "reflect", "organize", "enrich", "commit"]
                next_stage = next((stage for stage in stage_order if stage in missing), "observe")

                for wid in gated_ids:
                    print(colorize(f"  Cannot resolve {wid} — triage not complete.", "red"))
                print()

                if next_stage == "observe":
                    print(colorize("  You must analyze the findings before resolving this.", "yellow"))
                    print(colorize("  Start by examining themes, root causes, and contradictions:", "dim"))
                    print(colorize('    desloppify plan triage --stage observe --report "..."', "dim"))
                    print()
                    print(colorize("  The report must be 100+ chars describing what you found.", "dim"))
                elif next_stage == "reflect":
                    print(colorize("  Observe is done. Now compare against previously completed work:", "yellow"))
                    print(colorize('    desloppify plan triage --stage reflect --report "..."', "dim"))
                    print()
                    print(colorize("  The report must mention recurring dimensions if any exist.", "dim"))
                elif next_stage == "organize":
                    print(colorize("  Reflect is done. Now create clusters and prioritize:", "yellow"))
                    print(colorize('    desloppify plan cluster create <name> --description "..."', "dim"))
                    print(colorize("    desloppify plan cluster add <name> <issue-patterns>", "dim"))
                    print(colorize('    desloppify plan cluster update <name> --steps "step1" "step2"', "dim"))
                    print(colorize('    desloppify plan triage --stage organize --report "..."', "dim"))
                    print()
                    print(colorize("  All manual clusters must have descriptions and action_steps.", "dim"))
                elif next_stage == "enrich":
                    print(colorize("  Organize is done. Now enrich steps with detail and issue refs:", "yellow"))
                    print(colorize('    desloppify plan cluster update <name> --update-step N --detail "sub-details"', "dim"))
                    print(colorize('    desloppify plan triage --stage enrich --report "..."', "dim"))
                elif next_stage == "commit":
                    print(colorize("  Enrich is done. Finalize the execution plan:", "yellow"))
                    print(colorize('    desloppify plan triage --complete --strategy "..."', "dim"))

                print()
                print(colorize(f"  Remaining stages: {', '.join(sorted(missing))}", "dim"))
                print(colorize("  To skip triage: --force-resolve --note 'reason for skipping triage'", "dim"))

                append_log_entry(
                    plan,
                    "workflow_blocked",
                    issue_ids=gated_ids,
                    actor="user",
                    note=note,
                    detail={"missing_stages": sorted(missing), "next_stage": next_stage},
                )
                save_plan(plan)
                return

            if missing and force:
                if not note or len(note.strip()) < 50:
                    print(
                        colorize(
                            "  --force-resolve still requires --note (min 50 chars) explaining "
                            "why you're skipping triage.",
                            "red",
                        )
                    )
                    return
                print(colorize("  WARNING: Skipping triage requirement — this is logged.", "yellow"))
                append_log_entry(
                    plan,
                    "workflow_force_skip",
                    issue_ids=gated_ids,
                    actor="user",
                    note=note,
                    detail={"forced": True, "missing_stages": sorted(missing)},
                )
                save_plan(plan)

        if gated_ids:
            scan_count_at_start = plan.get("scan_count_at_plan_start")
            force = getattr(args, "force_resolve", False)
            if scan_count_at_start is not None:
                resolved_state_path = state_path(args)
                state_data = state_mod.load_state(resolved_state_path)
                current_scan_count = int(state_data.get("scan_count", 0) or 0)
                scan_ran = current_scan_count > scan_count_at_start
                scan_skipped = plan.get("scan_gate_skipped", False)

                if not scan_ran and not scan_skipped and not force:
                    for wid in gated_ids:
                        print(colorize(f"  Cannot resolve {wid} — no scan has run this cycle.", "red"))
                    print()
                    print(colorize("  You must run a scan before resolving workflow items:", "yellow"))
                    print(colorize("    desloppify scan", "dim"))
                    print()
                    print(
                        colorize(
                            f"  Scans at cycle start: {scan_count_at_start}  "
                            f"Current: {current_scan_count}",
                            "dim",
                        )
                    )
                    print(
                        colorize(
                            "  To skip scan requirement: desloppify plan scan-gate --skip "
                            '--note "reason for skipping scan"',
                            "dim",
                        )
                    )
                    print(colorize("  Or use: --force-resolve --note 'reason for skipping'", "dim"))

                    append_log_entry(
                        plan,
                        "scan_gate_blocked",
                        issue_ids=gated_ids,
                        actor="user",
                        note=note,
                        detail={
                            "scan_count_at_start": scan_count_at_start,
                            "current_scan_count": current_scan_count,
                        },
                    )
                    save_plan(plan)
                    return

        purge_ids(plan, synthetic_ids)
        step_messages = auto_complete_steps(plan)
        for msg in step_messages:
            print(colorize(msg, "green"))
        append_log_entry(plan, "done", issue_ids=synthetic_ids, actor="user", note=note)
        save_plan(plan)
        for sid in synthetic_ids:
            print(colorize(f"  Resolved: {sid}", "green"))
        if not real_patterns:
            return
        patterns = real_patterns
        args.patterns = patterns

    if not validate_note_length(note):
        show_note_length_requirement(note)
        return

    if not validate_attestation(attestation):
        show_attestation_requirement("Plan resolve", attestation, ATTEST_EXAMPLE)
        return

    plan: dict | None = None
    try:
        runtime = command_runtime(args)
        state = runtime.state
        plan = load_plan()
        if check_cluster_guard(patterns, plan, state):
            return
    except PLAN_LOAD_EXCEPTIONS:
        plan = None

    try:
        if plan is None:
            plan = load_plan()
        clusters = plan.get("clusters", {})
        cluster_name = next((pattern for pattern in patterns if pattern in clusters), None)
        append_log_entry(
            plan,
            "done",
            issue_ids=patterns,
            cluster_name=cluster_name,
            actor="user",
            note=note,
        )
        save_plan(plan)
    except PLAN_LOAD_EXCEPTIONS as exc:
        log_best_effort_failure(logger, "append plan resolve log entry", exc)
        print(colorize(f"  Note: unable to append plan resolve log entry ({exc}).", "dim"))

    resolve_args = argparse.Namespace(
        status="fixed",
        patterns=patterns,
        note=note,
        attest=attestation,
        confirm_batch_wontfix=False,
        force_resolve=bool(getattr(args, "force_resolve", False)),
        state=getattr(args, "state", None),
        lang=getattr(args, "lang", None),
        path=getattr(args, "path", None),
        exclude=getattr(args, "exclude", None),
    )

    cmd_resolve(resolve_args)


__all__ = ["cmd_plan_resolve"]
