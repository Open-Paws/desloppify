"""Sync subjective dimensions into the plan queue.

Two independent sync functions:

- **sync_unscored_dimensions** — prepend never-scored (placeholder) dimensions
  to the *front* of the queue unconditionally (onboarding priority).
- **sync_stale_dimensions** — append stale (previously-scored) dimensions to
  the *back* of the queue when no objective items remain.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from desloppify.engine._plan.schema import PlanModel, ensure_plan_defaults
from desloppify.engine._plan.subjective_policy import (
    NON_OBJECTIVE_DETECTORS,
    SubjectiveVisibility,
)
from desloppify.engine._state.schema import StateModel

SUBJECTIVE_PREFIX = "subjective::"
TRIAGE_ID = "triage::pending"  # deprecated, kept for migration

TRIAGE_PREFIX = "triage::"
TRIAGE_STAGE_IDS = (
    "triage::observe",
    "triage::reflect",
    "triage::organize",
    "triage::commit",
)
TRIAGE_IDS = set(TRIAGE_STAGE_IDS)
WORKFLOW_CREATE_PLAN_ID = "workflow::create-plan"
WORKFLOW_SCORE_CHECKPOINT_ID = "workflow::score-checkpoint"
WORKFLOW_IMPORT_SCORES_ID = "workflow::import-scores"
WORKFLOW_COMMUNICATE_SCORE_ID = "workflow::communicate-score"
WORKFLOW_PREFIX = "workflow::"
SYNTHETIC_PREFIXES = ("triage::", "workflow::", "subjective::")


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StaleDimensionSyncResult:
    """What changed during a stale-dimension sync."""

    injected: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)

    @property
    def changes(self) -> int:
        return len(self.injected) + len(self.pruned)


@dataclass
class UnscoredDimensionSyncResult:
    """What changed during an unscored-dimension sync."""

    injected: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)

    @property
    def changes(self) -> int:
        return len(self.injected) + len(self.pruned)


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------

def _current_stale_ids(state: StateModel) -> set[str]:
    """Return the set of ``subjective::<slug>`` IDs that are currently stale."""
    from desloppify.engine._work_queue.helpers import slugify
    from desloppify.engine.planning.scorecard_projection import (
        all_subjective_entries,
    )

    dim_scores = state.get("dimension_scores", {}) or {}
    if not dim_scores:
        return set()

    stale: set[str] = set()
    for entry in all_subjective_entries(state, dim_scores=dim_scores):
        if not entry.get("stale"):
            continue
        dim_key = entry.get("dimension_key", "")
        if dim_key:
            stale.add(f"{SUBJECTIVE_PREFIX}{slugify(dim_key)}")
    return stale


def current_unscored_ids(state: StateModel) -> set[str]:
    """Return the set of ``subjective::<slug>`` IDs that are currently unscored (placeholder).

    Checks ``subjective_assessments`` first; when that dict is empty
    (common before any reviews have been run), falls through to
    ``dimension_scores`` which carries placeholder metadata from scan.
    """
    from desloppify.engine._work_queue.helpers import slugify

    # Primary source: subjective_assessments with placeholder=True
    assessments = state.get("subjective_assessments")
    if isinstance(assessments, dict) and assessments:
        unscored: set[str] = set()
        for dim_key, payload in assessments.items():
            if not isinstance(payload, dict):
                continue
            if not payload.get("placeholder"):
                continue
            if dim_key:
                unscored.add(f"{SUBJECTIVE_PREFIX}{slugify(dim_key)}")
        return unscored

    # Fallback: check dimension_scores directly for placeholder subjective
    # dimensions.  This handles the common case where subjective_assessments
    # hasn't been populated yet but dimension_scores already has placeholder
    # entries from scan.  We can't use scorecard_subjective_entries() here
    # because the scorecard pipeline intentionally hides placeholders.
    dim_scores = state.get("dimension_scores", {}) or {}
    if not dim_scores:
        return set()

    unscored = set()
    for _name, data in dim_scores.items():
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
            unscored.add(f"{SUBJECTIVE_PREFIX}{slugify(dim_key)}")
    return unscored


def current_under_target_ids(
    state: StateModel,
    *,
    target_strict: float = 95.0,
) -> set[str]:
    """Return ``subjective::<slug>`` IDs that are under target but not stale or unscored.

    These are dimensions whose assessment is still current (not needing refresh)
    but whose score hasn't reached the target yet.
    """
    from desloppify.engine._work_queue.helpers import slugify
    from desloppify.engine.planning.scorecard_projection import (
        all_subjective_entries,
    )

    dim_scores = state.get("dimension_scores", {}) or {}
    if not dim_scores:
        return set()

    stale_ids = _current_stale_ids(state)
    unscored_ids = current_unscored_ids(state)

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
        fid = f"{SUBJECTIVE_PREFIX}{slugify(dim_key)}"
        if fid not in stale_ids and fid not in unscored_ids:
            under_target.add(fid)
    return under_target


# ---------------------------------------------------------------------------
# Promoted-aware insertion helper
# ---------------------------------------------------------------------------

def _after_promoted(order: list[str], plan: PlanModel) -> int:
    """Return the insertion index just after the last promoted item in *order*.

    When no promoted items are present (or none are in *order*), returns 0
    so callers fall back to existing front-of-queue behavior.
    """
    promoted = set(plan.get("promoted_ids", []))
    if not promoted:
        return 0
    last_idx = -1
    for i, fid in enumerate(order):
        if fid in promoted:
            last_idx = i
    return last_idx + 1 if last_idx >= 0 else 0


# ---------------------------------------------------------------------------
# Unscored dimension sync (front of queue, unconditional)
# ---------------------------------------------------------------------------

def sync_unscored_dimensions(
    plan: PlanModel,
    state: StateModel,
) -> UnscoredDimensionSyncResult:
    """Keep the plan queue in sync with unscored (placeholder) subjective dimensions.

    1. **Prune** — remove ``subjective::*`` IDs from ``queue_order`` that are
       no longer unscored AND not stale (avoids pruning stale IDs — that is
       ``sync_stale_dimensions``' responsibility).
    2. **Inject** — unconditionally prepend currently-unscored IDs to the
       *front* of ``queue_order`` so initial reviews are the first priority.
    """
    ensure_plan_defaults(plan)
    result = UnscoredDimensionSyncResult()
    unscored_ids = current_unscored_ids(state)
    stale_ids = _current_stale_ids(state)
    order: list[str] = plan["queue_order"]

    # --- Cleanup: prune subjective IDs that are no longer unscored --------
    # Only prune IDs that are neither unscored nor stale (stale sync owns those).
    to_remove: list[str] = [
        fid for fid in order
        if fid.startswith(SUBJECTIVE_PREFIX)
        and fid not in unscored_ids
        and fid not in stale_ids
    ]
    for fid in to_remove:
        order.remove(fid)
        result.pruned.append(fid)

    # --- Inject: prepend unscored IDs after any promoted items -------------
    existing = set(order)
    insert_at = _after_promoted(order, plan)
    for uid in reversed(sorted(unscored_ids)):
        if uid not in existing:
            order.insert(insert_at, uid)
            result.injected.append(uid)

    return result


# ---------------------------------------------------------------------------
# Stale dimension sync (back of queue, conditional)
# ---------------------------------------------------------------------------

def sync_stale_dimensions(
    plan: PlanModel,
    state: StateModel,
    *,
    policy: SubjectiveVisibility | None = None,
    cycle_just_completed: bool = False,
) -> StaleDimensionSyncResult:
    """Keep the plan queue in sync with stale and under-target subjective dimensions.

    1. Remove any ``subjective::*`` IDs from ``queue_order`` that are no
       longer stale/under-target and not unscored (avoids pruning IDs owned
       by ``sync_unscored_dimensions``).
    2. Inject stale and under-target dimension IDs when either:
       a. No objective items remain (mid-cycle: append to back), OR
       b. A cycle just completed (post-cycle: insert at front so subjective
          review takes priority over new objective issues).
    """
    ensure_plan_defaults(plan)
    result = StaleDimensionSyncResult()
    stale_ids = _current_stale_ids(state)
    under_target_ids = current_under_target_ids(state)
    injectable_ids = stale_ids | under_target_ids
    unscored_ids = current_unscored_ids(state)
    order: list[str] = plan["queue_order"]

    # --- Cleanup: prune resolved subjective IDs --------------------------
    # Only prune IDs that are no longer injectable and not unscored.
    to_remove: list[str] = [
        fid for fid in order
        if fid.startswith(SUBJECTIVE_PREFIX)
        and fid not in injectable_ids
        and fid not in unscored_ids
    ]
    for fid in to_remove:
        order.remove(fid)
        result.pruned.append(fid)

    # --- Inject or evict stale + under-target dimensions -----------------
    if policy is not None:
        has_real_items = policy.has_objective_backlog
    else:
        has_real_items = any(
            f.get("status") == "open"
            and f.get("detector") not in NON_OBJECTIVE_DETECTORS
            and not f.get("suppressed")
            for f in state.get("issues", {}).values()
        )

    should_inject = not has_real_items or cycle_just_completed

    if not should_inject:
        # Mid-cycle with objective backlog: evict any stale/under-target IDs
        # that are present in the queue.  They may have been grandfathered from
        # the unscored phase and should not be visible until the objective
        # backlog clears or a cycle completes.
        to_evict = [
            fid for fid in order
            if fid.startswith(SUBJECTIVE_PREFIX)
            and fid in injectable_ids
        ]
        for fid in to_evict:
            order.remove(fid)
            result.pruned.append(fid)

    if should_inject and injectable_ids:
        existing = set(order)
        if cycle_just_completed and has_real_items:
            # Post-cycle: front-of-queue after promoted items so subjective
            # review happens before the new objective cycle begins.
            insert_at = _after_promoted(order, plan)
            for sid in reversed(sorted(injectable_ids)):
                if sid not in existing:
                    order.insert(insert_at, sid)
                    result.injected.append(sid)
        else:
            # Mid-cycle or no objective backlog: append to back.
            for sid in sorted(injectable_ids):
                if sid not in existing:
                    order.append(sid)
                    result.injected.append(sid)

    return result


# ---------------------------------------------------------------------------
# Triage snapshot hash + sync
# ---------------------------------------------------------------------------

def review_issue_snapshot_hash(state: StateModel) -> str:
    """Hash open review issue IDs to detect changes.

    Returns empty string when there are no open review issues.
    """
    issues = state.get("issues", {})
    review_ids = sorted(
        fid for fid, f in issues.items()
        if f.get("status") == "open"
        and f.get("detector") in ("review", "concerns")
    )
    if not review_ids:
        return ""
    return hashlib.sha256("|".join(review_ids).encode()).hexdigest()[:16]


@dataclass
class TriageSyncResult:
    """What changed during a triage sync."""

    injected: bool = False
    pruned: bool = False

    @property
    def changes(self) -> int:
        return int(self.injected) + int(self.pruned)


def sync_triage_needed(
    plan: PlanModel,
    state: StateModel,
) -> TriageSyncResult:
    """Inject 4 triage stage IDs at front of queue when review issues change.

    Only injects stages not already confirmed in ``epic_triage_meta``.

    When stages are already present but all new issues have been resolved
    since injection, auto-prunes the stale stages and updates the hash.

    When issues are *resolved* (current IDs are a subset of previously
    triaged IDs), the snapshot hash is updated silently — no re-triage
    is needed since the user is working through the plan.
    """
    ensure_plan_defaults(plan)
    result = TriageSyncResult()
    order: list[str] = plan["queue_order"]
    meta = plan.get("epic_triage_meta", {})
    confirmed = set(meta.get("triage_stages", {}).keys())

    # Check if any triage stage is already in queue
    already_present = any(sid in order for sid in TRIAGE_IDS)

    current_hash = review_issue_snapshot_hash(state)
    last_hash = meta.get("issue_snapshot_hash", "")

    if already_present:
        # Stages present — check if the reason for injection still applies.
        # Only auto-prune when triage was completed before (hash exists),
        # all new issues have been resolved, and no triage work is in
        # progress.  This avoids pruning the initial triage or a
        # user-started triage session.
        if last_hash and not confirmed:
            issues = state.get("issues", {})
            current_review_ids = {
                fid for fid, f in issues.items()
                if f.get("status") == "open"
                and f.get("detector") in ("review", "concerns")
            }
            triaged_ids = set(meta.get("triaged_ids", []))
            new_since_triage = current_review_ids - triaged_ids

            if not new_since_triage:
                # No new issues remain — prune stale stages
                for sid in TRIAGE_STAGE_IDS:
                    while sid in order:
                        order.remove(sid)
                if current_hash:
                    meta["issue_snapshot_hash"] = current_hash
                    plan["epic_triage_meta"] = meta
                result.pruned = True
        return result

    if current_hash and current_hash != last_hash:
        # Distinguish "new issues appeared" from "issues were resolved".
        # Only re-triage when genuinely new issues exist.
        issues = state.get("issues", {})
        current_review_ids = {
            fid for fid, f in issues.items()
            if f.get("status") == "open"
            and f.get("detector") in ("review", "concerns")
        }
        triaged_ids = set(meta.get("triaged_ids", []))
        new_since_triage = current_review_ids - triaged_ids

        if new_since_triage:
            # New review issues appeared — re-triage needed
            insert_at = _after_promoted(order, plan)
            stage_names = ("observe", "reflect", "organize", "commit")
            existing = set(order)
            injected_count = 0
            for sid, name in zip(TRIAGE_STAGE_IDS, stage_names):
                if name not in confirmed and sid not in existing:
                    order.insert(insert_at + injected_count, sid)
                    injected_count += 1
            if injected_count:
                result.injected = True
        else:
            # Only resolved issues changed the hash — update silently
            meta["issue_snapshot_hash"] = current_hash
            plan["epic_triage_meta"] = meta

    return result


@dataclass
class ScoreCheckpointSyncResult:
    """What changed during a score-checkpoint sync."""

    injected: bool = False

    @property
    def changes(self) -> int:
        return int(self.injected)


def sync_score_checkpoint_needed(
    plan: PlanModel,
    state: StateModel,
    *,
    policy: SubjectiveVisibility | None = None,
) -> ScoreCheckpointSyncResult:
    """Inject ``workflow::score-checkpoint`` when all initial reviews complete.

    Injects when:
    - No unscored (placeholder) subjective dimensions remain
    - ``workflow::score-checkpoint`` is not already in the queue

    Positioned after subjective items but before triage/create-plan
    so the user sees their updated strict score right after reviews finish.
    """
    ensure_plan_defaults(plan)
    result = ScoreCheckpointSyncResult()
    order: list[str] = plan["queue_order"]

    if WORKFLOW_SCORE_CHECKPOINT_ID in order:
        return result

    # Check that no unscored dimensions remain
    if policy is not None:
        if policy.unscored_ids:
            return result
    else:
        unscored = current_unscored_ids(state)
        if unscored:
            return result

    # Insert after any subjective items, before triage/workflow/issues
    insert_at = 0
    for i, fid in enumerate(order):
        if fid.startswith(SUBJECTIVE_PREFIX):
            insert_at = i + 1
    order.insert(insert_at, WORKFLOW_SCORE_CHECKPOINT_ID)
    result.injected = True
    return result


@dataclass
class CreatePlanSyncResult:
    """What changed during a create-plan sync."""

    injected: bool = False

    @property
    def changes(self) -> int:
        return int(self.injected)


def sync_create_plan_needed(
    plan: PlanModel,
    state: StateModel,
    *,
    policy: SubjectiveVisibility | None = None,
) -> CreatePlanSyncResult:
    """Inject ``workflow::create-plan`` when reviews complete + objective backlog exists.

    Only injects when:
    - No unscored (placeholder) subjective dimensions remain
    - At least one objective issue exists
    - ``workflow::create-plan`` is not already in the queue
    - No triage stages are pending
    """
    ensure_plan_defaults(plan)
    result = CreatePlanSyncResult()
    order: list[str] = plan["queue_order"]

    if WORKFLOW_CREATE_PLAN_ID in order:
        return result

    # Don't inject if triage stages are pending
    if any(sid in order for sid in TRIAGE_IDS):
        return result

    # Check that no unscored dimensions remain
    if policy is not None:
        if policy.unscored_ids:
            return result
        has_objective = policy.has_objective_backlog
    else:
        unscored = current_unscored_ids(state)
        if unscored:
            return result
        issues = state.get("issues", {})
        has_objective = any(
            f.get("status") == "open"
            and f.get("detector") not in NON_OBJECTIVE_DETECTORS
            for f in issues.values()
        )
    if not has_objective:
        return result

    # Insert after any subjective/workflow items, at the end of the
    # synthetic block (so create-plan comes after score-checkpoint).
    insert_at = 0
    for i, fid in enumerate(order):
        if fid.startswith(SUBJECTIVE_PREFIX) or fid.startswith(TRIAGE_PREFIX) or fid.startswith(WORKFLOW_PREFIX):
            insert_at = i + 1
    order.insert(insert_at, WORKFLOW_CREATE_PLAN_ID)
    result.injected = True
    return result


def compute_new_issue_ids(plan: PlanModel, state: StateModel) -> set[str]:
    """Return the set of open review/concerns issue IDs added since last triage.

    Returns an empty set when no prior triage has recorded ``triaged_ids``.
    """
    meta = plan.get("epic_triage_meta", {})
    triaged = set(meta.get("triaged_ids", meta.get("synthesized_ids", [])))
    current = {
        fid for fid, f in state.get("issues", {}).items()
        if f.get("status") == "open" and f.get("detector") in ("review", "concerns")
    }
    return current - triaged if triaged else set()


def is_triage_stale(plan: PlanModel, state: StateModel) -> bool:
    """Side-effect-free check: is triage needed?

    Returns True when genuinely *new* review issues appeared since the
    last triage.  Triage stage IDs being in the queue alone is not
    sufficient — the new issues that triggered injection may have been
    resolved since then.

    When issues are merely resolved (current IDs are a subset of
    previously triaged IDs), triage is NOT stale — the user is working
    through the plan.
    """
    ensure_plan_defaults(plan)
    meta = plan.get("epic_triage_meta", {})

    # Always check for genuinely new issues (same logic regardless of
    # whether triage stages are in the queue).
    issues = state.get("issues", {})
    current_review_ids = {
        fid for fid, f in issues.items()
        if f.get("status") == "open"
        and f.get("detector") in ("review", "concerns")
    }
    triaged_ids = set(meta.get("triaged_ids", []))
    new_since_triage = current_review_ids - triaged_ids
    if new_since_triage:
        return True

    # If triage stages are in queue but there's in-progress triage work,
    # still consider it stale so the user finishes what they started.
    confirmed = set(meta.get("triage_stages", {}).keys())
    if confirmed:
        order = set(plan.get("queue_order", []))
        if order & TRIAGE_IDS:
            return True

    return False


@dataclass
class ImportScoresSyncResult:
    """What changed during an import-scores sync."""

    injected: bool = False

    @property
    def changes(self) -> int:
        return int(self.injected)


def sync_import_scores_needed(
    plan: PlanModel,
    state: StateModel,
    *,
    assessment_mode: str | None = None,
) -> ImportScoresSyncResult:
    """Inject ``workflow::import-scores`` after issues-only import.

    Only injects when:
    - Assessment mode was ``issues_only`` (scores were skipped)
    - ``workflow::import-scores`` is not already in the queue
    - There are assessments in the payload that could be imported

    Positioned after score-checkpoint, before create-plan.
    """
    ensure_plan_defaults(plan)
    result = ImportScoresSyncResult()
    order: list[str] = plan["queue_order"]

    if WORKFLOW_IMPORT_SCORES_ID in order:
        return result

    # Only inject when scores were skipped (issues-only mode)
    if assessment_mode != "issues_only":
        return result

    # Insert after any subjective/workflow items
    insert_at = 0
    for i, fid in enumerate(order):
        if fid.startswith(SUBJECTIVE_PREFIX) or fid.startswith(WORKFLOW_PREFIX):
            insert_at = i + 1
    order.insert(insert_at, WORKFLOW_IMPORT_SCORES_ID)
    result.injected = True
    return result


@dataclass
class CommunicateScoreSyncResult:
    """What changed during a communicate-score sync."""

    injected: bool = False

    @property
    def changes(self) -> int:
        return int(self.injected)


def sync_communicate_score_needed(
    plan: PlanModel,
    state: StateModel,
    *,
    policy: SubjectiveVisibility | None = None,
    scores_just_imported: bool = False,
) -> CommunicateScoreSyncResult:
    """Inject ``workflow::communicate-score`` when scores should be shown.

    Injects when either:
    - All initial subjective reviews are complete (no unscored dimensions), OR
    - Scores were just imported (trusted/attested/override)

    And ``workflow::communicate-score`` is not already in the queue.
    Positioned after subjective items but before triage/create-plan.
    """
    ensure_plan_defaults(plan)
    result = CommunicateScoreSyncResult()
    order: list[str] = plan["queue_order"]

    # Also treat legacy score-checkpoint as already-present
    if WORKFLOW_COMMUNICATE_SCORE_ID in order or WORKFLOW_SCORE_CHECKPOINT_ID in order:
        return result

    # Trigger 1: scores just imported
    should_inject = scores_just_imported

    # Trigger 2: all initial reviews complete (no unscored dimensions)
    if not should_inject:
        if policy is not None:
            should_inject = not policy.unscored_ids
        else:
            should_inject = not current_unscored_ids(state)

    if not should_inject:
        return result

    # Insert after any subjective items, before triage/workflow/issues
    insert_at = 0
    for i, fid in enumerate(order):
        if fid.startswith(SUBJECTIVE_PREFIX):
            insert_at = i + 1
    order.insert(insert_at, WORKFLOW_COMMUNICATE_SCORE_ID)
    result.injected = True
    return result


__all__ = [
    "NON_OBJECTIVE_DETECTORS",
    "SUBJECTIVE_PREFIX",
    "TRIAGE_ID",
    "TRIAGE_IDS",
    "TRIAGE_PREFIX",
    "TRIAGE_STAGE_IDS",
    "SYNTHETIC_PREFIXES",
    "WORKFLOW_COMMUNICATE_SCORE_ID",
    "WORKFLOW_CREATE_PLAN_ID",
    "WORKFLOW_IMPORT_SCORES_ID",
    "WORKFLOW_PREFIX",
    "WORKFLOW_SCORE_CHECKPOINT_ID",
    "CommunicateScoreSyncResult",
    "CreatePlanSyncResult",
    "ImportScoresSyncResult",
    "ScoreCheckpointSyncResult",
    "StaleDimensionSyncResult",
    "TriageSyncResult",
    "UnscoredDimensionSyncResult",
    "current_under_target_ids",
    "current_unscored_ids",
    "compute_new_issue_ids",
    "is_triage_stale",
    "review_issue_snapshot_hash",
    "sync_communicate_score_needed",
    "sync_create_plan_needed",
    "sync_import_scores_needed",
    "sync_score_checkpoint_needed",
    "sync_stale_dimensions",
    "sync_triage_needed",
    "sync_unscored_dimensions",
]
