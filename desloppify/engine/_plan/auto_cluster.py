"""Auto-clustering algorithm — groups issues into task clusters."""

from __future__ import annotations

import os
from collections import defaultdict

from desloppify.core.registry import DETECTORS, DetectorMeta
from desloppify.engine._plan.schema import Cluster, PlanModel, ensure_plan_defaults
from desloppify.engine._plan.stale_dimensions import (
    SUBJECTIVE_PREFIX,
    _current_stale_ids,
    current_under_target_ids,
    current_unscored_ids,
)
from desloppify.engine._plan.subjective_policy import (
    NON_OBJECTIVE_DETECTORS,
    SubjectiveVisibility,
    compute_subjective_visibility,
)
from desloppify.engine._state.schema import StateModel, utc_now

AUTO_PREFIX = "auto/"
_MIN_CLUSTER_SIZE = 2
_STALE_KEY = "subjective::stale"
_STALE_NAME = "auto/stale-review"
_UNSCORED_KEY = "subjective::unscored"
_UNSCORED_NAME = "auto/initial-review"
_UNDER_TARGET_KEY = "subjective::under-target"
_UNDER_TARGET_NAME = "auto/under-target-review"
_MIN_UNSCORED_CLUSTER_SIZE = 1


# ---------------------------------------------------------------------------
# Grouping key computation
# ---------------------------------------------------------------------------

def _extract_subtype(issue: dict) -> str | None:
    """Extract the subtype/kind from a issue.

    Checks detail.kind first, then falls back to parsing the issue ID
    (format: ``detector::file::subtype`` or ``detector::file::symbol::subtype``).
    """
    detail = issue.get("detail") or {}
    kind = detail.get("kind")
    if kind:
        return kind

    # Parse from issue ID — third segment is often the subtype
    fid = issue.get("id", "")
    parts = fid.split("::")
    if len(parts) >= 3:
        # For IDs like smells::file.py::silent_except, the subtype is parts[2]
        # For IDs like dict_keys::file.py::key::phantom_read, subtype is last part
        candidate = parts[-1]
        # Skip if it looks like a file path or symbol name (contains / or .)
        if "/" not in candidate and "." not in candidate:
            return candidate
    return None


def _grouping_key(issue: dict, meta: DetectorMeta | None) -> str | None:
    """Compute a deterministic grouping key for a issue.

    Returns None if the issue should not be auto-clustered.
    """
    detector = issue.get("detector", "")

    if meta is None:
        # Unknown detector — group by detector name
        return f"detector::{detector}"

    # Review issues → group by dimension
    if detector in ("review", "subjective_review"):
        detail = issue.get("detail") or {}
        dimension = detail.get("dimension", "")
        if dimension:
            return f"review::{dimension}"
        return f"detector::{detector}"

    # Per-file detectors (structural, responsibility_cohesion)
    if meta.needs_judgment and detector in (
        "structural", "responsibility_cohesion",
    ):
        file = issue.get("file", "")
        if file:
            basename = os.path.basename(file)
            return f"file::{detector}::{basename}"

    # Needs-judgment detectors — group by subtype when available
    if meta.needs_judgment:
        subtype = _extract_subtype(issue)
        if subtype:
            return f"typed::{detector}::{subtype}"

    # Pure auto-fix (no judgment needed) → all issues by detector
    if meta.action_type == "auto_fix" and not meta.needs_judgment:
        return f"auto::{detector}"

    # Everything else → by detector
    return f"detector::{detector}"


def _cluster_name_from_key(key: str) -> str:
    """Convert a grouping key to a cluster name with auto/ prefix."""
    # auto::unused → auto/unused
    # typed::dict_keys::phantom_read → auto/dict_keys-phantom_read
    # file::structural::big_file.py → auto/structural-big_file.py
    # review::abstraction_fitness → auto/review-abstraction_fitness
    # detector::security → auto/security
    parts = key.split("::")
    if len(parts) == 2:
        prefix_type = parts[0]
        # For review keys, keep the prefix for clarity
        if prefix_type == "review":
            return f"{AUTO_PREFIX}review-{parts[1]}"
        return f"{AUTO_PREFIX}{parts[1]}"
    if len(parts) == 3:
        return f"{AUTO_PREFIX}{parts[1]}-{parts[2]}"
    return f"{AUTO_PREFIX}{key.replace('::', '-')}"


# ---------------------------------------------------------------------------
# Description and action generation
# ---------------------------------------------------------------------------

def _generate_description(
    cluster_name: str,
    members: list[dict],
    meta: DetectorMeta | None,
    subtype: str | None,
) -> str:
    """Generate a human-readable cluster description."""
    count = len(members)
    detector = members[0].get("detector", "") if members else ""

    if detector in ("review", "subjective_review"):
        detail = (members[0].get("detail") or {}) if members else {}
        dimension = detail.get("dimension", detector)
        return f"Address {count} {dimension} review issues"

    if detector == "structural":
        files = {os.path.basename(m.get("file", "")) for m in members}
        if len(files) == 1:
            return f"Decompose {next(iter(files))}"
        return f"Decompose {count} large files"

    display = meta.display if meta else detector
    if subtype:
        label = subtype.replace("_", " ")
        return f"Fix {count} {label} issues"

    if meta and meta.action_type == "auto_fix" and not meta.needs_judgment:
        return f"Remove {count} {display} issues"

    return f"Fix {count} {display} issues"


def _subtype_has_fixer(meta: DetectorMeta, subtype: str | None) -> str | None:
    """Check if a subtype maps to a specific fixer."""
    if not meta.fixers or not subtype:
        return None
    # Convention: fixer name is subtype with _ replaced by -
    fixer_name = subtype.replace("_", "-")
    if fixer_name in meta.fixers:
        return fixer_name
    # Also check if subtype is a substring (e.g. "unused" matches "unused-imports")
    for fixer in meta.fixers:
        if subtype in fixer:
            return fixer
    return None


def _strip_guidance_examples(guidance: str) -> str:
    """Strip subtype-specific examples from guidance text.

    Many guidance strings have format "verb — specific examples".
    Strip after the dash to get the core action:
      "fix code smells — dead useEffect, empty if chains" → "fix code smells"
    """
    if " — " in guidance:
        return guidance.split(" — ", 1)[0].strip()
    return guidance


_ACTION_TYPE_TEMPLATES: dict[str, str] = {
    "reorganize": "reorganize with desloppify move",
    "refactor": "review and refactor each issue",
    "manual_fix": "review and fix each issue",
}


def _generate_action(
    meta: DetectorMeta | None,
    subtype: str | None,
) -> str:
    """Generate an action string from detector metadata.

    Always returns a non-empty string — every cluster gets an action.
    """
    if meta is None:
        return "review and fix each issue"

    # For detectors with subtypes, only suggest a fixer if the subtype matches
    if subtype and meta.fixers:
        matched_fixer = _subtype_has_fixer(meta, subtype)
        if matched_fixer:
            return f"desloppify autofix {matched_fixer} --dry-run"
    elif meta.action_type == "auto_fix" and meta.fixers and not meta.needs_judgment:
        # Pure auto-fix detector, no subtypes
        return f"desloppify autofix {meta.fixers[0]} --dry-run"

    if meta.tool == "move":
        return "desloppify move"

    # Guidance available — use it (strip examples for subtyped detectors)
    if meta.guidance:
        if subtype:
            return _strip_guidance_examples(meta.guidance)
        return meta.guidance

    # Final fallback: action_type template
    return _ACTION_TYPE_TEMPLATES.get(
        meta.action_type, "review and fix each issue"
    )


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------

def _repair_ghost_cluster_refs(plan: PlanModel, now: str) -> int:
    """Clear override cluster refs that point to non-existent clusters."""
    clusters = plan.get("clusters", {})
    overrides = plan.get("overrides", {})
    repaired = 0
    for override in overrides.values():
        cluster_name = override.get("cluster")
        if cluster_name and cluster_name not in clusters:
            override["cluster"] = None
            override["updated_at"] = now
            repaired += 1
    return repaired


# ---------------------------------------------------------------------------
# Shared create-or-update helper
# ---------------------------------------------------------------------------

def _sync_auto_cluster(
    plan: PlanModel,
    clusters: dict,
    existing_by_key: dict[str, str],
    *,
    cluster_key: str,
    cluster_name: str,
    member_ids: list[str],
    description: str,
    action: str,
    now: str,
    optional: bool = False,
) -> int:
    """Create or update an auto-cluster and sync its override entries.

    Handles the common pattern: check if cluster exists by key, update
    membership/metadata if changed, or create a new cluster.  Always syncs
    override entries for all *member_ids*.

    Returns 1 if a change was made, 0 otherwise.
    """
    changes = 0
    existing_name = existing_by_key.get(cluster_key)
    if existing_name and existing_name in clusters:
        cluster = clusters[existing_name]
        old_ids = set(cluster.get("issue_ids", []))
        new_ids_set = set(member_ids)
        if old_ids != new_ids_set or cluster.get("description") != description or cluster.get("action") != action:
            cluster["issue_ids"] = list(member_ids)
            cluster["description"] = description
            cluster["action"] = action
            cluster["updated_at"] = now
            changes = 1
    else:
        new_cluster: Cluster = {
            "name": cluster_name,
            "description": description,
            "issue_ids": list(member_ids),
            "created_at": now,
            "updated_at": now,
            "auto": True,
            "cluster_key": cluster_key,
            "action": action,
            "user_modified": False,
        }
        if optional:
            new_cluster["optional"] = True
        clusters[cluster_name] = new_cluster
        existing_by_key[cluster_key] = cluster_name
        changes = 1

    # Sync overrides
    overrides = plan.get("overrides", {})
    current_name = existing_by_key.get(cluster_key, cluster_name)
    for fid in member_ids:
        if fid not in overrides:
            overrides[fid] = {"issue_id": fid, "created_at": now}
        overrides[fid]["cluster"] = current_name
        overrides[fid]["updated_at"] = now

    return changes


# ---------------------------------------------------------------------------
# Main algorithm
# ---------------------------------------------------------------------------

def _sync_issue_clusters(
    plan: PlanModel,
    issues: dict,
    clusters: dict,
    existing_by_key: dict[str, str],
    active_auto_keys: set[str],
    now: str,
) -> int:
    """Group open issues by detector/subtype and sync auto-clusters."""
    changes = 0

    # Set of issue IDs in manual (non-auto) clusters
    manual_member_ids: set[str] = set()
    for cluster in clusters.values():
        if not cluster.get("auto"):
            manual_member_ids.update(cluster.get("issue_ids", []))

    # Collect open, non-suppressed issues and group by key
    groups: dict[str, list[str]] = defaultdict(list)
    issue_data: dict[str, dict] = {}
    for fid, issue in issues.items():
        if issue.get("status") != "open":
            continue
        if issue.get("suppressed"):
            continue
        if fid in manual_member_ids:
            continue

        detector = issue.get("detector", "")
        meta = DETECTORS.get(detector)
        key = _grouping_key(issue, meta)
        if key is None:
            continue

        groups[key].append(fid)
        issue_data[fid] = issue

    # Drop singleton groups
    groups = {k: v for k, v in groups.items() if len(v) >= _MIN_CLUSTER_SIZE}

    for key, member_ids in groups.items():
        active_auto_keys.add(key)
        cluster_name = _cluster_name_from_key(key)

        # Representative issue for metadata
        rep = issue_data.get(member_ids[0], {})
        detector = rep.get("detector", "")
        meta = DETECTORS.get(detector)
        members = [issue_data[fid] for fid in member_ids if fid in issue_data]

        # Extract subtype from grouping key (typed::detector::subtype)
        key_parts = key.split("::")
        subtype = key_parts[2] if len(key_parts) >= 3 else None

        description = _generate_description(cluster_name, members, meta, subtype)
        action = _generate_action(meta, subtype)

        # User-modified clusters: merge new members only, keep user edits
        existing_name = existing_by_key.get(key)
        if existing_name and existing_name in clusters:
            cluster = clusters[existing_name]
            if cluster.get("user_modified"):
                existing_ids = set(cluster.get("issue_ids", []))
                new_ids = [fid for fid in member_ids if fid not in existing_ids]
                if new_ids:
                    cluster["issue_ids"].extend(new_ids)
                    cluster["updated_at"] = now
                    changes += 1
                # Still sync overrides for all members
                overrides = plan.get("overrides", {})
                for fid in member_ids:
                    if fid not in overrides:
                        overrides[fid] = {"issue_id": fid, "created_at": now}
                    overrides[fid]["cluster"] = existing_name
                    overrides[fid]["updated_at"] = now
                continue

        # Handle name collision (existing auto-cluster with different key)
        if cluster_name in clusters and clusters[cluster_name].get("cluster_key") != key:
            cluster_name = f"{cluster_name}-{len(member_ids)}"

        changes += _sync_auto_cluster(
            plan, clusters, existing_by_key,
            cluster_key=key,
            cluster_name=cluster_name,
            member_ids=member_ids,
            description=description,
            action=action,
            now=now,
        )

    return changes


def _sync_subjective_clusters(
    plan: PlanModel,
    state: StateModel,
    issues: dict,
    clusters: dict,
    existing_by_key: dict[str, str],
    active_auto_keys: set[str],
    now: str,
    *,
    target_strict: float,
    policy: SubjectiveVisibility | None = None,
    cycle_just_completed: bool = False,
) -> int:
    """Sync unscored, stale, and under-target subjective dimension clusters."""
    changes = 0

    all_subjective_ids = sorted(
        fid for fid in plan.get("queue_order", [])
        if fid.startswith(SUBJECTIVE_PREFIX)
    )

    if policy is not None:
        unscored_state_ids = policy.unscored_ids
        stale_state_ids = policy.stale_ids
    else:
        unscored_state_ids = current_unscored_ids(state)
        stale_state_ids = _current_stale_ids(state)

    unscored_queue_ids = sorted(
        fid for fid in all_subjective_ids if fid in unscored_state_ids
    )
    stale_queue_ids = sorted(
        fid for fid in all_subjective_ids
        if fid in stale_state_ids and fid not in unscored_state_ids
    )

    # -- Initial review cluster (unscored, min size 1) ---------------------
    if len(unscored_queue_ids) >= _MIN_UNSCORED_CLUSTER_SIZE:
        active_auto_keys.add(_UNSCORED_KEY)
        cli_keys = [fid.removeprefix(SUBJECTIVE_PREFIX) for fid in unscored_queue_ids]
        description = f"Initial review of {len(unscored_queue_ids)} unscored subjective dimensions"
        action = f"desloppify review --prepare --dimensions {','.join(cli_keys)}"
        changes += _sync_auto_cluster(
            plan, clusters, existing_by_key,
            cluster_key=_UNSCORED_KEY,
            cluster_name=_UNSCORED_NAME,
            member_ids=unscored_queue_ids,
            description=description,
            action=action,
            now=now,
        )

    # -- Stale review cluster (previously scored, min size 2) --------------
    if len(stale_queue_ids) >= _MIN_CLUSTER_SIZE:
        active_auto_keys.add(_STALE_KEY)
        cli_keys = [fid.removeprefix(SUBJECTIVE_PREFIX) for fid in stale_queue_ids]
        description = f"Re-review {len(stale_queue_ids)} stale subjective dimensions"
        action = (
            "desloppify review --prepare --dimensions "
            + ",".join(cli_keys)
        )
        changes += _sync_auto_cluster(
            plan, clusters, existing_by_key,
            cluster_key=_STALE_KEY,
            cluster_name=_STALE_NAME,
            member_ids=stale_queue_ids,
            description=description,
            action=action,
            now=now,
        )

    # -- Under-target review cluster (optional, current but below target) ----
    if policy is not None:
        under_target_ids = policy.under_target_ids
    else:
        under_target_ids = current_under_target_ids(state, target_strict=target_strict)
    under_target_queue_ids = sorted(under_target_ids)

    # Prune: remove IDs that were previously in the under-target cluster
    # but are no longer under target (they've improved above threshold).
    prev_ut_cluster = clusters.get(_UNDER_TARGET_NAME, {})
    prev_ut_ids = set(prev_ut_cluster.get("issue_ids", []))
    order = plan.get("queue_order", [])
    _ut_prune = [
        fid for fid in prev_ut_ids
        if fid not in under_target_ids
        and fid not in stale_state_ids
        and fid not in unscored_state_ids
        and fid in order
    ]
    for fid in _ut_prune:
        order.remove(fid)
        changes += 1

    # Guard: only inject under-target items when no objective issues
    # remain open — mirror the guard used by sync_stale_dimensions().
    if policy is not None:
        has_objective_items = policy.has_objective_backlog
    else:
        has_objective_items = any(
            f.get("status") == "open"
            and f.get("detector") not in NON_OBJECTIVE_DETECTORS
            and not f.get("suppressed")
            for f in issues.values()
        )

    if not has_objective_items and len(under_target_queue_ids) >= _MIN_CLUSTER_SIZE:
        active_auto_keys.add(_UNDER_TARGET_KEY)
        cli_keys = [fid.removeprefix(SUBJECTIVE_PREFIX) for fid in under_target_queue_ids]
        description = (
            f"Consider re-reviewing {len(under_target_queue_ids)} "
            f"dimensions under target score"
        )
        action = (
            "desloppify review --prepare --dimensions "
            + ",".join(cli_keys)
        )
        changes += _sync_auto_cluster(
            plan, clusters, existing_by_key,
            cluster_key=_UNDER_TARGET_KEY,
            cluster_name=_UNDER_TARGET_NAME,
            member_ids=under_target_queue_ids,
            description=description,
            action=action,
            now=now,
            optional=True,
        )

        # Ensure under-target IDs are in queue_order (at the back)
        order = plan.get("queue_order", [])
        existing_order = set(order)
        for fid in under_target_queue_ids:
            if fid not in existing_order:
                order.append(fid)

    # Evict under-target IDs from queue when objective backlog has returned
    # — but NOT after a completed cycle, where they should stay for review.
    if has_objective_items and not cycle_just_completed:
        _objective_evict = [
            fid for fid in order
            if fid in under_target_ids
        ]
        for fid in _objective_evict:
            order.remove(fid)
            changes += 1

    return changes


def _prune_stale_clusters(
    plan: PlanModel,
    issues: dict,
    clusters: dict,
    active_auto_keys: set[str],
    now: str,
) -> int:
    """Delete auto-clusters that no longer have matching groups."""
    changes = 0
    for name in list(clusters.keys()):
        cluster = clusters[name]
        if not cluster.get("auto"):
            continue
        ck = cluster.get("cluster_key", "")
        if ck in active_auto_keys:
            continue
        if cluster.get("user_modified"):
            # Keep user-modified clusters but prune dead member IDs
            alive = [fid for fid in cluster.get("issue_ids", [])
                     if fid in issues and issues[fid].get("status") == "open"]
            if alive:
                if len(alive) != len(cluster.get("issue_ids", [])):
                    cluster["issue_ids"] = alive
                    cluster["updated_at"] = now
                    changes += 1
                continue
            # All members gone — delete even if user_modified
        # Delete stale cluster
        del clusters[name]
        # Clear cluster refs from overrides
        for fid in cluster.get("issue_ids", []):
            override = plan.get("overrides", {}).get(fid)
            if override and override.get("cluster") == name:
                override["cluster"] = None
                override["updated_at"] = now
        if plan.get("active_cluster") == name:
            plan["active_cluster"] = None
        changes += 1
    return changes


def auto_cluster_issues(
    plan: PlanModel,
    state: StateModel,
    *,
    target_strict: float = 95.0,
    policy: SubjectiveVisibility | None = None,
    cycle_just_completed: bool = False,
) -> int:
    """Regenerate auto-clusters from current open issues.

    Returns count of changes made (clusters created, updated, or deleted).
    """
    ensure_plan_defaults(plan)

    issues = state.get("issues", {})
    clusters = plan.get("clusters", {})

    # Map existing auto-clusters by cluster_key
    existing_by_key: dict[str, str] = {}  # cluster_key → cluster_name
    for name, cluster in list(clusters.items()):
        if cluster.get("auto"):
            ck = cluster.get("cluster_key", "")
            if ck:
                existing_by_key[ck] = name

    now = utc_now()
    active_auto_keys: set[str] = set()
    changes = 0

    changes += _sync_issue_clusters(
        plan, issues, clusters, existing_by_key, active_auto_keys, now,
    )
    changes += _sync_subjective_clusters(
        plan, state, issues, clusters, existing_by_key, active_auto_keys, now,
        target_strict=target_strict,
        policy=policy,
        cycle_just_completed=cycle_just_completed,
    )
    changes += _prune_stale_clusters(
        plan, issues, clusters, active_auto_keys, now,
    )
    changes += _repair_ghost_cluster_refs(plan, now)

    plan["updated"] = now
    return changes


__all__ = [
    "AUTO_PREFIX",
    "auto_cluster_issues",
]
