"""Focused public plan API for triage orchestration surfaces."""

from __future__ import annotations

from desloppify.engine._plan.constants import (
    TRIAGE_IDS,
    TRIAGE_PREFIX,
    TRIAGE_STAGE_IDS,
    TRIAGE_STAGE_ORDER,
    TRIAGE_STAGE_SPECS,
)
from desloppify.engine._plan.triage.core import (
    TriageInput,
    build_triage_prompt,
    collect_triage_input,
    detect_recurring_patterns,
    extract_issue_citations,
)
from desloppify.engine._plan.triage.playbook import (
    TRIAGE_CMD_CLUSTER_ADD,
    TRIAGE_CMD_CLUSTER_CREATE,
    TRIAGE_CMD_CLUSTER_ENRICH,
    TRIAGE_CMD_CLUSTER_ENRICH_COMPACT,
    TRIAGE_CMD_CLUSTER_STEPS,
    TRIAGE_CMD_COMPLETE,
    TRIAGE_CMD_COMPLETE_VERBOSE,
    TRIAGE_CMD_CONFIRM_EXISTING,
    TRIAGE_CMD_ENRICH,
    TRIAGE_CMD_OBSERVE,
    TRIAGE_CMD_ORGANIZE,
    TRIAGE_CMD_REFLECT,
    TRIAGE_CMD_RUN_STAGES_CLAUDE,
    TRIAGE_CMD_RUN_STAGES_CODEX,
    TRIAGE_CMD_SENSE_CHECK,
    TRIAGE_STAGE_DEPENDENCIES,
    TRIAGE_STAGE_LABELS,
    triage_manual_stage_command,
    triage_run_stages_command,
    triage_runner_commands,
)
from desloppify.engine._plan.sync.triage_start_policy import (
    TriageStartDecision,
    decide_triage_start,
)
from desloppify.engine.plan_queue import has_objective_backlog
from desloppify.engine.plan_state import PlanModel, ensure_plan_defaults


def triage_phase_banner(plan: PlanModel, state: dict | None = None) -> str:
    """Return a banner string describing triage status."""
    ensure_plan_defaults(plan)
    order = set(plan.get("queue_order", []))
    has_triage = any(stage_id in order for stage_id in TRIAGE_IDS)
    meta = plan.get("epic_triage_meta", {})
    run_hint = (
        f"Run: {TRIAGE_CMD_RUN_STAGES_CODEX} "
        f"(or {TRIAGE_CMD_RUN_STAGES_CLAUDE})"
    )

    if not has_triage:
        undispositioned = meta.get("undispositioned_issue_count", 0)
        if undispositioned:
            return (
                "TRIAGE RECOVERY NEEDED — "
                f"{undispositioned} review issue(s) still need cluster/skip dispositions. "
                f"{run_hint}"
            )
        if meta.get("triage_recommended"):
            return (
                "TRIAGE RECOMMENDED — review issues changed since last triage. "
                f"{run_hint}"
            )
        return ""

    if state and has_objective_backlog(state, None):
        undispositioned = meta.get("undispositioned_issue_count", 0)
        if undispositioned:
            return (
                "TRIAGE PENDING — "
                f"{undispositioned} review issue(s) still need cluster/skip dispositions after current work. "
                f"{run_hint}"
            )
        return (
            "TRIAGE PENDING — queued and will activate after objective work "
            "is complete."
        )
    stages = meta.get("triage_stages", {})
    completed = [
        stage
        for stage in ("observe", "reflect", "organize", "enrich", "sense-check")
        if stage in stages
    ]
    if completed:
        return (
            f"TRIAGE MODE ({len(completed)}/5 stages complete) — "
            f"complete all stages to exit. {run_hint}"
        )
    return (
        "TRIAGE MODE — review issues need analysis before fixing. "
        f"{run_hint}"
    )

__all__ = [
    "TRIAGE_CMD_CLUSTER_ADD",
    "TRIAGE_CMD_CLUSTER_CREATE",
    "TRIAGE_CMD_CLUSTER_ENRICH",
    "TRIAGE_CMD_CLUSTER_ENRICH_COMPACT",
    "TRIAGE_CMD_CLUSTER_STEPS",
    "TRIAGE_CMD_COMPLETE",
    "TRIAGE_CMD_COMPLETE_VERBOSE",
    "TRIAGE_CMD_CONFIRM_EXISTING",
    "TRIAGE_CMD_ENRICH",
    "TRIAGE_CMD_OBSERVE",
    "TRIAGE_CMD_ORGANIZE",
    "TRIAGE_CMD_REFLECT",
    "TRIAGE_CMD_RUN_STAGES_CLAUDE",
    "TRIAGE_CMD_RUN_STAGES_CODEX",
    "TRIAGE_CMD_SENSE_CHECK",
    "TRIAGE_IDS",
    "TRIAGE_PREFIX",
    "TRIAGE_STAGE_DEPENDENCIES",
    "TRIAGE_STAGE_IDS",
    "TRIAGE_STAGE_LABELS",
    "TRIAGE_STAGE_ORDER",
    "TRIAGE_STAGE_SPECS",
    "TriageStartDecision",
    "TriageInput",
    "build_triage_prompt",
    "collect_triage_input",
    "decide_triage_start",
    "detect_recurring_patterns",
    "extract_issue_citations",
    "triage_phase_banner",
    "triage_manual_stage_command",
    "triage_run_stages_command",
    "triage_runner_commands",
]
