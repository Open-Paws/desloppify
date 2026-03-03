"""Pure mutation operations on the plan model."""

from __future__ import annotations

from desloppify.engine._plan.schema import (
    Cluster,
    ExecutionLogEntry,
    PlanModel,
    SkipEntry,
    empty_plan,
    ensure_plan_defaults,
)
from desloppify.engine._state.schema import utc_now


_DEFAULT_MAX_LOG_ENTRIES = 10000


def _get_log_cap() -> int:
    """Read execution_log_max_entries from config. Returns 0 for unlimited."""
    try:
        from desloppify.core.config import load_config

        config = load_config()
        value = config.get("execution_log_max_entries", _DEFAULT_MAX_LOG_ENTRIES)
        return max(0, int(value))
    except (ImportError, OSError, ValueError, TypeError):
        return _DEFAULT_MAX_LOG_ENTRIES


def append_log_entry(
    plan: PlanModel,
    action: str,
    *,
    issue_ids: list[str] | None = None,
    cluster_name: str | None = None,
    actor: str = "user",
    note: str | None = None,
    detail: dict | None = None,
) -> None:
    """Append a structured entry to the plan's execution log."""
    log = plan.get("execution_log", [])
    entry: ExecutionLogEntry = {
        "timestamp": utc_now(),
        "action": action,
        "issue_ids": issue_ids or [],
        "cluster_name": cluster_name,
        "actor": actor,
        "note": note,
        "detail": detail or {},
    }
    log.append(entry)
    cap = _get_log_cap()
    if cap > 0 and len(log) > cap:
        plan["execution_log"] = log[-cap:]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _remove_id_from_lists(plan: PlanModel, issue_id: str) -> None:
    """Remove a issue ID from queue_order and skipped."""
    order: list[str] = plan["queue_order"]
    skipped: dict[str, SkipEntry] = plan.get("skipped", {})
    if issue_id in order:
        order.remove(issue_id)
    skipped.pop(issue_id, None)


def _resolve_position(
    order: list[str],
    position: str,
    target: str | None = None,
    offset: int | None = None,
    issue_ids: list[str] | None = None,
) -> int:
    """Resolve a position specifier to an insertion index.

    *issue_ids* are the IDs being moved — used to calculate relative
    positions when they already exist in the list.
    """
    moving = set(issue_ids or [])

    if position == "top":
        return 0
    if position == "bottom":
        return len(order)

    if position in {"before", "after"} and target:
        return _resolve_relative_position(order, moving, position=position, target=target)

    if position in {"up", "down"} and offset is not None:
        return _resolve_offset_position(
            order,
            moving,
            position=position,
            offset=offset,
            issue_ids=issue_ids,
        )

    return len(order)


def _resolve_relative_position(
    order: list[str],
    moving: set[str],
    *,
    position: str,
    target: str,
) -> int:
    for i, item_id in enumerate(order):
        if item_id == target and item_id not in moving:
            return i if position == "before" else i + 1
    return 0 if position == "before" else len(order)


def _find_index(items: list[str], target: str) -> int | None:
    for i, item_id in enumerate(items):
        if item_id == target:
            return i
    return None


def _resolve_offset_position(
    order: list[str],
    moving: set[str],
    *,
    position: str,
    offset: int,
    issue_ids: list[str] | None,
) -> int:
    if not issue_ids:
        return 0 if position == "up" else len(order)
    first_id = issue_ids[0]
    clean_order = [x for x in order if x not in moving]
    current_idx = _find_index(clean_order, first_id)
    if current_idx is None:
        if position == "up":
            return max(0, len(clean_order) - offset)
        return len(clean_order)
    if position == "up":
        return max(0, current_idx - offset)
    return min(len(clean_order), current_idx + offset)


# ---------------------------------------------------------------------------
# Move items
# ---------------------------------------------------------------------------

def move_items(
    plan: PlanModel,
    issue_ids: list[str],
    position: str,
    target: str | None = None,
    offset: int | None = None,
) -> int:
    """Move issue IDs to a position in queue_order. Returns count moved."""
    ensure_plan_defaults(plan)

    # Triage stage IDs are workflow-managed and cannot be manually reordered
    from desloppify.engine._plan.stale_dimensions import TRIAGE_IDS
    issue_ids = [fid for fid in issue_ids if fid not in TRIAGE_IDS]
    if not issue_ids:
        return 0

    order: list[str] = plan["queue_order"]

    # Remove from skipped if present
    skipped: dict[str, SkipEntry] = plan.get("skipped", {})
    for fid in issue_ids:
        skipped.pop(fid, None)

    # Remove from current position in order
    for fid in issue_ids:
        if fid in order:
            order.remove(fid)

    # Resolve insertion point
    idx = _resolve_position(order, position, target, offset, issue_ids)

    # Insert in original order
    for i, fid in enumerate(issue_ids):
        order.insert(idx + i, fid)

    # Track user-promoted IDs only when explicitly moved to the front.
    # Moving to bottom/down/after should not create a promotion barrier.
    if position == "top":
        promoted: list[str] = plan.get("promoted_ids", [])
        existing_promoted = set(promoted)
        for fid in issue_ids:
            if fid not in existing_promoted:
                promoted.append(fid)
                existing_promoted.add(fid)
        plan["promoted_ids"] = promoted

    return len(issue_ids)


# ---------------------------------------------------------------------------
# Skip / unskip
# ---------------------------------------------------------------------------

def skip_items(
    plan: PlanModel,
    issue_ids: list[str],
    *,
    kind: str = "temporary",
    reason: str | None = None,
    note: str | None = None,
    attestation: str | None = None,
    review_after: int | None = None,
    scan_count: int = 0,
) -> int:
    """Move issue IDs to the skipped dict. Returns count skipped."""
    ensure_plan_defaults(plan)
    now = utc_now()
    count = 0
    skipped: dict[str, SkipEntry] = plan["skipped"]
    skip_set = set(issue_ids)
    promoted: list[str] = plan.get("promoted_ids", [])
    plan["promoted_ids"] = [p for p in promoted if p not in skip_set]
    for fid in issue_ids:
        _remove_id_from_lists(plan, fid)
        skipped[fid] = {
            "issue_id": fid,
            "kind": kind,
            "reason": reason,
            "note": note,
            "attestation": attestation,
            "created_at": now,
            "review_after": review_after,
            "skipped_at_scan": scan_count,
        }
        count += 1
    return count


def unskip_items(
    plan: PlanModel, issue_ids: list[str]
) -> tuple[int, list[str]]:
    """Bring issue IDs back from skipped to the end of queue_order.

    Returns ``(count_unskipped, permanent_ids_needing_state_reopen)``
    where the second list contains IDs that were permanent or false_positive
    and need their state-layer status reopened by the caller.
    """
    ensure_plan_defaults(plan)
    count = 0
    need_reopen: list[str] = []
    skipped: dict[str, SkipEntry] = plan["skipped"]
    for fid in issue_ids:
        entry = skipped.pop(fid, None)
        if entry is not None:
            if entry.get("kind") in ("permanent", "false_positive"):
                need_reopen.append(fid)
            if fid not in plan["queue_order"]:
                plan["queue_order"].append(fid)
            count += 1
    return count, need_reopen


def resurface_stale_skips(
    plan: PlanModel, current_scan_count: int
) -> list[str]:
    """Move temporary skips past their review_after threshold back to queue.

    Returns list of resurfaced issue IDs.
    """
    ensure_plan_defaults(plan)
    skipped: dict[str, SkipEntry] = plan["skipped"]
    resurfaced: list[str] = []
    for fid in list(skipped):
        entry = skipped[fid]
        if entry.get("kind") != "temporary":
            continue
        review_after = entry.get("review_after")
        if review_after is None:
            continue
        skipped_at = entry.get("skipped_at_scan", 0)
        if current_scan_count >= skipped_at + review_after:
            skipped.pop(fid)
            if fid not in plan["queue_order"]:
                plan["queue_order"].append(fid)
            resurfaced.append(fid)
    return resurfaced


# ---------------------------------------------------------------------------
# Describe / annotate
# ---------------------------------------------------------------------------

def describe_issue(
    plan: PlanModel, issue_id: str, description: str | None
) -> None:
    """Set or clear an augmented description on a issue."""
    ensure_plan_defaults(plan)
    now = utc_now()
    overrides = plan["overrides"]
    if issue_id not in overrides:
        overrides[issue_id] = {"issue_id": issue_id, "created_at": now}
    overrides[issue_id]["description"] = description
    overrides[issue_id]["updated_at"] = now


def annotate_issue(
    plan: PlanModel, issue_id: str, note: str | None
) -> None:
    """Set or clear a note on a issue."""
    ensure_plan_defaults(plan)
    now = utc_now()
    overrides = plan["overrides"]
    if issue_id not in overrides:
        overrides[issue_id] = {"issue_id": issue_id, "created_at": now}
    overrides[issue_id]["note"] = note
    overrides[issue_id]["updated_at"] = now


# ---------------------------------------------------------------------------
# Clusters
# ---------------------------------------------------------------------------

def create_cluster(
    plan: PlanModel,
    name: str,
    description: str | None = None,
    action: str | None = None,
) -> Cluster:
    """Create a named cluster. Raises ValueError if it already exists."""
    ensure_plan_defaults(plan)
    if name.startswith("auto/"):
        raise ValueError(
            f"Cluster names starting with 'auto/' are reserved for auto-clusters: {name!r}"
        )
    if name.startswith("epic/"):
        raise ValueError(
            f"Cluster names starting with 'epic/' are reserved for triage epics: {name!r}"
        )
    if name in plan["clusters"]:
        raise ValueError(f"Cluster {name!r} already exists")
    now = utc_now()
    cluster: Cluster = {
        "name": name,
        "description": description,
        "issue_ids": [],
        "created_at": now,
        "updated_at": now,
        "auto": False,
        "cluster_key": "",
        "action": action,
        "user_modified": False,
    }
    plan["clusters"][name] = cluster
    return cluster


def add_to_cluster(
    plan: PlanModel, cluster_name: str, issue_ids: list[str]
) -> int:
    """Add issue IDs to a cluster. Returns count added."""
    ensure_plan_defaults(plan)
    cluster = plan["clusters"].get(cluster_name)
    if cluster is None:
        raise ValueError(f"Cluster {cluster_name!r} does not exist")

    member_ids: list[str] = cluster["issue_ids"]
    count = 0
    now = utc_now()
    for fid in issue_ids:
        if fid not in member_ids:
            member_ids.append(fid)
            count += 1
        # Update override to track cluster membership
        overrides = plan["overrides"]
        if fid not in overrides:
            overrides[fid] = {"issue_id": fid, "created_at": now}
        overrides[fid]["cluster"] = cluster_name
        overrides[fid]["updated_at"] = now

    cluster["updated_at"] = now
    return count


def remove_from_cluster(
    plan: PlanModel, cluster_name: str, issue_ids: list[str]
) -> int:
    """Remove issue IDs from a cluster. Returns count removed."""
    ensure_plan_defaults(plan)
    cluster = plan["clusters"].get(cluster_name)
    if cluster is None:
        raise ValueError(f"Cluster {cluster_name!r} does not exist")

    member_ids: list[str] = cluster["issue_ids"]
    now = utc_now()
    count = 0
    for fid in issue_ids:
        if fid in member_ids:
            member_ids.remove(fid)
            count += 1
        # Clear cluster from override
        override = plan["overrides"].get(fid)
        if override and override.get("cluster") == cluster_name:
            override["cluster"] = None
            override["updated_at"] = now

    # Mark auto-clusters as user_modified when items are manually removed
    if count > 0 and cluster.get("auto"):
        cluster["user_modified"] = True

    cluster["updated_at"] = now
    return count


def delete_cluster(plan: PlanModel, name: str) -> list[str]:
    """Delete a cluster and clear cluster refs from overrides. Returns orphaned IDs."""
    ensure_plan_defaults(plan)
    cluster = plan["clusters"].pop(name, None)
    if cluster is None:
        raise ValueError(f"Cluster {name!r} does not exist")

    orphaned = list(cluster.get("issue_ids", []))
    now = utc_now()
    for fid in orphaned:
        override = plan["overrides"].get(fid)
        if override and override.get("cluster") == name:
            override["cluster"] = None
            override["updated_at"] = now

    if plan.get("active_cluster") == name:
        plan["active_cluster"] = None

    return orphaned


def merge_clusters(
    plan: PlanModel, source_name: str, target_name: str
) -> tuple[int, list[str]]:
    """Move all source issues to target, copy missing metadata, delete source.

    Returns ``(added_count, source_issue_ids)``.
    """
    ensure_plan_defaults(plan)
    if source_name == target_name:
        raise ValueError("Cannot merge a cluster into itself")
    source = plan["clusters"].get(source_name)
    if source is None:
        raise ValueError(f"Source cluster {source_name!r} does not exist")
    target = plan["clusters"].get(target_name)
    if target is None:
        raise ValueError(f"Target cluster {target_name!r} does not exist")

    source_ids = list(source.get("issue_ids", []))
    target_ids: list[str] = target["issue_ids"]
    now = utc_now()

    # Add source issues to target (deduplicate)
    existing = set(target_ids)
    added = 0
    for fid in source_ids:
        if fid not in existing:
            target_ids.append(fid)
            existing.add(fid)
            added += 1
        # Update override to point to target cluster
        overrides = plan["overrides"]
        if fid not in overrides:
            overrides[fid] = {"issue_id": fid, "created_at": now}
        overrides[fid]["cluster"] = target_name
        overrides[fid]["updated_at"] = now

    # Copy metadata from source if target is missing them
    if not target.get("description") and source.get("description"):
        target["description"] = source["description"]
    if not target.get("action_steps") and source.get("action_steps"):
        target["action_steps"] = list(source["action_steps"])
    if not target.get("action") and source.get("action"):
        target["action"] = source["action"]

    target["updated_at"] = now

    # Delete source cluster
    plan["clusters"].pop(source_name, None)
    if plan.get("active_cluster") == source_name:
        plan["active_cluster"] = None

    return added, source_ids


def move_cluster(
    plan: PlanModel,
    cluster_name: str,
    position: str,
    target: str | None = None,
    offset: int | None = None,
) -> int:
    """Move all cluster members as a contiguous block. Returns count moved."""
    ensure_plan_defaults(plan)
    cluster = plan["clusters"].get(cluster_name)
    if cluster is None:
        raise ValueError(f"Cluster {cluster_name!r} does not exist")

    member_ids = list(cluster.get("issue_ids", []))
    if not member_ids:
        return 0

    return move_items(plan, member_ids, position, target, offset)


# ---------------------------------------------------------------------------
# Focus
# ---------------------------------------------------------------------------

def set_focus(plan: PlanModel, cluster_name: str) -> None:
    """Set the active cluster focus."""
    ensure_plan_defaults(plan)
    if cluster_name not in plan["clusters"]:
        raise ValueError(f"Cluster {cluster_name!r} does not exist")
    plan["active_cluster"] = cluster_name


def clear_focus(plan: PlanModel) -> None:
    """Clear the active cluster focus."""
    ensure_plan_defaults(plan)
    plan["active_cluster"] = None


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

def reset_plan(plan: PlanModel) -> None:
    """Reset plan to empty state, preserving version and created timestamp.

    Sets ``plan_start_scores`` to a sentinel so the next scan seeds real
    scores instead of incorrectly treating the reset as a completed cycle.
    """
    created = plan.get("created", utc_now())
    plan.clear()
    for k, v in empty_plan().items():
        plan[k] = v
    plan["created"] = created
    # Sentinel: truthy so ``not plan.get("plan_start_scores")`` is False,
    # but recognized by _seed_plan_start_scores as needing replacement.
    plan["plan_start_scores"] = {"reset": True}


def purge_ids(plan: PlanModel, issue_ids: list[str]) -> int:
    """Remove issue IDs from the plan entirely.

    Cleans queue_order, skipped, and all cluster memberships.
    Does NOT touch overrides (descriptions/notes are kept for history).
    Returns count of IDs that were actually present somewhere.
    """
    ensure_plan_defaults(plan)
    found = 0

    purge_set = set(issue_ids)
    promoted: list[str] = plan.get("promoted_ids", [])
    plan["promoted_ids"] = [p for p in promoted if p not in purge_set]

    order: list[str] = plan["queue_order"]
    skipped: dict[str, SkipEntry] = plan["skipped"]
    for fid in issue_ids:
        was_present = False
        if fid in order:
            order.remove(fid)
            was_present = True
        if fid in skipped:
            skipped.pop(fid)
            was_present = True
        for cluster in plan.get("clusters", {}).values():
            ids = cluster.get("issue_ids", [])
            if fid in ids:
                ids.remove(fid)
                was_present = True
        # Clear stale cluster reference from override (preserve notes/descriptions)
        override = plan.get("overrides", {}).get(fid)
        if override and override.get("cluster"):
            override["cluster"] = None
            override["updated_at"] = utc_now()
        if was_present:
            found += 1

    return found


__all__ = [
    "add_to_cluster",
    "annotate_issue",
    "append_log_entry",
    "clear_focus",
    "create_cluster",
    "delete_cluster",
    "describe_issue",
    "merge_clusters",
    "move_cluster",
    "move_items",
    "purge_ids",
    "remove_from_cluster",
    "reset_plan",
    "resurface_stale_skips",
    "set_focus",
    "skip_items",
    "unskip_items",
]
