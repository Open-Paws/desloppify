"""Pure policy helpers for stale/unscored subjective planning decisions."""

from __future__ import annotations

import hashlib

from desloppify.base.config import DEFAULT_TARGET_STRICT_SCORE
from desloppify.engine._state.schema import StateModel
from desloppify.engine._work_queue.helpers import slugify
from desloppify.engine.planning.scorecard_projection import all_subjective_entries

_REVIEW_DETECTORS = ("review", "concerns", "subjective_review")


def current_stale_ids(
    state: StateModel,
    *,
    subjective_prefix: str = "subjective::",
) -> set[str]:
    """Return ``subjective::<slug>`` IDs that are currently stale."""
    dim_scores = state.get("dimension_scores", {}) or {}
    if not dim_scores:
        return set()

    stale: set[str] = set()
    for entry in all_subjective_entries(state, dim_scores=dim_scores):
        if not entry.get("stale"):
            continue
        dim_key = entry.get("dimension_key", "")
        if dim_key:
            stale.add(f"{subjective_prefix}{slugify(dim_key)}")
    return stale


def current_unscored_ids(
    state: StateModel,
    *,
    subjective_prefix: str = "subjective::",
) -> set[str]:
    """Return ``subjective::<slug>`` IDs that are currently unscored."""
    assessments = state.get("subjective_assessments")
    if isinstance(assessments, dict) and assessments:
        unscored: set[str] = set()
        for dim_key, payload in assessments.items():
            if not isinstance(payload, dict):
                continue
            if not payload.get("placeholder"):
                continue
            if dim_key:
                unscored.add(f"{subjective_prefix}{slugify(dim_key)}")
        return unscored

    dim_scores = state.get("dimension_scores", {}) or {}
    if not dim_scores:
        return set()

    unscored = set()
    for data in dim_scores.values():
        if not isinstance(data, dict):
            continue
        detectors = data.get("detectors", {})
        meta = detectors.get("subjective_assessment")
        if not isinstance(meta, dict):
            continue
        if not meta.get("placeholder"):
            continue
        dim_key = meta.get("dimension_key", "")
        if dim_key:
            unscored.add(f"{subjective_prefix}{slugify(dim_key)}")
    return unscored


def current_under_target_ids(
    state: StateModel,
    *,
    target_strict: float = DEFAULT_TARGET_STRICT_SCORE,
    subjective_prefix: str = "subjective::",
) -> set[str]:
    """Return under-target subjective IDs that are neither stale nor unscored."""
    dim_scores = state.get("dimension_scores", {}) or {}
    if not dim_scores:
        return set()

    stale_ids = current_stale_ids(state, subjective_prefix=subjective_prefix)
    unscored_ids = current_unscored_ids(state, subjective_prefix=subjective_prefix)

    under_target: set[str] = set()
    for entry in all_subjective_entries(state, dim_scores=dim_scores):
        if entry.get("placeholder") or entry.get("stale"):
            continue
        strict_val = float(entry.get("strict", entry.get("score", 100.0)))
        if strict_val >= target_strict:
            continue
        dim_key = entry.get("dimension_key", "")
        if not dim_key:
            continue
        item_id = f"{subjective_prefix}{slugify(dim_key)}"
        if item_id not in stale_ids and item_id not in unscored_ids:
            under_target.add(item_id)
    return under_target


def review_issue_snapshot_hash(state: StateModel) -> str:
    """Hash open review/concerns issue IDs to detect triage-relevant changes."""
    issues = state.get("issues", {})
    review_ids = sorted(
        issue_id
        for issue_id, issue in issues.items()
        if issue.get("status") == "open" and issue.get("detector") in _REVIEW_DETECTORS
    )
    if not review_ids:
        return ""
    return hashlib.sha256("|".join(review_ids).encode()).hexdigest()[:16]


def compute_new_issue_ids(plan: dict, state: StateModel) -> set[str]:
    """Return open review/concerns IDs that appeared since the last triage."""
    meta = plan.get("epic_triage_meta", {})
    triaged = set(meta.get("triaged_ids", []))
    current = {
        issue_id
        for issue_id, issue in state.get("issues", {}).items()
        if issue.get("status") == "open" and issue.get("detector") in _REVIEW_DETECTORS
    }
    return current - triaged if triaged else set()


def is_triage_stale(
    plan: dict,
    state: StateModel,
    *,
    triage_ids: set[str] | frozenset[str] = frozenset(),
) -> bool:
    """Return True when triage should run because review work has changed."""
    meta = plan.get("epic_triage_meta", {})

    issues = state.get("issues", {})
    current_review_ids = {
        issue_id
        for issue_id, issue in issues.items()
        if issue.get("status") == "open" and issue.get("detector") in _REVIEW_DETECTORS
    }
    triaged_ids = set(meta.get("triaged_ids", []))
    new_since_triage = current_review_ids - triaged_ids
    if new_since_triage:
        return True

    confirmed = set(meta.get("triage_stages", {}).keys())
    if confirmed:
        order = set(plan.get("queue_order", []))
        if order & set(triage_ids):
            return True
    return False


__all__ = [
    "compute_new_issue_ids",
    "current_stale_ids",
    "current_under_target_ids",
    "current_unscored_ids",
    "is_triage_stale",
    "review_issue_snapshot_hash",
]
