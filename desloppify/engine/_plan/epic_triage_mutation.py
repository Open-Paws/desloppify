"""Epic triage plan mutation — applies parsed triage results to the living plan."""

from __future__ import annotations

from desloppify.engine._plan.schema import (
    EPIC_PREFIX,
    Cluster,
    PlanModel,
    ensure_plan_defaults,
)
from desloppify.engine._plan.stale_dimensions import review_issue_snapshot_hash
from desloppify.engine._state.schema import StateModel, utc_now

from desloppify.engine._plan.epic_triage import TriageMutationResult, TriageResult


def apply_triage_to_plan(
    plan: PlanModel,
    state: StateModel,
    triage: TriageResult,
    *,
    trigger: str = "manual",
) -> TriageMutationResult:
    """Apply parsed triage result to the living plan.

    1. Creates/updates triage-clusters in plan["clusters"]
    2. Marks dismissed issues as triaged_out skips
    3. Reorders queue_order to group epic members by dependency_order
    4. Updates epic_triage_meta with snapshot hash
    """
    ensure_plan_defaults(plan)
    now = utc_now()
    result = TriageMutationResult()
    result.strategy_summary = triage.strategy_summary

    clusters = plan["clusters"]
    skipped: dict = plan["skipped"]
    order: list[str] = plan["queue_order"]
    meta = plan.get("epic_triage_meta", {})
    version = int(meta.get("version", 0)) + 1
    result.triage_version = version

    # --- Update/create triage-clusters ------------------------------------
    for epic_data in sorted(triage.epics, key=lambda e: e.get("dependency_order", 999)):
        raw_name = epic_data["name"]
        epic_name = f"{EPIC_PREFIX}{raw_name}" if not raw_name.startswith(EPIC_PREFIX) else raw_name

        existing = clusters.get(epic_name)
        if existing and existing.get("thesis"):
            # Update existing triage-cluster
            existing["thesis"] = epic_data["thesis"]
            existing["direction"] = epic_data["direction"]
            existing["root_cause"] = epic_data.get("root_cause", "")
            existing["issue_ids"] = epic_data["issue_ids"]
            existing["dismissed"] = epic_data.get("dismissed", [])
            existing["agent_safe"] = epic_data.get("agent_safe", False)
            existing["dependency_order"] = epic_data["dependency_order"]
            existing["action_steps"] = epic_data.get("action_steps", [])
            existing["updated_at"] = now
            existing["triage_version"] = version
            existing["description"] = epic_data["thesis"]
            # Don't overwrite in_progress status from agent
            if existing.get("status") != "in_progress":
                existing["status"] = epic_data.get("status", "pending")
            result.epics_updated += 1
        else:
            # Create new triage-cluster
            cluster: Cluster = {
                "name": epic_name,
                "description": epic_data["thesis"],
                "issue_ids": epic_data["issue_ids"],
                "auto": True,
                "cluster_key": f"epic::{epic_name}",
                "action": f"desloppify plan focus {epic_name}",
                "user_modified": False,
                "created_at": now,
                "updated_at": now,
                # Epic fields
                "thesis": epic_data["thesis"],
                "direction": epic_data["direction"],
                "root_cause": epic_data.get("root_cause", ""),
                "supersedes": [],
                "dismissed": epic_data.get("dismissed", []),
                "agent_safe": epic_data.get("agent_safe", False),
                "dependency_order": epic_data["dependency_order"],
                "action_steps": epic_data.get("action_steps", []),
                "source_clusters": [],
                "status": epic_data.get("status", "pending"),
                "triage_version": version,
            }
            clusters[epic_name] = cluster
            result.epics_created += 1

    # --- Dismiss issues ---------------------------------------------------
    dismissed_ids: list[str] = []
    for df in triage.dismissed_issues:
        fid = df.issue_id
        dismissed_ids.append(fid)
        # Remove from queue, add to skipped as triaged_out
        if fid in order:
            order.remove(fid)
        skipped[fid] = {
            "issue_id": fid,
            "kind": "triaged_out",
            "reason": df.reason,
            "note": f"Dismissed by epic triage v{version}",
            "attestation": None,
            "created_at": now,
            "review_after": None,
            "skipped_at_scan": int(state.get("scan_count", 0)),
        }
        result.issues_dismissed += 1

    # Also handle per-epic dismissed lists
    for epic_data in triage.epics:
        for fid in epic_data.get("dismissed", []):
            if fid not in dismissed_ids and fid in order:
                order.remove(fid)
                dismissed_ids.append(fid)
                skipped[fid] = {
                    "issue_id": fid,
                    "kind": "triaged_out",
                    "reason": f"Dismissed by epic triage v{version}",
                    "note": None,
                    "attestation": None,
                    "created_at": now,
                    "review_after": None,
                    "skipped_at_scan": int(state.get("scan_count", 0)),
                }
                result.issues_dismissed += 1

    # --- Reorder queue: epic issues grouped by dependency_order -----------
    epic_issue_ids: set[str] = set()
    epic_ordered_ids: list[str] = []
    for epic_data in sorted(triage.epics, key=lambda e: e.get("dependency_order", 999)):
        for fid in epic_data["issue_ids"]:
            if fid not in epic_issue_ids and fid not in dismissed_ids:
                epic_issue_ids.add(fid)
                epic_ordered_ids.append(fid)

    # Rebuild order: epic items first (by dependency), then non-epic items in original order
    non_epic_items = [fid for fid in order if fid not in epic_issue_ids]
    # Insert epic items at the front.
    new_order: list[str] = []
    new_order.extend(epic_ordered_ids)
    new_order.extend(non_epic_items)
    order.clear()
    order.extend(new_order)

    # --- Update triage meta -----------------------------------------------
    current_hash = review_issue_snapshot_hash(state)
    open_review_ids = sorted(
        fid for fid, f in state.get("issues", {}).items()
        if f.get("status") == "open"
        and f.get("detector") in ("review", "concerns")
    )

    plan["epic_triage_meta"] = {
        "triaged_ids": open_review_ids,
        "last_run": now,
        "version": version,
        "dismissed_ids": dismissed_ids,
        "issue_snapshot_hash": current_hash,
        "strategy_summary": triage.strategy_summary,
        "trigger": trigger,
    }
    plan["updated"] = now

    return result
