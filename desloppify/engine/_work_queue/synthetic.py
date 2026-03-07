"""Synthetic work-queue item builders and dimension scoring.

Builds workflow stage items, score checkpoint items, create-plan items,
subjective dimension items, and subjective score lookups.
"""

from __future__ import annotations

from typing import Any

from desloppify.engine._state.schema import StateModel
from desloppify.engine._scoring.subjective.core import DISPLAY_NAMES
from desloppify.engine._work_queue.helpers import (
    detail_dict,
    slugify,
)
from desloppify.engine._work_queue.synthetic_workflow import (
    build_communicate_score_item,
    build_create_plan_item,
    build_import_scores_item,
    build_score_checkpoint_item,
)
from desloppify.engine._work_queue.types import WorkQueueItem
from desloppify.engine.planning.scorecard_projection import (
    all_subjective_entries,
)
from desloppify.intelligence.integrity import (
    unassessed_subjective_dimensions,
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

def subjective_strict_scores(state: StateModel | dict[str, Any]) -> dict[str, float]:
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

def build_triage_stage_items(plan: dict, state: dict) -> list[WorkQueueItem]:
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
    stage_names = ("observe", "reflect", "organize", "enrich", "commit")

    items: list[WorkQueueItem] = []
    for sid, name in zip(TRIAGE_STAGE_IDS, stage_names, strict=False):
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

        item: WorkQueueItem = {
            "id": sid,
            "tier": 1,
            "confidence": "high",
            "detector": "triage",
            "file": ".",
            "kind": "workflow_stage",
            "summary": f"Triage: {label_map.get(name, name)}",
            "detail": {
                "total_review_issues": open_review_count,
                "stage": name,
                "stage_label": label_map.get(name, name),
            },
            "blocked_by": blocked_by,
            "is_blocked": bool(blocked_by),
        }
        item["primary_command"] = cmd
        items.append(item)
    return items


def build_subjective_items(
    state: dict, issues: dict, *, threshold: float = 100.0
) -> list[WorkQueueItem]:
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
        if issue.get("status") != "open":
            continue
        if issue.get("detector") == "review":
            dim_key = str(detail_dict(issue).get("dimension", "")).strip().lower()
            if dim_key:
                review_open_by_dim[dim_key] = review_open_by_dim.get(dim_key, 0) + 1

    items: list[WorkQueueItem] = []
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
        item: WorkQueueItem = {
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
        }
        item["primary_command"] = primary_command
        item["initial_review"] = is_unassessed
        items.append(item)
    return items


__all__ = [
    "build_communicate_score_item",
    "build_create_plan_item",
    "build_import_scores_item",
    "build_score_checkpoint_item",
    "build_subjective_items",
    "build_triage_stage_items",
    "subjective_strict_scores",
]
