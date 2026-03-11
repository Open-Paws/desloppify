"""Migration/default helpers for living plan schema payloads."""

from __future__ import annotations

import re
from typing import Any

from desloppify.engine._plan.schema.helpers import (
    _cleanup_synthesis_meta,
    _drop_legacy_plan_keys,
    _has_synthesis_artifacts,
    _migrate_action_steps_to_v8,
)
from desloppify.engine._state.schema import utc_now

V7_SCHEMA_VERSION = 7
V8_SCHEMA_VERSION = 8
_HEX_SUFFIX_RE = re.compile(r"^[0-9a-f]{8}$")


def _rename_key(d: dict, old: str, new: str) -> bool:
    if old not in d:
        return False
    d.setdefault(new, d.pop(old))
    return True


def _ensure_container(
    plan: dict[str, Any],
    key: str,
    expected_type: type[list] | type[dict],
    default_factory,
) -> None:
    if not isinstance(plan.get(key), expected_type):
        plan[key] = default_factory()


def ensure_container_types(plan: dict[str, Any]) -> None:
    for key, expected_type, default_factory in (
        ("queue_order", list, list),
        ("deferred", list, list),
        ("skipped", dict, dict),
        ("overrides", dict, dict),
        ("clusters", dict, dict),
        ("superseded", dict, dict),
        ("promoted_ids", list, list),
        ("plan_start_scores", dict, dict),
        ("refresh_state", dict, dict),
        ("execution_log", list, list),
        ("epic_triage_meta", dict, dict),
    ):
        _ensure_container(plan, key, expected_type, default_factory)
    _rename_key(plan["epic_triage_meta"], "finding_snapshot_hash", "issue_snapshot_hash")
    _ensure_container(plan, "commit_log", list, list)
    _rename_key(plan, "uncommitted_findings", "uncommitted_issues")
    _ensure_container(plan, "uncommitted_issues", list, list)
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


def _normalize_cluster_issue_id(raw_id: object) -> str | None:
    if not isinstance(raw_id, str):
        return None
    issue_id = raw_id.strip()
    if not issue_id:
        return None
    if _HEX_SUFFIX_RE.fullmatch(issue_id):
        return None
    if issue_id.startswith("review::") or issue_id.startswith("concerns::"):
        parts = issue_id.split("::")
        if len(parts) >= 2 and _HEX_SUFFIX_RE.fullmatch(parts[-1]):
            return "::".join(parts[:-1])
    return issue_id


def _override_cluster_members(plan: dict[str, Any]) -> dict[str, list[str]]:
    members: dict[str, list[str]] = {}
    seen_by_cluster: dict[str, set[str]] = {}
    overrides = plan.get("overrides", {})
    if not isinstance(overrides, dict):
        return members

    for issue_id, override in overrides.items():
        normalized_issue_id = _normalize_cluster_issue_id(issue_id)
        if normalized_issue_id is None or not isinstance(override, dict):
            continue
        cluster_name = override.get("cluster")
        if not isinstance(cluster_name, str) or not cluster_name.strip():
            continue
        cluster_name = cluster_name.strip()
        bucket = members.setdefault(cluster_name, [])
        seen = seen_by_cluster.setdefault(cluster_name, set())
        if normalized_issue_id in seen:
            continue
        seen.add(normalized_issue_id)
        bucket.append(normalized_issue_id)
    return members


def _execution_log_cluster_members(
    plan: dict[str, Any],
) -> tuple[dict[str, list[str]], dict[str, str]]:
    members: dict[str, list[str]] = {}
    hash_lookup: dict[str, str] = {}

    for entry in plan.get("execution_log", []):
        cluster_entry = _execution_log_cluster_entry(entry)
        if cluster_entry is None:
            continue
        cluster_name, action, normalized_issue_ids = cluster_entry
        if action == "cluster_delete":
            members.pop(cluster_name, None)
            continue
        if not normalized_issue_ids:
            continue
        _apply_execution_log_cluster_action(
            members,
            hash_lookup,
            cluster_name=cluster_name,
            action=action,
            issue_ids=normalized_issue_ids,
        )

    return members, hash_lookup


def _execution_log_cluster_entry(
    entry: object,
) -> tuple[str, object, list[str]] | None:
    if not isinstance(entry, dict):
        return None
    cluster_name = entry.get("cluster_name")
    if not isinstance(cluster_name, str) or not cluster_name.strip():
        return None
    return (
        cluster_name.strip(),
        entry.get("action"),
        _normalized_execution_log_issue_ids(entry),
    )


def _normalized_execution_log_issue_ids(entry: dict[str, Any]) -> list[str]:
    return [
        issue_id
        for raw_id in entry.get("issue_ids", [])
        if (issue_id := _normalize_cluster_issue_id(raw_id)) is not None
    ]


def _apply_execution_log_cluster_action(
    members: dict[str, list[str]],
    hash_lookup: dict[str, str],
    *,
    cluster_name: str,
    action: object,
    issue_ids: list[str],
) -> None:
    if action == "cluster_remove":
        bucket = members.get(cluster_name, [])
        if bucket:
            remove_set = set(issue_ids)
            members[cluster_name] = [
                issue_id for issue_id in bucket if issue_id not in remove_set
            ]
        return
    if action in {"cluster_add", "cluster_create", "cluster_update"}:
        _append_execution_log_members(
            members,
            hash_lookup,
            cluster_name=cluster_name,
            issue_ids=issue_ids,
        )


def _append_execution_log_members(
    members: dict[str, list[str]],
    hash_lookup: dict[str, str],
    *,
    cluster_name: str,
    issue_ids: list[str],
) -> None:
    bucket = members.setdefault(cluster_name, [])
    seen = set(bucket)
    for issue_id in issue_ids:
        if issue_id in seen:
            continue
        seen.add(issue_id)
        bucket.append(issue_id)
        _record_execution_log_hash(hash_lookup, issue_id)


def _record_execution_log_hash(hash_lookup: dict[str, str], issue_id: str) -> None:
    parts = issue_id.split("::")
    if parts and _HEX_SUFFIX_RE.fullmatch(parts[-1]):
        hash_lookup[parts[-1]] = issue_id


def normalize_cluster_defaults(plan: dict[str, Any]) -> None:
    recovered_members, hash_lookup = _execution_log_cluster_members(plan)
    override_members = _override_cluster_members(plan)

    for cluster in plan["clusters"].values():
        if not isinstance(cluster, dict):
            continue
        if not isinstance(cluster.get("issue_ids"), list):
            cluster["issue_ids"] = []
        cluster["issue_ids"] = _normalized_cluster_issue_ids(
            cluster,
            recovered_members=recovered_members,
            override_members=override_members,
            hash_lookup=hash_lookup,
        )
        cluster.setdefault("auto", False)
        cluster.setdefault("cluster_key", "")
        cluster.setdefault("action", None)
        cluster.setdefault("user_modified", False)


def _append_normalized_issue_id(
    raw_id: object,
    *,
    normalized_issue_ids: list[str],
    seen: set[str],
    hash_lookup: dict[str, str],
) -> None:
    issue_id = _normalize_cluster_issue_id(raw_id)
    if issue_id is None and isinstance(raw_id, str) and _HEX_SUFFIX_RE.fullmatch(raw_id):
        issue_id = hash_lookup.get(raw_id)
    if issue_id is None or issue_id in seen:
        return
    seen.add(issue_id)
    normalized_issue_ids.append(issue_id)


def _iter_cluster_raw_issue_ids(
    cluster: dict[str, Any],
    *,
    recovered_members: dict[str, list[str]],
    override_members: dict[str, list[str]],
) -> list[object]:
    raw_issue_ids: list[object] = list(cluster.get("issue_ids", []))
    for step in cluster.get("action_steps", []):
        if isinstance(step, dict):
            raw_issue_ids.extend(step.get("issue_refs", []))

    cluster_name = cluster.get("name")
    if isinstance(cluster_name, str):
        raw_issue_ids.extend(recovered_members.get(cluster_name, []))
        raw_issue_ids.extend(override_members.get(cluster_name, []))
    return raw_issue_ids


def _normalized_cluster_issue_ids(
    cluster: dict[str, Any],
    *,
    recovered_members: dict[str, list[str]],
    override_members: dict[str, list[str]],
    hash_lookup: dict[str, str],
) -> list[str]:
    normalized_issue_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in _iter_cluster_raw_issue_ids(
        cluster,
        recovered_members=recovered_members,
        override_members=override_members,
    ):
        _append_normalized_issue_id(
            raw_id,
            normalized_issue_ids=normalized_issue_ids,
            seen=seen,
            hash_lookup=hash_lookup,
        )
    return normalized_issue_ids


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
    # cycle-break: schema_migrations.py ↔ schema.py (via stale_dimensions.py)
    from desloppify.engine._plan.constants import (
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
                for stage_id, name in zip(TRIAGE_STAGE_IDS, stage_names, strict=False)
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
    order: list[str] = plan.get("queue_order", [])
    for index, issue_id in enumerate(order):
        if issue_id.startswith("synthesis::"):
            order[index] = "triage::" + issue_id[len("synthesis::"):]

    skipped: dict = plan.get("skipped", {})
    for old_key in [key for key in skipped if key.startswith("synthesis::")]:
        new_key = "triage::" + old_key[len("synthesis::"):]
        entry = skipped.pop(old_key)
        if isinstance(entry, dict):
            entry["issue_id"] = new_key
        skipped[new_key] = entry

    meta = plan.pop("epic_synthesis_meta", None)
    if meta is not None:
        if isinstance(meta, dict):
            _rename_key(meta, "synthesis_stages", "triage_stages")
            _rename_key(meta, "synthesized_ids", "triaged_ids")
        plan["epic_triage_meta"] = meta

    for entry in skipped.values():
        if isinstance(entry, dict) and entry.get("kind") == "synthesized_out":
            entry["kind"] = "triaged_out"

    for cluster in plan.get("clusters", {}).values():
        if isinstance(cluster, dict):
            _rename_key(cluster, "synthesis_version", "triage_version")


def upgrade_plan_to_v7(plan: dict[str, Any]) -> bool:
    """Apply legacy migrations once and normalize onto v7-only keys.

    Returns ``True`` when any legacy migration or key cleanup was applied.
    """
    changed = False
    original_version = plan.get("version", 1)
    if not isinstance(original_version, int):
        original_version = 1

    ensure_container_types(plan)
    meta = plan.get("epic_triage_meta")
    queue_order = plan.get("queue_order", [])
    skipped = plan.get("skipped", {})
    clusters = plan.get("clusters", {})
    has_synthesis_artifacts = _has_synthesis_artifacts(
        queue_order=queue_order,
        skipped=skipped,
        clusters=clusters,
        meta=meta,
    )

    needs_legacy_upgrade = (
        original_version < V7_SCHEMA_VERSION
        or bool(plan.get("deferred"))
        or "epics" in plan
        or "epic_synthesis_meta" in plan
        or "pending_plan_gate" in plan
        or "uncommitted_findings" in plan
        or has_synthesis_artifacts
    )

    if needs_legacy_upgrade:
        migrate_deferred_to_skipped(plan)
        migrate_epics_to_clusters(plan)
        normalize_cluster_defaults(plan)
        migrate_v5_to_v6(plan)
        migrate_synthesis_to_triage(plan)
        changed = True
    else:
        normalize_cluster_defaults(plan)

    changed = _drop_legacy_plan_keys(
        plan,
        (
            "epics",
            "epic_synthesis_meta",
            "pending_plan_gate",
            "uncommitted_findings",
        ),
    ) or changed

    meta = plan.get("epic_triage_meta")
    if _cleanup_synthesis_meta(meta):
        changed = True

    if plan.get("version") != V7_SCHEMA_VERSION:
        plan["version"] = V7_SCHEMA_VERSION
        changed = True
    return changed


def upgrade_plan_to_v8(plan: dict[str, Any]) -> bool:
    """Apply v7 migrations then upgrade action_steps to structured ActionStep dicts.

    Returns ``True`` when any migration was applied.
    """
    changed = upgrade_plan_to_v7(plan)

    # Migrate action_steps from flat strings to ActionStep dicts
    for cluster in plan.get("clusters", {}).values():
        if isinstance(cluster, dict):
            if _migrate_action_steps_to_v8(cluster):
                changed = True

    if plan.get("version") != V8_SCHEMA_VERSION:
        plan["version"] = V8_SCHEMA_VERSION
        changed = True
    return changed


__all__ = [
    "ensure_container_types",
    "upgrade_plan_to_v7",
    "upgrade_plan_to_v8",
    "migrate_deferred_to_skipped",
    "migrate_epics_to_clusters",
    "migrate_synthesis_to_triage",
    "migrate_v5_to_v6",
    "normalize_cluster_defaults",
]
