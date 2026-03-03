"""Ranking and grouping helpers for work queue selection."""

from __future__ import annotations

from desloppify.engine._work_queue.helpers import (
    ACTION_TYPE_PRIORITY,
    detail_dict,
    is_review_issue,
    is_subjective_issue,
    primary_command_for_issue,
    review_issue_weight,
    scope_matches,
    slugify,
    status_matches,
    supported_fixers_for_item,
)
from desloppify.engine._work_queue.synthetic import subjective_strict_scores
from desloppify.core.registry import DETECTORS
from desloppify.engine.planning.common import CONFIDENCE_ORDER
from desloppify.state import path_scoped_issues

# Plan-aware sort tiers (item_sort_key)
_TIER_PLANNED = 0   # Items with explicit plan position
_TIER_EXISTING = 1  # Known items, natural ranking
_TIER_NEW = 2       # Newly discovered items

# Natural ranking groups (_natural_sort_key)
_RANK_INITIAL_REVIEW = -3  # Unassessed subjective dimensions
_RANK_TRIAGE_STAGE = -2    # Epic triage workflow stages
_RANK_WORKFLOW = -1         # Score checkpoints, create-plan
_RANK_CLUSTER = 0           # Auto-clustered issues
_RANK_ISSUE = 1           # Individual issues + assessed subjective


def enrich_with_impact(items: list[dict], dimension_scores: dict) -> None:
    """Stamp ``estimated_impact`` on each item based on dimension-level headroom.

    Impact = ``overall_per_point * headroom`` where headroom = ``100 - score``.
    Items in dimensions with more score headroom sort first.
    """
    if not dimension_scores:
        for item in items:
            item["estimated_impact"] = 0.0
        return

    from desloppify.engine._scoring.results.health import compute_health_breakdown
    from desloppify.engine._scoring.results.impact import get_dimension_for_detector

    breakdown = compute_health_breakdown(dimension_scores)
    entries = breakdown.get("entries", [])

    # Build lookup: normalized dimension name -> {per_point, headroom}
    dim_impact: dict[str, dict[str, float]] = {}
    for entry in entries:
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        per_point = float(entry.get("overall_per_point", 0.0))
        score = float(entry.get("score", 0.0))
        headroom = 100.0 - score
        dim_impact[name.lower()] = {"per_point": per_point, "headroom": headroom}

    for item in items:
        impact = _compute_item_impact(item, dim_impact, get_dimension_for_detector)
        item["estimated_impact"] = impact


def _compute_item_impact(
    item: dict,
    dim_impact: dict[str, dict[str, float]],
    get_dimension_for_detector,
) -> float:
    """Compute impact value for a single queue item."""
    kind = item.get("kind", "issue")

    # Subjective items (synthetic dimensions or subjective issues):
    # look up by detail.dimension_name
    if kind == "subjective_dimension" or item.get("is_subjective"):
        dim_name = detail_dict(item).get("dimension_name", "")
        entry = dim_impact.get(dim_name.lower())
        if entry:
            return entry["per_point"] * entry["headroom"]
        return 0.0

    # Mechanical issues: use detector -> dimension mapping
    detector = item.get("detector", "")
    if detector:
        dimension = get_dimension_for_detector(detector)
        if dimension:
            entry = dim_impact.get(dimension.name.lower())
            if entry:
                return entry["per_point"] * entry["headroom"]

    return 0.0


def subjective_score_value(item: dict) -> float:
    if item.get("kind") == "subjective_dimension":
        detail = detail_dict(item)
        return float(detail.get("strict_score", item.get("subjective_score", 100.0)))
    return float(item.get("subjective_score", 100.0))


def build_issue_items(
    state: dict,
    *,
    scan_path: str | None,
    status_filter: str,
    scope: str | None,
    chronic: bool,
) -> list[dict]:
    scoped = path_scoped_issues(state.get("issues", {}), scan_path)
    subjective_scores = subjective_strict_scores(state)
    out: list[dict] = []

    for issue_id, issue in scoped.items():
        if issue.get("suppressed"):
            continue
        if not status_matches(issue.get("status", "open"), status_filter):
            continue
        if chronic and not (
            issue.get("status") == "open" and issue.get("reopen_count", 0) >= 2
        ):
            continue

        # Evidence-only: skip issues below standalone confidence threshold
        detector = issue.get("detector", "")
        meta = DETECTORS.get(detector)
        if meta and meta.standalone_threshold:
            threshold_rank = CONFIDENCE_ORDER.get(meta.standalone_threshold, 9)
            issue_rank = CONFIDENCE_ORDER.get(issue.get("confidence", "low"), 9)
            if issue_rank > threshold_rank:
                continue

        item = dict(issue)
        item["id"] = issue_id
        item["kind"] = "issue"
        item["is_review"] = is_review_issue(item)
        item["is_subjective"] = is_subjective_issue(item)
        item["review_weight"] = (
            review_issue_weight(item) if item["is_review"] else None
        )
        subjective_score = None
        if item["is_subjective"]:
            detail = detail_dict(issue)
            dim_name = detail.get("dimension_name", "")
            dim_key = detail.get("dimension", "") or slugify(dim_name)
            subjective_score = subjective_scores.get(
                dim_key, subjective_scores.get(dim_name.lower(), 100.0)
            )
        item["subjective_score"] = subjective_score
        supported_fixers = supported_fixers_for_item(state, item)
        item["primary_command"] = primary_command_for_issue(
            item,
            supported_fixers=supported_fixers,
        )

        if not scope_matches(item, scope):
            continue
        out.append(item)

    return out


def _natural_sort_key(item: dict) -> tuple:
    """Compute natural (non-plan-aware) ranking for queue items."""
    kind = item.get("kind", "issue")

    # Initial-review subjective items: highest priority
    if kind == "subjective_dimension" and item.get("initial_review"):
        return (_RANK_INITIAL_REVIEW, 0, subjective_score_value(item), item.get("id", ""))

    # Triage stage items: stage order, blocked after unblocked
    if kind == "workflow_stage":
        blocked_penalty = 1 if item.get("is_blocked") else 0
        stage_index = int(item.get("stage_index", 0))
        return (_RANK_TRIAGE_STAGE, blocked_penalty, stage_index, item.get("id", ""))

    # Workflow action items (e.g. create-plan)
    if kind == "workflow_action":
        return (_RANK_WORKFLOW, 0, 0, item.get("id", ""))

    if kind == "cluster":
        # Clusters sort before individual issues, ordered by action type
        action_pri = ACTION_TYPE_PRIORITY.get(
            item.get("action_type", "manual_fix"), 3
        )
        return (
            _RANK_CLUSTER,
            action_pri,
            -int(item.get("member_count", 0)),
            item.get("id", ""),
        )

    impact = item.get("estimated_impact", 0.0)

    if kind == "subjective_dimension" or item.get("is_subjective"):
        return (
            _RANK_ISSUE,
            -impact,
            subjective_score_value(item),
            item.get("id", ""),
        )

    detail = detail_dict(item)
    review_weight = float(item.get("review_weight", 0.0) or 0.0)
    return (
        _RANK_ISSUE,
        -impact,
        CONFIDENCE_ORDER.get(item.get("confidence", "low"), 9),
        -review_weight,
        -int(detail.get("count", 0) or 0),
        item.get("id", ""),
    )


def item_sort_key(item: dict) -> tuple:
    """Unified sort key: plan position first, then natural ranking.

    When ``_plan_position`` is stamped (by :func:`stamp_plan_sort_keys`),
    planned items sort first in plan order, then existing items by natural
    ranking, then newly-discovered items by natural ranking.

    When no plan fields are stamped, falls back to pure natural ranking.
    """
    plan_pos = item.get("_plan_position")

    if plan_pos is not None:
        kind = item.get("kind", "issue")
        # Triage stages: even when explicitly planned, maintain the
        # blocked-before-unblocked invariant for correctness.
        if kind == "workflow_stage":
            blocked = 1 if item.get("is_blocked") else 0
            stage_idx = int(item.get("stage_index", 0))
            return (_TIER_PLANNED, blocked, stage_idx, item.get("id", ""))
        return (_TIER_PLANNED, 0, plan_pos, item.get("id", ""))

    is_new = item.get("_is_new", False)
    group = _TIER_NEW if is_new else _TIER_EXISTING
    return (group, *_natural_sort_key(item))


def item_explain(item: dict) -> dict:
    kind = item.get("kind", "issue")
    if kind == "workflow_stage":
        return {
            "kind": "workflow_stage",
            "stage": item.get("stage_name"),
            "is_blocked": item.get("is_blocked", False),
            "blocked_by": item.get("blocked_by", []),
            "policy": "Triage stages sort by dependency order; blocked stages follow unblocked.",
            "ranking_factors": ["blocked_penalty asc", "stage_index asc"],
        }

    if kind == "workflow_action":
        return {
            "kind": "workflow_action",
            "policy": "Workflow items sort after triage stages, before issues.",
            "ranking_factors": ["id asc"],
        }

    if kind == "cluster":
        return {
            "kind": "cluster",
            "estimated_impact": item.get("estimated_impact", 0.0),
            "action_type": item.get("action_type", "manual_fix"),
            "member_count": item.get("member_count", 0),
            "policy": "Clusters sort before individual issues, ordered by action type then size.",
            "ranking_factors": ["action_type asc", "member_count desc", "id asc"],
        }

    if kind == "subjective_dimension":
        initial = item.get("initial_review", False)
        return {
            "kind": "subjective_dimension",
            "estimated_impact": item.get("estimated_impact", 0.0),
            "subjective_score": subjective_score_value(item),
            "initial_review": initial,
            "policy": (
                "Initial review items sort first (onboarding priority)."
                if initial else
                "Sorted by dimension impact (score headroom × weight), then subjective score."
            ),
            "ranking_factors": ["estimated_impact desc", "subjective_score asc", "id asc"],
        }

    detail = detail_dict(item)
    confidence = item.get("confidence", "low")
    is_subjective = bool(item.get("is_subjective"))
    is_review = bool(item.get("is_review"))
    ranking_factors: list[str]
    if is_subjective:
        ranking_factors = ["estimated_impact desc", "subjective_score asc", "id asc"]
    elif is_review:
        ranking_factors = [
            "estimated_impact desc",
            "confidence asc",
            "review_weight desc",
            "count desc",
            "id asc",
        ]
    else:
        ranking_factors = ["estimated_impact desc", "confidence asc", "count desc", "id asc"]
    explain = {
        "kind": "issue",
        "estimated_impact": item.get("estimated_impact", 0.0),
        "confidence": confidence,
        "confidence_rank": CONFIDENCE_ORDER.get(confidence, 9),
        "count": int(detail.get("count", 0) or 0),
        "id": item.get("id", ""),
        "ranking_factors": ranking_factors,
    }
    if is_review:
        explain["review_weight"] = float(item.get("review_weight", 0.0) or 0.0)
    if is_subjective:
        explain["policy"] = (
            "Sorted by dimension impact (score headroom × weight), then subjective score."
        )
        explain["subjective_score"] = subjective_score_value(item)
    return explain


def group_queue_items(items: list[dict], group: str) -> dict[str, list[dict]]:
    """Group queue items for alternate output modes."""
    grouped: dict[str, list[dict]] = {}
    for item in items:
        if group == "file":
            key = item.get("file", "")
        elif group == "detector":
            key = item.get("detector", "")
        elif group == "cluster":
            plan_cluster = item.get("plan_cluster")
            key = plan_cluster["name"] if isinstance(plan_cluster, dict) else "(unclustered)"
        else:
            key = "items"
        grouped.setdefault(key, []).append(item)
    return grouped


__all__ = [
    "build_issue_items",
    "enrich_with_impact",
    "item_explain",
    "item_sort_key",
    "subjective_score_value",
    "group_queue_items",
]
