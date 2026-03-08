"""Unified work-queue selection for next/show/plan views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from desloppify.engine._plan.subjective_policy import NON_OBJECTIVE_DETECTORS
from desloppify.engine._work_queue.context import QueueContext
from desloppify.engine._work_queue.helpers import (
    ALL_STATUSES,
    ATTEST_EXAMPLE,
    scope_matches,
)
from desloppify.engine._work_queue.plan_order import (
    collapse_clusters,
    enrich_plan_metadata,
    separate_skipped,
    stamp_plan_sort_keys,
    stamp_positions,
)
from desloppify.engine._work_queue.plan_order import (
    new_item_ids as _new_item_ids,
)
from desloppify.engine._work_queue.ranking import (
    build_issue_items,
    enrich_with_impact,
    group_queue_items,
    item_explain,
    item_sort_key,
)
from desloppify.engine._work_queue.synthetic import (
    build_communicate_score_item,
    build_create_plan_item,
    build_import_scores_item,
    build_score_checkpoint_item,
    build_subjective_items,
    build_triage_stage_items,
)
from desloppify.engine._work_queue.types import WorkQueueItem
from desloppify.state import StateModel


class _ScanPathFromState:
    """Sentinel type: resolve scan_path from state."""


# Sentinel: "read scan_path from state" (the safe default).
# Callers that want to override can pass an explicit str or None.
_SCAN_PATH_FROM_STATE = _ScanPathFromState()
ScanPathOption = str | None | _ScanPathFromState


@dataclass(frozen=True)
class QueueBuildOptions:
    """Configuration for queue construction.

    ``scan_path`` defaults to reading from ``state["scan_path"]`` so callers
    don't need to thread it manually.  Pass an explicit ``str`` or ``None``
    to override (``None`` disables scope filtering).
    """

    # Output control
    count: int | None = 1
    explain: bool = False

    # Scope filtering
    scan_path: ScanPathOption = _SCAN_PATH_FROM_STATE
    scope: str | None = None
    status: str = "open"
    chronic: bool = False

    # Subjective gating
    include_subjective: bool = True
    subjective_threshold: float = 100.0

    # Plan integration
    plan: dict | None = None
    include_skipped: bool = False

    # Pre-computed context (overrides plan)
    context: QueueContext | None = None


class WorkQueueResult(TypedDict):
    """Typed shape of the dict returned by :func:`build_work_queue`."""

    items: list[WorkQueueItem]
    total: int
    grouped: dict[str, list[WorkQueueItem]]
    new_ids: set[str]


def build_work_queue(
    state: StateModel,
    *,
    options: QueueBuildOptions | None = None,
) -> WorkQueueResult:
    """Build a ranked work queue from state issues.

    Pipeline:
    1. Gather    — issue items, subjective dimensions, workflow stages
    2. Score     — estimate impact from dimension headroom
    3. Presort   — stamp plan positions, separate skipped items
    4. Lifecycle — filter endgame-only items when objective work remains
    5. Sort      — rank by impact/confidence, apply plan order
    6. Limit     — truncate to count, optionally add explain metadata
    """
    opts = options or QueueBuildOptions()
    plan, scan_path, status, threshold = _resolve_inputs(opts, state)

    # 1. Gather
    items = build_issue_items(
        state, scan_path=scan_path, status_filter=status,
        scope=opts.scope, chronic=opts.chronic,
    )
    items += _gather_subjective_items(state, opts, threshold)
    items += _gather_workflow_items(state, plan, status)

    # 2. Score
    enrich_with_impact(items, state.get("dimension_scores", {}))

    # 3. Plan-aware ordering (part 1: separate skipped items)
    new_ids, skipped = _plan_presort(items, state, plan)

    # 4. Lifecycle filter — endgame-only items filtered when objective work remains
    items = _apply_lifecycle_filter(items)

    # 5. Sort & plan post-processing
    items.sort(key=item_sort_key)
    _plan_postsort(items, skipped, plan, opts)

    # 6. Finalize
    if not items:
        items += _empty_queue_fallback(plan)
    total = len(items)
    if opts.count is not None and opts.count > 0:
        items = items[:opts.count]
    if opts.explain:
        for item in items:
            item["explain"] = item_explain(item)

    return {
        "items": items,
        "total": total,
        "grouped": group_queue_items(items, "item"),
        "new_ids": new_ids,
    }


# ---------------------------------------------------------------------------
# Pipeline helpers (private to this module)
# ---------------------------------------------------------------------------


def _resolve_inputs(
    opts: QueueBuildOptions, state: StateModel,
) -> tuple[dict | None, str | None, str, float]:
    """Resolve plan, scan_path, status, and subjective threshold from options."""
    ctx = opts.context
    plan = ctx.plan if ctx is not None else opts.plan

    scan_path: str | None = (
        state.get("scan_path")
        if isinstance(opts.scan_path, _ScanPathFromState)
        else opts.scan_path
    )

    status = opts.status
    if status not in ALL_STATUSES:
        raise ValueError(f"Unsupported status filter: {status}")

    try:
        threshold = float(opts.subjective_threshold)
    except (TypeError, ValueError):
        threshold = 100.0
    threshold = max(0.0, min(100.0, threshold))

    return plan, scan_path, status, threshold


def _gather_subjective_items(
    state: StateModel,
    opts: QueueBuildOptions,
    threshold: float,
) -> list[WorkQueueItem]:
    """Build subjective dimension candidates.

    Lifecycle filtering (endgame gating) happens in _apply_lifecycle_filter,
    not here. This function only handles configuration and scope.
    """
    if not opts.include_subjective:
        return []
    if opts.status not in {"open", "all"}:
        return []
    if opts.chronic:
        return []

    candidates = build_subjective_items(
        state, state.get("issues", {}), threshold=threshold,
    )
    return [item for item in candidates if scope_matches(item, opts.scope)]


def _gather_workflow_items(
    state: StateModel, plan: dict | None, status: str,
) -> list[WorkQueueItem]:
    """Inject triage stages, checkpoints, and create-plan when plan is active."""
    if not plan or status not in {"open", "all"}:
        return []

    items: list[WorkQueueItem] = list(build_triage_stage_items(plan, state))
    for builder in (
        build_score_checkpoint_item,
        build_import_scores_item,
        build_communicate_score_item,
    ):
        item = builder(plan, state)
        if item is not None:
            items.append(item)
    plan_item = build_create_plan_item(plan)
    if plan_item is not None:
        items.append(plan_item)
    return items



def _plan_presort(
    items: list[WorkQueueItem], state: StateModel, plan: dict | None,
) -> tuple[set[str], list[WorkQueueItem]]:
    """Enrich plan metadata and stamp sort keys before sorting.

    Returns ``(new_ids, skipped)`` — skipped items are removed from
    ``items`` in place and returned separately for post-sort re-append.
    """
    if not plan:
        return set(), []

    new_ids = _new_item_ids(state)
    enrich_plan_metadata(items, plan)
    stamp_plan_sort_keys(items, plan, new_ids)
    remaining, skipped = separate_skipped(items, plan)
    items[:] = remaining
    return new_ids, skipped


def _plan_postsort(
    items: list[WorkQueueItem],
    skipped: list[WorkQueueItem],
    plan: dict | None,
    opts: QueueBuildOptions,
) -> None:
    """Re-append skipped items and stamp positions.

    Cluster focus filtering is intentionally NOT applied here — it is a
    view-layer concern that callers apply after building the canonical queue.
    This prevents UI focus state from affecting lifecycle decisions (scan
    gating, score display mode, empty-queue fallback).
    """
    if not plan:
        return

    if opts.include_skipped:
        items.extend(skipped)
    stamp_positions(items, plan)


def _has_objective_items(items: list[WorkQueueItem]) -> bool:
    """True if any objective mechanical work items remain in the queue."""
    return any(
        i.get("kind") == "issue"
        and i.get("detector", "") not in NON_OBJECTIVE_DETECTORS
        for i in items
    )


def _has_initial_reviews(items: list[WorkQueueItem]) -> bool:
    """True if any unassessed subjective dimensions need initial review."""
    return any(
        i.get("kind") == "subjective_dimension"
        and i.get("initial_review")
        for i in items
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
        i.get("kind") == "workflow_stage"
        and str(i.get("id", "")).startswith("triage::")
        for i in items
    )


def _apply_lifecycle_filter(items: list[WorkQueueItem]) -> list[WorkQueueItem]:
    """Enforce lifecycle visibility rules.

    The queue enforces a phase order: scan → initial review → triage → objective work.

    1. **Initial reviews pending** → only show initial-review subjective items.
       The user must complete first-time reviews before working objective items.
    2. **Triage in progress** → only show triage stages and workflow items.
       Cluster work items aren't ready until triage completes (enrich adds
       the detail that makes steps actionable).
    3. **Objective work remains** → show objective items, hide endgame-only
       subjective reassessments (stale re-reviews).
    4. **Objective drained** → everything visible (endgame).
    """
    if _has_initial_reviews(items):
        # Phase 1: only initial reviews visible — triage and workflow
        # items stay hidden until initial reviews are complete.
        return [
            i for i in items
            if i.get("kind") == "subjective_dimension" and i.get("initial_review")
        ]
    if _has_triage_stages(items):
        # Phase 2: triage in progress — only triage stages and workflow items visible.
        # Cluster work items aren't ready until enrich completes.
        return [
            i for i in items
            if i.get("kind") in ("workflow_stage", "workflow_action")
        ]
    if not _has_objective_items(items):
        return items  # endgame: everything visible
    return [i for i in items if not _is_endgame_only(i)]


def _empty_queue_fallback(plan: dict | None) -> list[WorkQueueItem]:
    """Return a 'run scan' nudge when an active plan cycle has cleared."""
    if not plan:
        return []
    plan_scores = plan.get("plan_start_scores", {})
    if plan_scores.get("strict") is None:
        return []
    return [{
        "id": "workflow::run-scan",
        "kind": "workflow_action",
        "summary": "Queue cleared \u2014 run scan to finalize and reveal your updated score.",
        "primary_command": "desloppify scan",
        "file": "",
        "detector": "workflow",
        "confidence": "high",
    }]


__all__ = [
    "ATTEST_EXAMPLE",
    "QueueBuildOptions",
    "QueueContext",
    "WorkQueueResult",
    "build_work_queue",
    "collapse_clusters",
    "group_queue_items",
]
