"""Helpers for the persisted queue lifecycle phase.

Persisted lifecycle is coarse: only ``"plan"`` or ``"execute"``.
Display-level phase names (review, assessment, workflow, triage, scan) are
derived from queue contents by snapshot.py and pipeline.py — never persisted.
"""

from __future__ import annotations

from typing import Iterable

from desloppify.engine._plan.constants import SYNTHETIC_PREFIXES
from desloppify.engine._plan.schema import PlanModel, ensure_plan_defaults
from desloppify.engine._state.issue_semantics import counts_toward_objective_backlog

_POSTFLIGHT_SCAN_KEY = "postflight_scan_completed_at_scan_count"
_SUBJECTIVE_REVIEW_KEY = "subjective_review_completed_at_scan_count"
_LIFECYCLE_PHASE_KEY = "lifecycle_phase"

# ── Display-only constants ──────────────────────────────────────────
# These are SHORT display names used by snapshot.py, pipeline.py, and
# consumers for phase-gated rendering.  They are NEVER persisted.
LIFECYCLE_PHASE_REVIEW_INITIAL = "review_initial"
LIFECYCLE_PHASE_ASSESSMENT_POSTFLIGHT = "assessment"
LIFECYCLE_PHASE_REVIEW_POSTFLIGHT = "review"
LIFECYCLE_PHASE_WORKFLOW_POSTFLIGHT = "workflow"
LIFECYCLE_PHASE_TRIAGE_POSTFLIGHT = "triage"
LIFECYCLE_PHASE_EXECUTE = "execute"
LIFECYCLE_PHASE_SCAN = "scan"

# Only these two values are persisted in refresh_state["lifecycle_phase"].
_VALID_PHASES = frozenset({"plan", "execute"})

# Data migration: ALL old phase names (fine-grained and coarse) map to a
# persisted mode.  This is the ONLY place legacy names are tolerated.
_LEGACY_PHASE_TO_MODE: dict[str, str] = {
    "review_initial": "plan",
    "assessment_postflight": "plan",
    "review_postflight": "plan",
    "workflow_postflight": "plan",
    "triage_postflight": "plan",
    "execute": "execute",
    "scan": "plan",
    "review": "plan",
    "workflow": "plan",
    "triage": "plan",
}


def _refresh_state(plan: PlanModel) -> dict[str, object]:
    ensure_plan_defaults(plan)
    refresh_state = plan.get("refresh_state")
    if not isinstance(refresh_state, dict):
        refresh_state = {}
        plan["refresh_state"] = refresh_state
    return refresh_state


def _is_real_queue_issue(issue_id: str) -> bool:
    return not any(str(issue_id).startswith(prefix) for prefix in SYNTHETIC_PREFIXES)


def _touches_objective_issue(
    *,
    issue_ids: Iterable[str] | None,
    state: dict[str, object] | None,
) -> bool:
    if issue_ids is None:
        return True

    real_issue_ids = [
        issue_id
        for issue_id in issue_ids
        if _is_real_queue_issue(str(issue_id))
    ]
    if not real_issue_ids:
        return False
    if not isinstance(state, dict):
        return True

    issues = state.get("work_items") or state.get("issues", {})
    if not isinstance(issues, dict):
        return True

    objective_seen = False
    for issue_id in real_issue_ids:
        issue = issues.get(issue_id)
        if not isinstance(issue, dict):
            return True
        if counts_toward_objective_backlog(issue):
            objective_seen = True
    return objective_seen


def current_lifecycle_phase(plan: PlanModel) -> str | None:
    """Return the persisted lifecycle mode: ``"plan"`` or ``"execute"``.

    Migrates any legacy fine-grained phase name on read.
    """
    refresh_state = plan.get("refresh_state")
    if isinstance(refresh_state, dict):
        phase = refresh_state.get(_LIFECYCLE_PHASE_KEY)
        if isinstance(phase, str):
            if phase in _VALID_PHASES:
                return phase
            # Data migration: old fine-grained or coarse names → mode.
            migrated = _LEGACY_PHASE_TO_MODE.get(phase)
            if migrated is not None:
                # If the old phase maps to "plan" but the plan work is
                # actually complete (no plan-mode items remain in queue),
                # the project was stuck due to the old mid-cycle
                # re-injection bug.  Use "execute" instead.
                if migrated == "plan" and plan.get("plan_start_scores"):
                    queue_order = plan.get("queue_order", [])
                    has_plan_work = any(
                        isinstance(item_id, str) and (
                            item_id.startswith("workflow::")
                            or item_id.startswith("triage::")
                        )
                        for item_id in queue_order
                    )
                    if not has_plan_work:
                        migrated = "execute"
                # Persist the migration so it only happens once.
                refresh_state[_LIFECYCLE_PHASE_KEY] = migrated
                return migrated
    if postflight_scan_pending(plan):
        return "plan"
    if plan.get("plan_start_scores"):
        return "execute"
    return None


def set_lifecycle_phase(plan: PlanModel, phase: str) -> bool:
    """Persist the current queue lifecycle mode (``"plan"`` or ``"execute"``)."""
    if phase not in _VALID_PHASES:
        raise ValueError(f"Unsupported lifecycle phase: {phase}")
    refresh_state = _refresh_state(plan)
    if refresh_state.get(_LIFECYCLE_PHASE_KEY) == phase:
        return False
    refresh_state[_LIFECYCLE_PHASE_KEY] = phase
    return True


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


def subjective_review_completed_for_scan(
    plan: PlanModel,
    *,
    scan_count: int | None,
) -> bool:
    """Return True when postflight subjective review finished for *scan_count*."""
    refresh_state = plan.get("refresh_state")
    if not isinstance(refresh_state, dict):
        return False
    try:
        normalized_scan_count = int(scan_count or 0)
    except (TypeError, ValueError):
        normalized_scan_count = 0
    return refresh_state.get(_SUBJECTIVE_REVIEW_KEY) == normalized_scan_count


def mark_subjective_review_completed(
    plan: PlanModel,
    *,
    scan_count: int | None,
) -> bool:
    """Record that subjective review completed for the current postflight scan."""
    refresh_state = _refresh_state(plan)
    try:
        normalized_scan_count = int(scan_count or 0)
    except (TypeError, ValueError):
        normalized_scan_count = 0
    if refresh_state.get(_SUBJECTIVE_REVIEW_KEY) == normalized_scan_count:
        return False
    refresh_state[_SUBJECTIVE_REVIEW_KEY] = normalized_scan_count
    return True


def clear_postflight_scan_completion(
    plan: PlanModel,
    *,
    issue_ids: Iterable[str] | None = None,
    state: dict[str, object] | None = None,
) -> bool:
    """Require a fresh scan after queue-changing work on objective issues."""
    if not _touches_objective_issue(issue_ids=issue_ids, state=state):
        return False
    refresh_state = _refresh_state(plan)
    if _POSTFLIGHT_SCAN_KEY not in refresh_state:
        return False
    refresh_state[_LIFECYCLE_PHASE_KEY] = "execute"
    refresh_state.pop(_POSTFLIGHT_SCAN_KEY, None)
    return True


__all__ = [
    "LIFECYCLE_PHASE_ASSESSMENT_POSTFLIGHT",
    "LIFECYCLE_PHASE_EXECUTE",
    "LIFECYCLE_PHASE_REVIEW_INITIAL",
    "LIFECYCLE_PHASE_REVIEW_POSTFLIGHT",
    "LIFECYCLE_PHASE_SCAN",
    "LIFECYCLE_PHASE_TRIAGE_POSTFLIGHT",
    "LIFECYCLE_PHASE_WORKFLOW_POSTFLIGHT",
    "clear_postflight_scan_completion",
    "current_lifecycle_phase",
    "mark_postflight_scan_completed",
    "mark_subjective_review_completed",
    "postflight_scan_pending",
    "set_lifecycle_phase",
    "subjective_review_completed_for_scan",
]
