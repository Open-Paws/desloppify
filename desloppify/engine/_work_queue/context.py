"""Unified queue-resolution context.

A frozen ``QueueContext`` computed once per operation replaces the scattered
``plan`` / ``target_strict`` / ``policy`` threading through function chains.
Callers build one context and pass it everywhere — makes the wrong thing
impossible.
"""

from __future__ import annotations

from dataclasses import dataclass

from desloppify.base.config import (
    DEFAULT_TARGET_STRICT_SCORE,
    target_strict_score_from_config,
)
from desloppify.base.exception_sets import PLAN_LOAD_EXCEPTIONS
from desloppify.engine import plan as plan_mod
from desloppify.engine._plan.subjective_policy import (
    SubjectiveVisibility,
    compute_subjective_visibility,
)
from desloppify.engine._state.schema import StateModel


class _PlanAutoLoad:
    """Sentinel type: auto-load plan from disk."""


# Sentinel: "auto-load plan from disk" (the default).
_PLAN_AUTO_LOAD = _PlanAutoLoad()
PlanOption = dict | None | _PlanAutoLoad


@dataclass(frozen=True)
class QueueContext:
    """Immutable snapshot of resolved queue parameters.

    Built once via :func:`queue_context`, then threaded through
    ``build_work_queue``, ``plan_aware_queue_breakdown``, and command
    helpers so every call site agrees on plan, target, and policy.
    """

    plan: dict | None
    target_strict: float
    policy: SubjectiveVisibility


def queue_context(
    state: StateModel,
    *,
    config: dict | None = None,
    plan: PlanOption = _PLAN_AUTO_LOAD,
    target_strict: float | None = None,
) -> QueueContext:
    """Build a :class:`QueueContext` with all parameters resolved.

    Resolution order:

    1. **plan** — explicit value wins; sentinel ``_PLAN_AUTO_LOAD`` triggers
       ``load_plan()`` (guarded by ``PLAN_LOAD_EXCEPTIONS``).
    2. **target_strict** — explicit float wins; ``None`` reads from *config*
       via ``target_strict_score_from_config``; final fallback is ``95.0``.
    3. **policy** — ``compute_subjective_visibility(state, ...)`` with the
       resolved plan and target_strict so every downstream consumer sees
       the same objective-vs-subjective balance.
    """
    # --- resolve plan ---
    if isinstance(plan, _PlanAutoLoad):
        try:
            resolved_plan: dict | None = plan_mod.load_plan()
        except PLAN_LOAD_EXCEPTIONS:
            resolved_plan = None
    else:
        resolved_plan = plan

    # --- resolve target_strict ---
    if target_strict is not None:
        resolved_target = target_strict
    elif config is not None:
        resolved_target = target_strict_score_from_config(config)
    else:
        resolved_target = DEFAULT_TARGET_STRICT_SCORE

    # --- resolve policy ---
    resolved_policy = compute_subjective_visibility(
        state,
        target_strict=resolved_target,
        plan=resolved_plan,
    )

    return QueueContext(
        plan=resolved_plan,
        target_strict=resolved_target,
        policy=resolved_policy,
    )


__all__ = [
    "QueueContext",
    "queue_context",
]
