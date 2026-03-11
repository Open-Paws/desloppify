"""Helpers for the persisted queue lifecycle phase.

The persisted phase is the normal source of truth for CLI/debugging, but it is
not trusted blindly. Queue assembly still re-resolves the active phase from the
currently visible items as a safety net so stale saved state cannot strand the
user in the wrong phase after out-of-band changes.
"""

from __future__ import annotations

from typing import Iterable

from desloppify.engine._plan.constants import SYNTHETIC_PREFIXES
from desloppify.engine._plan.schema import PlanModel, ensure_plan_defaults

_POSTFLIGHT_SCAN_KEY = "postflight_scan_completed_at_scan_count"
_LIFECYCLE_PHASE_KEY = "lifecycle_phase"

LIFECYCLE_PHASE_SCAN = "scan"
LIFECYCLE_PHASE_REVIEW = "review"
LIFECYCLE_PHASE_WORKFLOW = "workflow"
LIFECYCLE_PHASE_TRIAGE = "triage"
LIFECYCLE_PHASE_EXECUTE = "execute"
VALID_LIFECYCLE_PHASES = frozenset(
    {
        LIFECYCLE_PHASE_SCAN,
        LIFECYCLE_PHASE_REVIEW,
        LIFECYCLE_PHASE_WORKFLOW,
        LIFECYCLE_PHASE_TRIAGE,
        LIFECYCLE_PHASE_EXECUTE,
    }
)


def _refresh_state(plan: PlanModel) -> dict[str, object]:
    ensure_plan_defaults(plan)
    refresh_state = plan.get("refresh_state")
    if not isinstance(refresh_state, dict):
        refresh_state = {}
        plan["refresh_state"] = refresh_state
    return refresh_state


def _is_real_queue_issue(issue_id: str) -> bool:
    return not any(str(issue_id).startswith(prefix) for prefix in SYNTHETIC_PREFIXES)


def current_lifecycle_phase(plan: PlanModel) -> str | None:
    """Return the persisted lifecycle phase, falling back for legacy plans."""
    refresh_state = plan.get("refresh_state")
    if isinstance(refresh_state, dict):
        phase = refresh_state.get(_LIFECYCLE_PHASE_KEY)
        if isinstance(phase, str) and phase in VALID_LIFECYCLE_PHASES:
            return phase
    if postflight_scan_pending(plan):
        return LIFECYCLE_PHASE_SCAN
    if plan.get("plan_start_scores"):
        return LIFECYCLE_PHASE_EXECUTE
    return None


def set_lifecycle_phase(plan: PlanModel, phase: str) -> bool:
    """Persist the current queue lifecycle phase."""
    if phase not in VALID_LIFECYCLE_PHASES:
        raise ValueError(f"Unsupported lifecycle phase: {phase}")
    refresh_state = _refresh_state(plan)
    if refresh_state.get(_LIFECYCLE_PHASE_KEY) == phase:
        return False
    refresh_state[_LIFECYCLE_PHASE_KEY] = phase
    return True


def sync_lifecycle_phase(
    plan: PlanModel,
    *,
    has_initial_reviews: bool,
    has_objective_backlog: bool,
    has_postflight_review: bool,
    has_postflight_workflow: bool,
    has_triage: bool,
    has_deferred: bool,
) -> tuple[str, bool]:
    """Resolve and persist the current lifecycle phase from queue-state facts."""
    phase = resolve_lifecycle_phase(
        plan,
        has_initial_reviews=has_initial_reviews,
        has_objective_backlog=has_objective_backlog,
        has_postflight_review=has_postflight_review,
        has_postflight_workflow=has_postflight_workflow,
        has_triage=has_triage,
        has_deferred=has_deferred,
    )
    return phase, set_lifecycle_phase(plan, phase)


def resolve_lifecycle_phase(
    plan: PlanModel,
    *,
    has_initial_reviews: bool,
    has_objective_backlog: bool,
    has_postflight_review: bool,
    has_postflight_workflow: bool,
    has_triage: bool,
    has_deferred: bool,
) -> str:
    """Resolve the lifecycle phase from explicit queue-state facts."""
    if has_initial_reviews:
        return LIFECYCLE_PHASE_REVIEW
    if has_objective_backlog:
        return LIFECYCLE_PHASE_EXECUTE
    if has_deferred or postflight_scan_pending(plan):
        return LIFECYCLE_PHASE_SCAN
    if has_postflight_review:
        return LIFECYCLE_PHASE_REVIEW
    if has_postflight_workflow:
        return LIFECYCLE_PHASE_WORKFLOW
    if has_triage:
        return LIFECYCLE_PHASE_TRIAGE
    persisted = current_lifecycle_phase(plan)
    if persisted is not None:
        return persisted
    return LIFECYCLE_PHASE_SCAN


def postflight_scan_pending(plan: PlanModel) -> bool:
    """Return True when the current empty-queue boundary still needs a scan."""
    refresh_state = plan.get("refresh_state")
    if not isinstance(refresh_state, dict):
        return True
    return not isinstance(refresh_state.get(_POSTFLIGHT_SCAN_KEY), int)


def mark_postflight_scan_completed(
    plan: PlanModel,
    *,
    scan_count: int | None,
) -> bool:
    """Record that the scan stage completed for the current refresh cycle."""
    refresh_state = _refresh_state(plan)
    try:
        normalized_scan_count = int(scan_count or 0)
    except (TypeError, ValueError):
        normalized_scan_count = 0
    if refresh_state.get(_POSTFLIGHT_SCAN_KEY) == normalized_scan_count:
        return False
    refresh_state[_POSTFLIGHT_SCAN_KEY] = normalized_scan_count
    return True


def clear_postflight_scan_completion(
    plan: PlanModel,
    *,
    issue_ids: Iterable[str] | None = None,
) -> bool:
    """Require a fresh scan after queue-changing work on real issues."""
    if issue_ids is not None and not any(
        _is_real_queue_issue(issue_id) for issue_id in issue_ids
    ):
        return False
    refresh_state = _refresh_state(plan)
    if _POSTFLIGHT_SCAN_KEY not in refresh_state:
        return False
    refresh_state[_LIFECYCLE_PHASE_KEY] = LIFECYCLE_PHASE_EXECUTE
    refresh_state.pop(_POSTFLIGHT_SCAN_KEY, None)
    return True


__all__ = [
    "clear_postflight_scan_completion",
    "current_lifecycle_phase",
    "LIFECYCLE_PHASE_EXECUTE",
    "LIFECYCLE_PHASE_REVIEW",
    "LIFECYCLE_PHASE_SCAN",
    "LIFECYCLE_PHASE_TRIAGE",
    "LIFECYCLE_PHASE_WORKFLOW",
    "mark_postflight_scan_completed",
    "postflight_scan_pending",
    "resolve_lifecycle_phase",
    "set_lifecycle_phase",
    "sync_lifecycle_phase",
    "VALID_LIFECYCLE_PHASES",
]
