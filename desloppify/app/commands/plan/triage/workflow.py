"""Triage workflow orchestration for command routing and stage dispatch."""

from __future__ import annotations

import argparse
from collections.abc import Callable

from desloppify.base.output.terminal import colorize
from desloppify.engine.plan_triage import TRIAGE_CMD_OBSERVE

from . import helpers as _helpers_mod
from . import lifecycle as _lifecycle_mod
from .confirmations import router as _confirmations_router_mod
from .display import dashboard as _display_mod
from .runner.orchestrator_claude import run_claude_orchestrator
from .runner.orchestrator_codex_pipeline import run_codex_pipeline
from .runner.orchestrator_common import parse_only_stages
from .runner.stage_prompts import cmd_stage_prompt
from .services import TriageServices
from .stages.completion import cmd_confirm_existing, cmd_triage_complete
from .stages.commands import run_stage_command


def _cmd_triage_start(
    args: argparse.Namespace,
    *,
    state: dict,
    services: TriageServices,
) -> None:
    """Manually inject triage stage IDs into the queue and clear prior stages."""
    plan = services.load_plan()

    if _helpers_mod.has_triage_in_queue(plan):
        print(colorize("  Planning mode stages are already in the queue.", "yellow"))
        meta = plan.get("epic_triage_meta", {})
        stages = meta.get("triage_stages", {})
        if stages:
            print(
                colorize(
                    f"  {len(stages)} stage(s) in progress - clearing to restart.",
                    "yellow",
                )
            )
            meta["triage_stages"] = {}
            _helpers_mod.ensure_active_triage_issue_ids(plan, state)
            _helpers_mod.inject_triage_stages(plan)
            services.save_plan(plan)
            services.append_log_entry(
                plan,
                "triage_start",
                actor="user",
                detail={"action": "restart", "cleared_stages": list(stages.keys())},
            )
            services.save_plan(plan)
            print(colorize("  Stages cleared. Begin with observe:", "green"))
        else:
            _helpers_mod.ensure_active_triage_issue_ids(plan, state)
            _helpers_mod.inject_triage_stages(plan)
            services.save_plan(plan)
            print(colorize("  Begin with observe:", "green"))
        print(colorize(f"    {TRIAGE_CMD_OBSERVE}", "dim"))
        return

    attestation: str | None = getattr(args, "attestation", None)
    start_outcome = _lifecycle_mod.ensure_triage_started(
        plan,
        services=services,
        state=state,
        attestation=attestation,
        log_action="triage_start",
        log_actor="user",
        log_detail={"action": "start"},
        start_message="  Planning mode started (6 stages queued).",
        start_message_style="green",
    )
    if start_outcome.status == "blocked":
        return

    si = services.collect_triage_input(plan, state)
    print(f"  Open review issues: {len(si.open_issues)}")
    print(colorize("  Begin with observe:", "dim"))
    print(colorize(f"    {TRIAGE_CMD_OBSERVE}", "dim"))


def _run_staged_runner(
    args: argparse.Namespace,
    *,
    services: TriageServices,
) -> None:
    runner = str(getattr(args, "runner", "codex")).strip().lower()
    try:
        stages_to_run = parse_only_stages(getattr(args, "only_stages", None))
    except ValueError as exc:
        print(colorize(f"  {exc}", "red"))
        return
    if runner == "claude":
        run_claude_orchestrator(args, services=services)
        return
    if runner == "codex":
        run_codex_pipeline(
            args,
            stages_to_run=stages_to_run,
            services=services,
        )
        return
    print(colorize(f"  Unknown runner: {runner}. Use 'codex' or 'claude'.", "red"))


def _run_dry_run(
    *,
    services: TriageServices,
    state: dict,
) -> None:
    plan = services.load_plan()
    si = services.collect_triage_input(plan, state)
    prompt = services.build_triage_prompt(si)
    existing_clusters = getattr(si, "existing_clusters", getattr(si, "existing_epics", {}))
    print(colorize("  Cluster triage - dry run", "bold"))
    print(colorize("  " + "─" * 60, "dim"))
    print(f"  Open review issues: {len(si.open_issues)}")
    print(f"  Existing clusters: {len(existing_clusters)}")
    print(f"  New since last: {len(si.new_since_last)}")
    print(f"  Resolved since last: {len(si.resolved_since_last)}")
    print(colorize("\n  Prompt that would be sent to LLM:", "dim"))
    print()
    print(prompt)


def run_triage_workflow(
    args: argparse.Namespace,
    *,
    services: TriageServices,
    require_issue_inventory_fn: Callable[[dict], bool],
) -> None:
    """Route `plan triage` args through one orchestration seam."""
    runtime = services.command_runtime(args)
    state = runtime.state
    if not require_issue_inventory_fn(state):
        return

    if getattr(args, "stage_prompt", None):
        cmd_stage_prompt(args, services=services)
        return
    if getattr(args, "run_stages", False):
        _run_staged_runner(args, services=services)
        return
    if getattr(args, "start", False):
        _cmd_triage_start(args, state=state, services=services)
        return
    if getattr(args, "confirm", None):
        _confirmations_router_mod.cmd_confirm_stage(args, services=services)
        return
    if getattr(args, "complete", False):
        cmd_triage_complete(args, services=services)
        return
    if getattr(args, "confirm_existing", False):
        cmd_confirm_existing(args, services=services)
        return

    stage = getattr(args, "stage", None)
    if run_stage_command(stage, args, services=services):
        return

    if getattr(args, "dry_run", False):
        _run_dry_run(services=services, state=state)
        return

    _display_mod.cmd_triage_dashboard(args, services=services)


__all__ = ["run_triage_workflow"]
