"""Migration/default helpers for living plan schema payloads."""

from __future__ import annotations

from typing import Any

from desloppify.engine._state.schema import utc_now


def ensure_container_types(plan: dict[str, Any]) -> None:
    if not isinstance(plan.get("queue_order"), list):
        plan["queue_order"] = []
    if not isinstance(plan.get("deferred"), list):
        plan["deferred"] = []
    if not isinstance(plan.get("skipped"), dict):
        plan["skipped"] = {}
    if not isinstance(plan.get("overrides"), dict):
        plan["overrides"] = {}
    if not isinstance(plan.get("clusters"), dict):
        plan["clusters"] = {}
    if not isinstance(plan.get("superseded"), dict):
        plan["superseded"] = {}
    if not isinstance(plan.get("promoted_ids"), list):
        plan["promoted_ids"] = []
    if not isinstance(plan.get("plan_start_scores"), dict):
        plan["plan_start_scores"] = {}
    if not isinstance(plan.get("execution_log"), list):
        plan["execution_log"] = []
    if not isinstance(plan.get("epic_triage_meta"), dict):
        plan["epic_triage_meta"] = {}
    # Legacy "finding_snapshot_hash" → "issue_snapshot_hash" in epic_triage_meta
    _meta = plan["epic_triage_meta"]
    if "finding_snapshot_hash" in _meta and "issue_snapshot_hash" not in _meta:
        _meta["issue_snapshot_hash"] = _meta.pop("finding_snapshot_hash")
    elif "finding_snapshot_hash" in _meta:
        _meta.pop("finding_snapshot_hash", None)
    if not isinstance(plan.get("commit_log"), list):
        plan["commit_log"] = []
    # Legacy "uncommitted_findings" → "uncommitted_issues"
    if "uncommitted_findings" in plan and "uncommitted_issues" not in plan:
        plan["uncommitted_issues"] = plan.pop("uncommitted_findings")
    elif "uncommitted_findings" in plan:
        plan.pop("uncommitted_findings", None)
    if not isinstance(plan.get("uncommitted_issues"), list):
        plan["uncommitted_issues"] = []
    if "commit_tracking_branch" not in plan:
        plan["commit_tracking_branch"] = None


def migrate_deferred_to_skipped(plan: dict[str, Any]) -> None:
    deferred: list[str] = plan["deferred"]
    skipped: dict[str, dict[str, Any]] = plan["skipped"]
    if not deferred:
        return

    now = utc_now()
    for issue_id in list(deferred):
        if issue_id in skipped:
            continue
        skipped[issue_id] = {
            "issue_id": issue_id,
            "kind": "temporary",
            "reason": None,
            "note": None,
            "attestation": None,
            "created_at": now,
            "review_after": None,
            "skipped_at_scan": 0,
        }
    deferred.clear()


def normalize_cluster_defaults(plan: dict[str, Any]) -> None:
    for cluster in plan["clusters"].values():
        if not isinstance(cluster, dict):
            continue
        if not isinstance(cluster.get("issue_ids"), list):
            cluster["issue_ids"] = []
        cluster.setdefault("auto", False)
        cluster.setdefault("cluster_key", "")
        cluster.setdefault("action", None)
        cluster.setdefault("user_modified", False)


def migrate_epics_to_clusters(plan: dict[str, Any]) -> None:
    """Migrate v3 top-level ``epics`` dict into ``clusters`` (v4 unification)."""
    epics = plan.pop("epics", None)
    if not isinstance(epics, dict) or not epics:
        return
    clusters = plan["clusters"]
    now = utc_now()
    for name, epic in epics.items():
        if not isinstance(epic, dict):
            continue
        if name in clusters:
            continue
        clusters[name] = {
            "name": name,
            "description": epic.get("thesis", ""),
            "issue_ids": epic.get("issue_ids", []),
            "auto": True,
            "cluster_key": f"epic::{name}",
            "action": f"desloppify plan focus {name}",
            "user_modified": False,
            "created_at": epic.get("created_at", now),
            "updated_at": epic.get("updated_at", now),
            "thesis": epic.get("thesis", ""),
            "direction": epic.get("direction", "simplify"),
            "root_cause": epic.get("root_cause", ""),
            "supersedes": epic.get("supersedes", []),
            "dismissed": epic.get("dismissed", []),
            "agent_safe": epic.get("agent_safe", False),
            "dependency_order": epic.get("dependency_order", 999),
            "action_steps": epic.get("action_steps", []),
            "source_clusters": epic.get("source_clusters", []),
            "status": epic.get("status", "pending"),
            "triage_version": epic.get("triage_version", epic.get("synthesis_version", 0)),
        }


def migrate_v5_to_v6(plan: dict[str, Any]) -> None:
    """Migrate v5 → v6: unified queue system."""
    from desloppify.engine._plan.stale_dimensions import (
        TRIAGE_STAGE_IDS,
        WORKFLOW_CREATE_PLAN_ID,
    )

    order: list[str] = plan.get("queue_order", [])

    # Handle legacy synthesis::pending or triage::pending
    for legacy_pending in ("synthesis::pending", "triage::pending"):
        if legacy_pending in order:
            idx = order.index(legacy_pending)
            order.remove(legacy_pending)
            meta = plan.get("epic_triage_meta", plan.get("epic_synthesis_meta", {}))
            confirmed = set(meta.get("triage_stages", meta.get("synthesis_stages", {})).keys())
            stage_names = ("observe", "reflect", "organize", "commit")
            to_inject = [
                stage_id
                for stage_id, name in zip(TRIAGE_STAGE_IDS, stage_names)
                if name not in confirmed and stage_id not in order
            ]
            for offset, stage_id in enumerate(to_inject):
                order.insert(idx + offset, stage_id)
            break

    if plan.pop("pending_plan_gate", False):
        if WORKFLOW_CREATE_PLAN_ID not in order:
            insert_at = 0
            for idx, issue_id in enumerate(order):
                if issue_id.startswith("triage::") or issue_id.startswith("synthesis::"):
                    insert_at = idx + 1
            order.insert(insert_at, WORKFLOW_CREATE_PLAN_ID)
    else:
        plan.pop("pending_plan_gate", None)


def migrate_synthesis_to_triage(plan: dict[str, Any]) -> None:
    """Migrate synthesis::* → triage::* naming throughout the plan.

    - Renames ``synthesis::*`` IDs to ``triage::*`` in ``queue_order`` and ``skipped``
    - Renames ``epic_synthesis_meta`` key to ``epic_triage_meta``
    - Renames ``synthesis_stages`` to ``triage_stages`` inside that meta dict
    - Renames ``synthesized_ids`` to ``triaged_ids`` inside that meta dict
    - Renames ``synthesis_version`` to ``triage_version`` in cluster dicts
    """
    # Rename synthesis::* IDs in queue_order
    order: list[str] = plan.get("queue_order", [])
    for i, fid in enumerate(order):
        if fid.startswith("synthesis::"):
            order[i] = "triage::" + fid[len("synthesis::"):]

    # Rename synthesis::* IDs in skipped
    skipped: dict = plan.get("skipped", {})
    synth_keys = [k for k in skipped if k.startswith("synthesis::")]
    for old_key in synth_keys:
        new_key = "triage::" + old_key[len("synthesis::"):]
        entry = skipped.pop(old_key)
        if isinstance(entry, dict):
            entry["issue_id"] = new_key
        skipped[new_key] = entry

    # Rename epic_synthesis_meta → epic_triage_meta
    if "epic_synthesis_meta" in plan:
        meta = plan.pop("epic_synthesis_meta")
        if isinstance(meta, dict):
            # Rename synthesis_stages → triage_stages
            if "synthesis_stages" in meta:
                meta["triage_stages"] = meta.pop("synthesis_stages")
            # Rename synthesized_ids → triaged_ids
            if "synthesized_ids" in meta:
                meta["triaged_ids"] = meta.pop("synthesized_ids")
        plan["epic_triage_meta"] = meta

    # Rename synthesized_out → triaged_out skip kind
    for entry in skipped.values():
        if isinstance(entry, dict) and entry.get("kind") == "synthesized_out":
            entry["kind"] = "triaged_out"

    # Rename synthesis_version → triage_version in clusters
    for cluster in plan.get("clusters", {}).values():
        if not isinstance(cluster, dict):
            continue
        if "synthesis_version" in cluster:
            cluster["triage_version"] = cluster.pop("synthesis_version")


__all__ = [
    "ensure_container_types",
    "migrate_deferred_to_skipped",
    "migrate_epics_to_clusters",
    "migrate_synthesis_to_triage",
    "migrate_v5_to_v6",
    "normalize_cluster_defaults",
]

