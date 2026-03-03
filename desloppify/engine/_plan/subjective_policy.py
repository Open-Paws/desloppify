"""Unified subjective-visibility policy.

A single frozen dataclass computed once per operation replaces the scattered
``has_objective_items`` / ``objective_count`` computations in
``stale_dimensions``, ``auto_cluster``, and ``_work_queue/core``.
"""

from __future__ import annotations

from dataclasses import dataclass

from desloppify.engine._state.schema import StateModel

# Detectors whose issues are NOT objective mechanical work.
# Canonical definition — re-exported by stale_dimensions for back-compat.
NON_OBJECTIVE_DETECTORS: frozenset[str] = frozenset({
    "review", "concerns", "subjective_review", "subjective_assessment",
})


@dataclass(frozen=True)
class SubjectiveVisibility:
    """Immutable snapshot of the subjective-vs-objective balance."""

    has_objective_backlog: bool  # any open non-subjective issues?
    objective_count: int  # how many
    unscored_ids: frozenset[str]  # subjective::* IDs needing initial review
    stale_ids: frozenset[str]  # subjective::* IDs needing re-review
    under_target_ids: frozenset[str]  # below target, not stale/unscored

    def should_surface(self, item: dict) -> bool:
        """Should this subjective queue item appear in the work queue?

        Unscored (initial_review) -> always.  All others -> only when drained.
        """
        if item.get("initial_review"):
            return True
        return not self.has_objective_backlog

    def should_inject_to_plan(self, fid: str) -> bool:
        """Should this subjective ID be injected into plan queue_order?"""
        if fid in self.unscored_ids:
            return True  # unconditional
        if fid in self.stale_ids:
            return not self.has_objective_backlog
        if fid in self.under_target_ids:
            return not self.has_objective_backlog
        return False

    def should_evict_from_plan(self, fid: str) -> bool:
        """Should this subjective ID be removed from plan queue_order?"""
        if fid in self.unscored_ids:
            return False  # never evict unscored
        if fid in self.stale_ids or fid in self.under_target_ids:
            return self.has_objective_backlog
        return False

    @property
    def backlog_blocks_rerun(self) -> bool:
        """Preflight: should reruns be blocked?"""
        return self.has_objective_backlog


def _is_evidence_only(issue: dict) -> bool:
    """Return True if the issue is below its detector's standalone threshold."""
    from desloppify.core.registry import DETECTORS
    from desloppify.engine.planning.common import CONFIDENCE_ORDER

    detector = issue.get("detector", "")
    meta = DETECTORS.get(detector)
    if meta and meta.standalone_threshold:
        threshold_rank = CONFIDENCE_ORDER.get(meta.standalone_threshold, 9)
        issue_rank = CONFIDENCE_ORDER.get(issue.get("confidence", "low"), 9)
        if issue_rank > threshold_rank:
            return True
    return False


_SCAN_PATH_FROM_STATE_POLICY = object()


def compute_subjective_visibility(
    state: StateModel,
    *,
    target_strict: float = 95.0,
    scan_path: str | None | object = _SCAN_PATH_FROM_STATE_POLICY,
    plan: dict | None = None,
) -> SubjectiveVisibility:
    """Build the policy snapshot from current state.

    *scan_path* defaults to ``state["scan_path"]`` so callers don't need to
    thread it manually.  Pass an explicit ``str`` to override, or ``None``
    to disable scope filtering.  When *plan* is set, issues whose IDs
    appear in ``plan["skipped"]`` are excluded.

    Imports building-block helpers from ``stale_dimensions`` so the
    source-of-truth logic stays in one place.
    """
    from desloppify.engine._plan.stale_dimensions import (
        _current_stale_ids,
        current_under_target_ids,
        current_unscored_ids,
    )
    from desloppify.engine._state.filtering import issue_in_scan_scope

    resolved_scan_path: str | None = (
        state.get("scan_path")
        if scan_path is _SCAN_PATH_FROM_STATE_POLICY
        else scan_path  # type: ignore[assignment]
    )

    issues = state.get("issues", {})
    skipped_ids = set((plan or {}).get("skipped", {}).keys())

    # Count open, non-suppressed, objective issues.
    # Evidence-only issues (below standalone confidence threshold) are
    # excluded — they still affect scores but are not actionable queue items.
    # Issues outside scan_path and plan-skipped issues are also excluded
    # so the policy matches what the user actually sees in the queue.
    objective_count = sum(
        1
        for fid, f in issues.items()
        if f.get("status") == "open"
        and f.get("detector") not in NON_OBJECTIVE_DETECTORS
        and not f.get("suppressed")
        and not _is_evidence_only(f)
        and issue_in_scan_scope(str(f.get("file", "")), resolved_scan_path)
        and fid not in skipped_ids
    )

    unscored = current_unscored_ids(state)
    stale = _current_stale_ids(state)
    under_target = current_under_target_ids(state, target_strict=target_strict)

    return SubjectiveVisibility(
        has_objective_backlog=objective_count > 0,
        objective_count=objective_count,
        unscored_ids=frozenset(unscored),
        stale_ids=frozenset(stale),
        under_target_ids=frozenset(under_target),
    )


__all__ = [
    "NON_OBJECTIVE_DETECTORS",
    "SubjectiveVisibility",
    "compute_subjective_visibility",
]
