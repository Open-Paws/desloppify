"""Synthetic work-queue item builders and dimension scoring.

Builds workflow stage items, score checkpoint items, create-plan items,
subjective dimension items, and subjective score lookups.
"""

from __future__ import annotations

from desloppify.engine.planning.scorecard_projection import (
    all_subjective_entries,
)
from desloppify.intelligence.integrity import (
    is_holistic_subjective_issue,
    unassessed_subjective_dimensions,
)
from desloppify.scoring import DISPLAY_NAMES

from desloppify.engine._work_queue.helpers import (
    detail_dict,
    slugify,
)


# ---------------------------------------------------------------------------
# Dimension key normalization
# ---------------------------------------------------------------------------

def _canonical_subjective_dimension_key(display_name: str) -> str:
    """Map a display label (e.g. 'Mid elegance') to its canonical dimension key."""
    cleaned = display_name.replace(" (subjective)", "").strip()
    target = cleaned.lower()

    for dim_key, label in DISPLAY_NAMES.items():
        if str(label).lower() == target:
            return str(dim_key)
    return slugify(cleaned)


def _subjective_dimension_aliases(display_name: str) -> set[str]:
    """Return normalized aliases used to match display labels with issue dimension keys."""
    cleaned = display_name.replace(" (subjective)", "").strip()
    canonical = _canonical_subjective_dimension_key(cleaned)
    return {
        cleaned.lower(),
        cleaned.replace(" ", "_").lower(),
        slugify(cleaned),
        canonical.lower(),
        slugify(canonical),
    }


# ---------------------------------------------------------------------------
# Subjective strict scores
# ---------------------------------------------------------------------------

def subjective_strict_scores(state: dict) -> dict[str, float]:
    dim_scores = state.get("dimension_scores", {}) or {}
    if not dim_scores:
        return {}

    entries = all_subjective_entries(state, dim_scores=dim_scores)
    scores: dict[str, float] = {}
    for entry in entries:
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        strict_val = float(entry.get("strict", entry.get("score", 100.0)))
        dim_key = _canonical_subjective_dimension_key(name)
        aliases = _subjective_dimension_aliases(name)
        for cli_key in entry.get("cli_keys", []):
            key = str(cli_key).strip().lower()
            if not key:
                continue
            aliases.add(key)
            aliases.add(slugify(key))
        aliases.add(dim_key.lower())
        aliases.add(slugify(dim_key))
        for alias in aliases:
            scores[alias] = strict_val
    return scores


# ---------------------------------------------------------------------------
# Synthetic item builders
# ---------------------------------------------------------------------------

def build_triage_stage_items(plan: dict, state: dict) -> list[dict]:
    """Build synthetic work items for each ``triage::*`` stage ID in the queue.

    Returns an empty list when no triage stages are pending.
    """
    from desloppify.app.commands.plan.triage_playbook import (
        TRIAGE_STAGE_DEPENDENCIES,
        TRIAGE_STAGE_LABELS,
    )
    from desloppify.engine._plan.stale_dimensions import (
        TRIAGE_IDS,
        TRIAGE_STAGE_IDS,
    )

    order = plan.get("queue_order", [])
    order_set = set(order)
    present = order_set & TRIAGE_IDS
    if not present:
        return []

    meta = plan.get("epic_triage_meta", {})
    confirmed = set(meta.get("triage_stages", {}).keys())

    issues = state.get("issues", {})
    open_review_count = sum(
        1 for f in issues.values()
        if f.get("status") == "open"
        and f.get("detector") in ("review", "concerns")
    )

    label_map = dict(TRIAGE_STAGE_LABELS)
    stage_names = ("observe", "reflect", "organize", "commit")

    items: list[dict] = []
    for idx, (sid, name) in enumerate(zip(TRIAGE_STAGE_IDS, stage_names)):
        if sid not in present:
            continue
        if name in confirmed:
            continue

        # Compute blocked_by: dependency stages that are still in the queue
        deps = TRIAGE_STAGE_DEPENDENCIES.get(name, set())
        blocked_by = sorted(
            f"triage::{dep}" for dep in deps
            if f"triage::{dep}" in present and dep not in confirmed
        )

        cmd = f"desloppify plan triage --stage {name}"
        if name == "commit":
            cmd = 'desloppify plan triage --complete --strategy "..."'

        items.append({
            "id": sid,
            "tier": 1,
            "confidence": "high",
            "detector": "triage",
            "file": ".",
            "kind": "workflow_stage",
            "stage_name": name,
            "stage_index": idx,
            "summary": f"Triage: {label_map.get(name, name)}",
            "detail": {
                "total_review_issues": open_review_count,
                "stage": name,
                "stage_label": label_map.get(name, name),
            },
            "primary_command": cmd,
            "blocked_by": blocked_by,
            "is_blocked": bool(blocked_by),
        })
    return items


def build_score_checkpoint_item(plan: dict, state: dict) -> dict | None:
    """Build a synthetic work item for ``workflow::score-checkpoint`` if it's in the queue.

    Returns ``None`` when the item is not pending.
    """
    from desloppify.engine._plan.stale_dimensions import WORKFLOW_SCORE_CHECKPOINT_ID

    if WORKFLOW_SCORE_CHECKPOINT_ID not in plan.get("queue_order", []):
        return None

    from desloppify import state as state_mod

    snapshot = state_mod.score_snapshot(state)
    strict = snapshot.strict if snapshot.strict is not None else 0.0
    plan_start = (plan.get("plan_start_scores") or {}).get("strict")
    delta = round(strict - plan_start, 1) if plan_start is not None else None
    delta_str = f" ({'+' if delta > 0 else ''}{delta:.1f})" if delta else ""

    return {
        "id": WORKFLOW_SCORE_CHECKPOINT_ID,
        "tier": 1,
        "confidence": "high",
        "detector": "workflow",
        "file": ".",
        "kind": "workflow_action",
        "summary": f"Score checkpoint: strict {strict:.1f}/100{delta_str}",
        "detail": {
            "strict": strict,
            "plan_start_strict": plan_start,
            "delta": delta,
        },
        "primary_command": f'desloppify plan resolve "{WORKFLOW_SCORE_CHECKPOINT_ID}" --note "Reviewed score checkpoint" --confirm',
        "blocked_by": [],
        "is_blocked": False,
    }


def build_create_plan_item(plan: dict) -> dict | None:
    """Build a synthetic work item for ``workflow::create-plan`` if it's in the queue.

    Returns ``None`` when the item is not pending.
    """
    from desloppify.engine._plan.stale_dimensions import WORKFLOW_CREATE_PLAN_ID

    if WORKFLOW_CREATE_PLAN_ID not in plan.get("queue_order", []):
        return None

    return {
        "id": WORKFLOW_CREATE_PLAN_ID,
        "tier": 1,
        "confidence": "high",
        "detector": "workflow",
        "file": ".",
        "kind": "workflow_action",
        "summary": "Create prioritized plan from review results",
        "detail": {},
        "primary_command": "desloppify plan",
        "blocked_by": [],
        "is_blocked": False,
    }


def build_subjective_items(
    state: dict, issues: dict, *, threshold: float = 100.0
) -> list[dict]:
    """Create synthetic subjective work items."""
    dim_scores = state.get("dimension_scores", {}) or {}
    if not dim_scores:
        return []
    threshold = max(0.0, min(100.0, float(threshold)))

    subjective_entries = all_subjective_entries(state, dim_scores=dim_scores)
    if not subjective_entries:
        return []
    unassessed_dims = {
        str(name).strip()
        for name in unassessed_subjective_dimensions(
            dim_scores
        )
    }

    # Review issues are keyed by raw dimension name (snake_case).
    review_open_by_dim: dict[str, int] = {}
    for issue in issues.values():
        if issue.get("status") != "open" or issue.get("detector") != "review":
            continue
        dim_key = str(detail_dict(issue).get("dimension", "")).strip().lower()
        if not dim_key:
            continue
        review_open_by_dim[dim_key] = review_open_by_dim.get(dim_key, 0) + 1

    items: list[dict] = []
    def _prepare_command(
        cli_keys: list[str],
        *,
        force_review_rerun: bool = False,
    ) -> str:
        command = "desloppify review --prepare"
        if cli_keys:
            command += " --dimensions " + ",".join(cli_keys)
        if force_review_rerun:
            command += " --force-review-rerun"
        return command

    for entry in subjective_entries:
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        strict_val = float(entry.get("strict", entry.get("score", 100.0)))
        if strict_val >= threshold:
            continue

        dim_key = _canonical_subjective_dimension_key(name)
        aliases = set(_subjective_dimension_aliases(name))
        cli_keys = [
            str(key).strip().lower()
            for key in entry.get("cli_keys", [])
            if str(key).strip()
        ]
        aliases.update(cli_keys)
        aliases.update(slugify(key) for key in cli_keys)
        open_review = sum(review_open_by_dim.get(alias, 0) for alias in aliases)
        is_unassessed = bool(entry.get("placeholder")) or (
            name in unassessed_dims
            or (strict_val <= 0.0 and int(entry.get("failing", 0)) == 0)
        )
        is_stale = bool(entry.get("stale"))
        # If review issues already exist for this dimension, triage/fix them
        # before suggesting another review refresh pass.
        if open_review > 0:
            primary_command = "desloppify show review --status open"
        else:
            primary_command = _prepare_command(cli_keys)
        stale_tag = " [stale — re-review]" if is_stale else ""
        summary = f"Subjective dimension below target: {name} ({strict_val:.1f}%){stale_tag}"
        items.append(
            {
                "id": f"subjective::{slugify(dim_key)}",
                "detector": "subjective_assessment",
                "file": ".",
                "confidence": "medium",
                "summary": summary,
                "detail": {
                    "dimension_name": name,
                    "dimension": dim_key,
                    "failing": int(entry.get("failing", 0)),
                    "strict_score": strict_val,
                    "open_review_issues": open_review,
                    "cli_keys": cli_keys,
                },
                "status": "open",
                "kind": "subjective_dimension",
                "primary_command": primary_command,
                "initial_review": is_unassessed,
                "stale_review": is_stale and not is_unassessed,
            }
        )
    return items


def build_import_scores_item(plan: dict, state: dict) -> dict | None:
    """Build a synthetic work item for ``workflow::import-scores`` if it's in the queue.

    Returns ``None`` when the item is not pending.
    """
    from desloppify.engine._plan.stale_dimensions import WORKFLOW_IMPORT_SCORES_ID

    if WORKFLOW_IMPORT_SCORES_ID not in plan.get("queue_order", []):
        return None

    return {
        "id": WORKFLOW_IMPORT_SCORES_ID,
        "tier": 1,
        "confidence": "high",
        "detector": "workflow",
        "file": ".",
        "kind": "workflow_action",
        "summary": "Import assessment scores with attestation",
        "detail": {
            "explanation": (
                "Review issues were imported but assessment scores were skipped "
                "(untrusted source). Re-import with attestation to update dimension scores."
            ),
        },
        "primary_command": (
            'desloppify review --import issues.json --attested-external '
            '--attest "I validated this review was completed without awareness '
            'of overall score and is unbiased."'
        ),
        "blocked_by": [],
        "is_blocked": False,
    }


def build_communicate_score_item(plan: dict, state: dict) -> dict | None:
    """Build a synthetic work item for ``workflow::communicate-score`` if it's in the queue.

    Returns ``None`` when the item is not pending.
    """
    from desloppify.engine._plan.stale_dimensions import WORKFLOW_COMMUNICATE_SCORE_ID

    if WORKFLOW_COMMUNICATE_SCORE_ID not in plan.get("queue_order", []):
        return None

    from desloppify import state as state_mod

    snapshot = state_mod.score_snapshot(state)
    strict = snapshot.strict if snapshot.strict is not None else 0.0
    plan_start = (plan.get("plan_start_scores") or {}).get("strict")
    delta = round(strict - plan_start, 1) if plan_start is not None else None
    delta_str = f" ({'+' if delta > 0 else ''}{delta:.1f})" if delta else ""

    return {
        "id": WORKFLOW_COMMUNICATE_SCORE_ID,
        "tier": 1,
        "confidence": "high",
        "detector": "workflow",
        "file": ".",
        "kind": "workflow_action",
        "summary": f"Communicate updated score to user: strict {strict:.1f}/100{delta_str}",
        "detail": {
            "strict": strict,
            "plan_start_strict": plan_start,
            "delta": delta,
        },
        "primary_command": (
            f'desloppify plan resolve "{WORKFLOW_COMMUNICATE_SCORE_ID}" '
            '--note "Score communicated" --confirm'
        ),
        "blocked_by": [],
        "is_blocked": False,
    }


__all__ = [
    "build_communicate_score_item",
    "build_create_plan_item",
    "build_import_scores_item",
    "build_score_checkpoint_item",
    "build_subjective_items",
    "build_triage_stage_items",
    "subjective_strict_scores",
]
