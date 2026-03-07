"""Sync subjective dimensions into the plan queue.

Two independent sync functions:

- **sync_unscored_dimensions** — prepend never-scored (placeholder) dimensions
  to the *front* of the queue unconditionally (onboarding priority).
- **sync_stale_dimensions** — append stale (previously-scored) dimensions to
  the *back* of the queue when no objective items remain.
"""

from __future__ import annotations
from dataclasses import dataclass, field

from desloppify.base.config import DEFAULT_TARGET_STRICT_SCORE
from desloppify.engine._plan import stale_policy as stale_policy_mod
from desloppify.engine._plan.promoted_ids import promoted_insertion_index
from desloppify.engine._plan.schema import PlanModel, ensure_plan_defaults
from desloppify.engine._plan.subjective_policy import (
    NON_OBJECTIVE_DETECTORS as _NON_OBJECTIVE_DETECTORS,
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
    "triage::enrich",
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
    return stale_policy_mod.current_stale_ids(
        state,
        subjective_prefix=SUBJECTIVE_PREFIX,
    )


def current_unscored_ids(state: StateModel) -> set[str]:
    """Return the set of ``subjective::<slug>`` IDs that are currently unscored (placeholder).

    Checks ``subjective_assessments`` first; when that dict is empty
    (common before any reviews have been run), falls through to
    ``dimension_scores`` which carries placeholder metadata from scan.
    """
    return stale_policy_mod.current_unscored_ids(
        state,
        subjective_prefix=SUBJECTIVE_PREFIX,
    )


def current_under_target_ids(
    state: StateModel,
    *,
    target_strict: float = DEFAULT_TARGET_STRICT_SCORE,
) -> set[str]:
    """Return ``subjective::<slug>`` IDs that are under target but not stale or unscored.

    These are dimensions whose assessment is still current (not needing refresh)
    but whose score hasn't reached the target yet.
    """
    return stale_policy_mod.current_under_target_ids(
        state,
        target_strict=target_strict,
        subjective_prefix=SUBJECTIVE_PREFIX,
    )


# ---------------------------------------------------------------------------
# Helpers for sync_stale_dimensions / sync_unscored_dimensions
# ---------------------------------------------------------------------------

def _has_objective_backlog(
    state: StateModel,
    policy: SubjectiveVisibility | None,
) -> bool:
    """Return whether an objective backlog exists (open non-subjective issues)."""
    if policy is not None:
        return policy.has_objective_backlog
    return any(
        f.get("status") == "open"
        and f.get("detector") not in _NON_OBJECTIVE_DETECTORS
        and not f.get("suppressed")
        for f in state.get("issues", {}).values()
    )


def _prune_subjective_ids(
    order: list[str],
    *,
    keep_ids: set[str],
    pruned: list[str],
) -> None:
    """Remove subjective IDs from *order* that are not in *keep_ids*, appending removed to *pruned*."""
    to_remove = [
        fid for fid in order
        if fid.startswith(SUBJECTIVE_PREFIX)
        and fid not in keep_ids
    ]
    for fid in to_remove:
        order.remove(fid)
        pruned.append(fid)


def _inject_subjective_ids(
    order: list[str],
    plan: PlanModel,
    *,
    inject_ids: set[str],
    to_front: bool,
    injected: list[str],
) -> None:
    """Inject subjective IDs into *order* if not already present.

    When *to_front* is True, inserts after promoted items (front of queue).
    Otherwise appends to the back.
    """
    existing = set(order)
    if to_front:
        insert_at = promoted_insertion_index(order, plan)
        for sid in reversed(sorted(inject_ids)):
            if sid not in existing:
                order.insert(insert_at, sid)
                injected.append(sid)
    else:
        for sid in sorted(inject_ids):
            if sid not in existing:
                order.append(sid)
                injected.append(sid)


# ---------------------------------------------------------------------------
# Helpers for sync_triage_needed
# ---------------------------------------------------------------------------

def _open_review_issue_ids(state: StateModel) -> set[str]:
    """Return set of open issue IDs whose detector is 'review' or 'concerns'."""
    issues = state.get("issues", {})
    return {
        fid for fid, f in issues.items()
        if f.get("status") == "open"
        and f.get("detector") in ("review", "concerns")
    }


def _new_review_ids_since_triage(
    state: StateModel,
    meta: dict,
) -> set[str]:
    """Return review issue IDs that are new since the last triage."""
    current_review_ids = _open_review_issue_ids(state)
    triaged_ids = set(meta.get("triaged_ids", []))
    return current_review_ids - triaged_ids


def _prune_all_triage_stages(order: list[str]) -> None:
    """Remove all ``triage::*`` stage IDs from *order*."""
    for sid in TRIAGE_STAGE_IDS:
        while sid in order:
            order.remove(sid)


def _inject_pending_triage_stages(
    order: list[str],
    plan: PlanModel,
    confirmed: set[str],
) -> bool:
    """Inject triage stages for pending (unconfirmed) items.

    Returns True if any stages were injected.
    """
    insert_at = promoted_insertion_index(order, plan)
    stage_names = ("observe", "reflect", "organize", "enrich", "commit")
    existing = set(order)
    injected_count = 0
    for sid, name in zip(TRIAGE_STAGE_IDS, stage_names, strict=False):
        if name not in confirmed and sid not in existing:
            order.insert(insert_at + injected_count, sid)
            injected_count += 1
    return injected_count > 0


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

    # Mid-cycle: don't inject unscored dimensions — they'll surface at cycle end.
    if plan.get("plan_start_scores"):
        return result

    unscored_ids = current_unscored_ids(state)
    stale_ids = _current_stale_ids(state)
    order: list[str] = plan["queue_order"]

    # --- Cleanup: prune subjective IDs that are no longer unscored --------
    # Only prune IDs that are neither unscored nor stale (stale sync owns those).
    _prune_subjective_ids(order, keep_ids=unscored_ids | stale_ids, pruned=result.pruned)

    # --- Inject: prepend unscored IDs after any promoted items -------------
    _inject_subjective_ids(order, plan, inject_ids=unscored_ids, to_front=True, injected=result.injected)

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
    _prune_subjective_ids(order, keep_ids=injectable_ids | unscored_ids, pruned=result.pruned)

    # --- Inject or evict stale + under-target dimensions -----------------
    has_real_items = _has_objective_backlog(state, policy)
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
        to_front = cycle_just_completed and has_real_items
        _inject_subjective_ids(order, plan, inject_ids=injectable_ids, to_front=to_front, injected=result.injected)

    return result


# ---------------------------------------------------------------------------
# Triage snapshot hash + sync
# ---------------------------------------------------------------------------

def review_issue_snapshot_hash(state: StateModel) -> str:
    """Hash open review issue IDs to detect changes.

    Returns empty string when there are no open review issues.
    """
    return stale_policy_mod.review_issue_snapshot_hash(state)


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
            new_since_triage = _new_review_ids_since_triage(state, meta)

            if not new_since_triage:
                # No new issues remain — prune stale stages
                _prune_all_triage_stages(order)
                if current_hash:
                    meta["issue_snapshot_hash"] = current_hash
                    plan["epic_triage_meta"] = meta
                result.pruned = True
        return result

    if current_hash and current_hash != last_hash:
        # Distinguish "new issues appeared" from "issues were resolved".
        # Only re-triage when genuinely new issues exist.
        new_since_triage = _new_review_ids_since_triage(state, meta)

        if new_since_triage:
            # New review issues appeared — re-triage needed
            result.injected = _inject_pending_triage_stages(order, plan, confirmed)
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
            and f.get("detector") not in _NON_OBJECTIVE_DETECTORS
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
    return stale_policy_mod.compute_new_issue_ids(plan, state)


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
    return stale_policy_mod.is_triage_stale(plan, state, triage_ids=TRIAGE_IDS)


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
