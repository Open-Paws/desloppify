"""Shared boundary-triggered plan reconciliation pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from desloppify.state_scoring import score_snapshot
from desloppify.engine._plan.auto_cluster import auto_cluster_issues
from desloppify.engine._plan.constants import (
    PRE_REVIEW_WORKFLOW_IDS,
    QueueSyncResult,
    is_synthetic_id,
)
from desloppify.engine._plan.operations.meta import append_log_entry
from desloppify.engine._plan.policy.subjective import compute_subjective_visibility
from desloppify.engine._plan.policy.stale import open_review_ids
from desloppify.engine._plan.refresh_lifecycle import (
    LIFECYCLE_PHASE_ASSESSMENT_POSTFLIGHT,
    LIFECYCLE_PHASE_EXECUTE,
    LIFECYCLE_PHASE_REVIEW_INITIAL,
    LIFECYCLE_PHASE_REVIEW_POSTFLIGHT,
    LIFECYCLE_PHASE_SCAN,
    LIFECYCLE_PHASE_TRIAGE_POSTFLIGHT,
    LIFECYCLE_PHASE_WORKFLOW_POSTFLIGHT,
    current_lifecycle_phase,
    set_lifecycle_phase,
)
from desloppify.engine._plan.sync.dimensions import sync_subjective_dimensions
from desloppify.engine._plan.sync.phase_cleanup import prune_synthetic_for_phase
from desloppify.engine._plan.sync.triage import sync_triage_needed
from desloppify.engine._plan.triage.snapshot import build_triage_snapshot
from desloppify.engine._plan.sync.workflow import (
    ScoreSnapshot,
    sync_communicate_score_needed,
    sync_create_plan_needed,
)


@dataclass
class ReconcileResult:
    """Mutation summary for one boundary-triggered reconcile pass."""

    subjective: QueueSyncResult | None = None
    auto_cluster_changes: int = 0
    communicate_score: QueueSyncResult | None = None
    create_plan: QueueSyncResult | None = None
    triage: QueueSyncResult | None = None
    lifecycle_phase: str = ""
    lifecycle_phase_changed: bool = False
    phase_cleanup_pruned: list[str] | None = None

    @property
    def dirty(self) -> bool:
        return any(
            (
                self.subjective is not None and bool(self.subjective.changes),
                self.auto_cluster_changes > 0,
                self.communicate_score is not None
                and bool(self.communicate_score.changes),
                self.create_plan is not None
                and bool(self.create_plan.changes),
                self.triage is not None
                and bool(
                    self.triage.changes
                    or getattr(self.triage, "deferred", False)
                ),
                self.lifecycle_phase_changed,
                bool(self.phase_cleanup_pruned),
            )
        )

    @property
    def workflow_injected_ids(self) -> list[str]:
        injected: list[str] = []
        for result in (self.communicate_score, self.create_plan):
            if result is None:
                continue
            injected.extend(list(result.injected))
        return injected


def _current_scores(state: dict) -> ScoreSnapshot:
    snapshot = score_snapshot(state)
    return ScoreSnapshot(
        strict=snapshot.strict,
        overall=snapshot.overall,
        objective=snapshot.objective,
        verified=snapshot.verified,
    )


def _log_gate_changes(plan: dict, action: str, detail: dict[str, object]) -> None:
    append_log_entry(plan, action, actor="system", detail=detail)


def _resolve_reconcile_display_phase(
    plan: dict,
    state: dict,
    *,
    result: ReconcileResult,
    policy: object | None,
) -> str:
    """Derive the display phase from queue contents.

    Returns a SHORT display name (review, assessment, workflow, triage,
    execute, scan) — never a persisted mode.
    """
    order = [item for item in plan.get("queue_order", []) if isinstance(item, str)]

    if any(item in PRE_REVIEW_WORKFLOW_IDS for item in order):
        return LIFECYCLE_PHASE_WORKFLOW_POSTFLIGHT

    subjective_ids = [item for item in order if item.startswith("subjective::")]
    if subjective_ids:
        unscored_ids = set(getattr(policy, "unscored_ids", ()) or ())
        if any(item in unscored_ids for item in subjective_ids):
            return LIFECYCLE_PHASE_REVIEW_INITIAL
        return LIFECYCLE_PHASE_ASSESSMENT_POSTFLIGHT

    if result.workflow_injected_ids or any(item.startswith("workflow::") for item in order):
        return LIFECYCLE_PHASE_WORKFLOW_POSTFLIGHT

    if result.triage and (result.triage.injected or result.triage.deferred):
        return LIFECYCLE_PHASE_TRIAGE_POSTFLIGHT
    if any(item.startswith("triage::") for item in order):
        return LIFECYCLE_PHASE_TRIAGE_POSTFLIGHT

    triage_snapshot = build_triage_snapshot(plan, state)
    if (
        triage_snapshot.triage_has_run
        and not triage_snapshot.has_triage_in_queue
        and not triage_snapshot.is_triage_stale
        and bool(triage_snapshot.live_open_ids)
    ):
        return LIFECYCLE_PHASE_REVIEW_POSTFLIGHT

    # Check for objective work in the queue.
    has_real_work = any(
        not item.startswith(("subjective::", "workflow::", "triage::"))
        for item in order
        if item not in (plan.get("skipped") or {})
    )
    if has_real_work:
        return LIFECYCLE_PHASE_EXECUTE

    if open_review_ids(state):
        return LIFECYCLE_PHASE_REVIEW_POSTFLIGHT
    return LIFECYCLE_PHASE_SCAN


def _display_phase_to_mode(display_phase: str) -> str:
    """Map a display phase to the persisted mode ("plan" or "execute")."""
    if display_phase == LIFECYCLE_PHASE_EXECUTE:
        return "execute"
    return "plan"


_MIGRATION_PRUNED_KEY = "_subjective_migration_pruned"


def _migrate_prune_stale_subjective(plan: dict) -> None:
    """One-time migration: remove stale subjective:: items from queue_order.

    The old system re-injected stale subjective items on every reconcile
    (not just at boundaries).  With boundary-only sync, these won't be
    re-added, but old plan files may still have them.  Prune them so they
    don't pollute phase derivation.  Runs at most once per plan.
    """
    refresh_state = plan.get("refresh_state")
    if not isinstance(refresh_state, dict):
        return
    if refresh_state.get(_MIGRATION_PRUNED_KEY):
        return  # Already done
    queue_order = plan.get("queue_order")
    if not isinstance(queue_order, list):
        return
    cleaned = [
        item_id for item_id in queue_order
        if not (isinstance(item_id, str) and item_id.startswith("subjective::"))
    ]
    if len(cleaned) < len(queue_order):
        plan["queue_order"] = cleaned
    refresh_state[_MIGRATION_PRUNED_KEY] = True


def live_planned_queue_empty(plan: dict) -> bool:
    """Return True when queue_order has no remaining substantive items.

    Overrides and clusters are ownership metadata — they must never expand
    the live queue.  Only explicit ``queue_order`` entries count.
    """
    order = plan.get("queue_order", [])
    skipped = plan.get("skipped", {})
    return not any(
        isinstance(item_id, str)
        and item_id not in skipped
        and not is_synthetic_id(item_id)
        for item_id in order
    )


def reconcile_plan(
    plan: dict,
    state: dict,
    *,
    target_strict: float,
    force_rescan: bool = False,
) -> ReconcileResult:
    """Run the shared boundary reconciliation pipeline."""
    result = ReconcileResult()

    # Migration cleanup: prune stale subjective items from queue_order
    # left by the old mid-cycle re-injection bug.  With boundary-only sync
    # they won't be re-added, so they just block phase resolution.
    _migrate_prune_stale_subjective(plan)

    policy = compute_subjective_visibility(
        state,
        target_strict=target_strict,
        plan=plan,
    )

    result.subjective = sync_subjective_dimensions(
        plan,
        state,
        policy=policy,
    )
    if result.subjective.changes:
        _log_gate_changes(plan, "sync_subjective", {"changes": True})

    # Auto-clustering and heavier workflow reconciliation only runs at queue boundaries.
    if live_planned_queue_empty(plan) or force_rescan:
        result.auto_cluster_changes = int(
            auto_cluster_issues(
                plan,
                state,
                target_strict=target_strict,
                policy=policy,
            )
        )
        if result.auto_cluster_changes:
            _log_gate_changes(plan, "auto_cluster", {"changes": True})

        result.communicate_score = sync_communicate_score_needed(
            plan,
            state,
            policy=policy,
            current_scores=_current_scores(state),
        )
        if result.communicate_score.changes:
            _log_gate_changes(plan, "sync_communicate_score", {"injected": True})

        result.create_plan = sync_create_plan_needed(
            plan,
            state,
            policy=policy,
        )
        if result.create_plan.changes:
            _log_gate_changes(plan, "sync_create_plan", {"injected": True})

        result.triage = sync_triage_needed(
            plan,
            state,
            policy=policy,
        )
        if result.triage.injected:
            _log_gate_changes(plan, "sync_triage", {"injected": True})

    result.lifecycle_phase = _resolve_reconcile_display_phase(
        plan,
        state,
        result=result,
        policy=policy,
    )
    mode = _display_phase_to_mode(result.lifecycle_phase)
    result.lifecycle_phase_changed = set_lifecycle_phase(plan, mode)
    if result.lifecycle_phase_changed:
        _log_gate_changes(
            plan,
            "sync_lifecycle_phase",
            {"phase": result.lifecycle_phase},
        )

    result.phase_cleanup_pruned = prune_synthetic_for_phase(plan, result.lifecycle_phase)
    if result.phase_cleanup_pruned:
        _log_gate_changes(
            plan,
            "phase_transition_cleanup",
            {"phase": result.lifecycle_phase, "pruned": list(result.phase_cleanup_pruned)},
        )

    return result


__all__ = ["ReconcileResult", "live_planned_queue_empty", "reconcile_plan"]
