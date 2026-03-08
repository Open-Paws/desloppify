"""Lifecycle visibility filtering for work-queue items."""

from __future__ import annotations

from desloppify.engine._plan.subjective_policy import NON_OBJECTIVE_DETECTORS
from desloppify.engine._work_queue.types import WorkQueueItem


def _has_objective_items(items: list[WorkQueueItem]) -> bool:
    """True if any objective mechanical work items remain in the queue."""
    return any(
        item.get("kind") == "issue"
        and item.get("detector", "") not in NON_OBJECTIVE_DETECTORS
        for item in items
    )


def _has_initial_reviews(items: list[WorkQueueItem]) -> bool:
    """True if any unassessed subjective dimensions need initial review."""
    return any(
        item.get("kind") == "subjective_dimension"
        and item.get("initial_review")
        for item in items
    )


def _is_endgame_only(item: WorkQueueItem) -> bool:
    """True if this item should only appear when the objective queue is drained."""
    return (
        item.get("kind") == "subjective_dimension"
        and not item.get("initial_review")
    )


def _has_triage_stages(items: list[WorkQueueItem]) -> bool:
    """True if any pending triage stage items are in the queue."""
    return any(
        item.get("kind") == "workflow_stage"
        and str(item.get("id", "")).startswith("triage::")
        for item in items
    )


def _is_triage_stage(item: WorkQueueItem) -> bool:
    """True when item is a triage workflow stage."""
    return (
        item.get("kind") == "workflow_stage"
        and str(item.get("id", "")).startswith("triage::")
    )


def apply_lifecycle_filter(items: list[WorkQueueItem]) -> list[WorkQueueItem]:
    """Enforce lifecycle visibility rules."""
    if _has_initial_reviews(items):
        return [
            item for item in items
            if item.get("kind") == "subjective_dimension" and item.get("initial_review")
        ]
    if _has_triage_stages(items):
        # Triage should not block while objective queue work still exists.
        if _has_objective_items(items):
            return [
                item for item in items
                if not _is_triage_stage(item) and not _is_endgame_only(item)
            ]
        return [
            item for item in items
            if item.get("kind") in ("workflow_stage", "workflow_action")
        ]
    if not _has_objective_items(items):
        return items
    return [item for item in items if not _is_endgame_only(item)]


__all__ = ["apply_lifecycle_filter"]
