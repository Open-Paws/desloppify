"""Queue policy — how items enter and are visible in `desloppify next`.

This module is documentation-grade code. It describes the queue model
and provides helpers that read from the canonical QueueSnapshot.
It is NOT a parallel source of truth — all real computation happens
in snapshot.py. This module provides:
  1. explain_queue() that renders a human-readable summary from a snapshot

ORDERING: plan["queue_order"] is the durable ordering source.
VISIBILITY: Phase gate re-resolved from items every build.
AUTO-PROMOTE: Detectors with auto_queue=True in the registry auto-inject.
The auto_queue decision lives in cluster_semantics.infer_cluster_execution_policy().
See snapshot.py for computation, docs/QUEUE_LIFECYCLE.md for lifecycle.
"""

from __future__ import annotations

from desloppify.engine._plan.cluster_semantics import (
    EXECUTION_POLICY_EPHEMERAL_AUTOPROMOTE,
)
from desloppify.engine._plan.refresh_lifecycle import (
    LIFECYCLE_PHASE_ASSESSMENT_POSTFLIGHT,
    LIFECYCLE_PHASE_EXECUTE,
    LIFECYCLE_PHASE_REVIEW_INITIAL,
    LIFECYCLE_PHASE_REVIEW_POSTFLIGHT,
    LIFECYCLE_PHASE_SCAN,
    LIFECYCLE_PHASE_TRIAGE_POSTFLIGHT,
    LIFECYCLE_PHASE_WORKFLOW_POSTFLIGHT,
    user_facing_mode,
)
from desloppify.engine._work_queue.snapshot import QueueSnapshot


def _count_auto_and_triage(
    plan: dict | None,
) -> tuple[int, list[str], int]:
    """Count auto-queued vs triage-promoted clusters from persisted semantics.

    Returns (auto_count, auto_cluster_names, triage_count).
    Names come from the actual persisted clusters, not the registry.
    """
    if not isinstance(plan, dict):
        return 0, [], 0
    auto_names: list[str] = []
    triage_count = 0
    for name, cluster in plan.get("clusters", {}).items():
        if not isinstance(cluster, dict):
            continue
        execution_status = cluster.get("execution_status", "")
        if execution_status != "active":
            continue
        policy = cluster.get("execution_policy", "")
        if policy == EXECUTION_POLICY_EPHEMERAL_AUTOPROMOTE:
            auto_names.append(name)
        else:
            triage_count += 1
    return len(auto_names), sorted(auto_names), triage_count


def explain_queue(snapshot: QueueSnapshot, plan: dict | None) -> str:
    """Render a human-readable queue explanation from the canonical snapshot.

    Reads snapshot.phase, snapshot.execution_items, snapshot.backlog_items,
    and count fields. Does NOT recompute anything — purely a view.
    """
    phase = snapshot.phase
    lines: list[str] = [f"    Mode: {user_facing_mode(phase)}"]

    execution_count = len(snapshot.execution_items)
    # planned_objective_count reflects queue_order filtering (post-triage);
    # objective_in_scope_count is the broader pre-triage number.
    blocked_count = (
        snapshot.planned_objective_count
        if snapshot.planned_objective_count > 0
        else snapshot.objective_in_scope_count
    )
    objective_backlog_count = snapshot.objective_backlog_count

    if phase == LIFECYCLE_PHASE_REVIEW_INITIAL:
        lines.append(
            "    Why: Reviewing code quality dimensions before execution work appears."
        )
        lines.append(
            f"    After review: {snapshot.objective_in_scope_count} objective items will become available."
        )
    elif phase == LIFECYCLE_PHASE_EXECUTE:
        auto_count, auto_names, triage_count = _count_auto_and_triage(plan)
        lines.append(f"    Visible items: {execution_count}")
        if auto_count or triage_count:
            lines.append("    Plan clusters (all scopes):")
            if auto_count:
                names_str = ", ".join(auto_names)
                lines.append(
                    f"      Auto-queued: {auto_count} ({names_str})"
                )
            if triage_count:
                lines.append(f"      Triage-promoted: {triage_count}")
        if objective_backlog_count:
            lines.append(f"    Backlog: {objective_backlog_count} objective items (not in queue_order)")
    elif phase == LIFECYCLE_PHASE_WORKFLOW_POSTFLIGHT:
        lines.append(
            "    Why: Processing a planning step before execution resumes."
        )
        lines.append(
            f"    Blocked: {blocked_count} work items available after."
        )
    elif phase == LIFECYCLE_PHASE_TRIAGE_POSTFLIGHT:
        lines.append(
            "    Why: Analyzing and prioritizing issues before execution resumes."
        )
        lines.append(
            f"    Blocked: {blocked_count} work items available after."
        )
    elif phase == LIFECYCLE_PHASE_ASSESSMENT_POSTFLIGHT:
        lines.append(
            "    Why: Scoring dimensions from review results before execution resumes."
        )
        lines.append(
            f"    Blocked: {blocked_count} work items available after."
        )
    elif phase == LIFECYCLE_PHASE_REVIEW_POSTFLIGHT:
        lines.append(
            "    Why: Reviewing findings from the latest scan before execution resumes."
        )
        lines.append(
            f"    Blocked: {blocked_count} work items available after."
        )
    elif phase == LIFECYCLE_PHASE_SCAN:
        lines.append(
            "    Why: Cycle complete. Run `desloppify scan` to start the next one."
        )
    else:
        lines.append(f"    Visible items: {execution_count}")

    return "\n".join(lines)


__all__ = [
    "explain_queue",
]
