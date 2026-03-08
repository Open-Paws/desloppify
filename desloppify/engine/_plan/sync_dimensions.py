"""Sync subjective dimensions into the plan queue.

Two independent sync functions:

- **sync_unscored_dimensions** — append never-scored (placeholder) dimensions
  to the *back* of the queue unconditionally.
- **sync_stale_dimensions** — append stale (previously-scored) dimensions to
  the *back* of the queue when no objective items remain, and evict them
  again when objective backlog returns.

Invariant: new items are always appended — sync never reorders existing queue.
"""

from __future__ import annotations

from desloppify.base.config import DEFAULT_TARGET_STRICT_SCORE
from desloppify.engine._plan import stale_policy as stale_policy_mod
from desloppify.engine._plan._sync_context import has_objective_backlog, is_mid_cycle
from desloppify.engine._plan.constants import SUBJECTIVE_PREFIX, QueueSyncResult
from desloppify.engine._plan.schema import PlanModel, ensure_plan_defaults
from desloppify.engine._plan.subjective_policy import SubjectiveVisibility
from desloppify.engine._state.schema import StateModel


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------

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
# Helpers
# ---------------------------------------------------------------------------

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
    *,
    inject_ids: set[str],
    injected: list[str],
) -> None:
    """Inject subjective IDs into *order* if not already present.

    Always appends to the back — new items never reorder existing queue.
    """
    existing = set(order)
    for sid in sorted(inject_ids):
        if sid not in existing:
            order.append(sid)
            injected.append(sid)


# ---------------------------------------------------------------------------
# Unscored dimension sync (back of queue, unconditional)
# ---------------------------------------------------------------------------

def sync_unscored_dimensions(
    plan: PlanModel,
    state: StateModel,
) -> QueueSyncResult:
    """Keep the plan queue in sync with unscored (placeholder) subjective dimensions.

    1. **Prune** — remove ``subjective::*`` IDs from ``queue_order`` that are
       no longer unscored AND not stale (avoids pruning stale IDs — that is
       ``sync_stale_dimensions``' responsibility).
    2. **Inject** — append currently-unscored IDs to the *back* of
       ``queue_order``.  Never reorders existing items.
    """
    ensure_plan_defaults(plan)
    result = QueueSyncResult()

    # Mid-cycle: don't inject unscored dimensions — they'll surface at cycle end.
    if is_mid_cycle(plan):
        return result

    unscored_ids = current_unscored_ids(state)
    stale_ids = stale_policy_mod.current_stale_ids(
        state, subjective_prefix=SUBJECTIVE_PREFIX,
    )
    order: list[str] = plan["queue_order"]

    # --- Cleanup: prune subjective IDs that are no longer unscored --------
    # Only prune IDs that are neither unscored nor stale (stale sync owns those).
    _prune_subjective_ids(order, keep_ids=unscored_ids | stale_ids, pruned=result.pruned)

    # --- Inject: append unscored IDs to back of queue ---------------------
    _inject_subjective_ids(order, inject_ids=unscored_ids, injected=result.injected)

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
) -> QueueSyncResult:
    """Keep the plan queue in sync with stale and under-target subjective dimensions.

    1. Remove any ``subjective::*`` IDs from ``queue_order`` that are no
       longer stale/under-target and not unscored (avoids pruning IDs owned
       by ``sync_unscored_dimensions``).
       When objective backlog exists (and this is not a just-completed cycle),
       stale/under-target IDs are also evicted so they do not block objective work.
    2. Append stale and under-target dimension IDs to the *back* when either:
       a. No objective items remain (mid-cycle), OR
       b. A cycle just completed.
       Never reorders existing items.
    """
    ensure_plan_defaults(plan)
    result = QueueSyncResult()
    stale_ids = stale_policy_mod.current_stale_ids(
        state, subjective_prefix=SUBJECTIVE_PREFIX,
    )
    under_target_ids = current_under_target_ids(state)
    injectable_ids = stale_ids | under_target_ids
    unscored_ids = current_unscored_ids(state)
    order: list[str] = plan["queue_order"]

    objective_backlog = has_objective_backlog(state, policy)

    # --- Cleanup: prune resolved subjective IDs --------------------------
    # Keep unscored IDs always. Keep stale/under-target only when objective
    # backlog is clear, or when intentionally front-loading right after a
    # completed cycle.
    keep_ids = unscored_ids | injectable_ids
    if objective_backlog and not cycle_just_completed:
        keep_ids = unscored_ids
    _prune_subjective_ids(order, keep_ids=keep_ids, pruned=result.pruned)

    # --- Inject stale + under-target dimensions --------------------------
    should_inject = not objective_backlog or cycle_just_completed

    if should_inject and injectable_ids:
        _inject_subjective_ids(order, inject_ids=injectable_ids, injected=result.injected)

    return result


__all__ = [
    "current_under_target_ids",
    "current_unscored_ids",
    "sync_stale_dimensions",
    "sync_unscored_dimensions",
]
