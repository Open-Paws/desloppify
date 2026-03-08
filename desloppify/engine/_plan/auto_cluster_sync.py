"""Internal sync helpers for auto-cluster regeneration."""

from __future__ import annotations

from collections import defaultdict

from desloppify.base.registry import DETECTORS
from desloppify.engine._plan import stale_policy as stale_policy_mod
from desloppify.engine._plan.cluster_strategy import (
    cluster_name_from_key as _cluster_name_from_key,
)
from desloppify.engine._plan.cluster_strategy import (
    generate_action as _generate_action,
)
from desloppify.engine._plan.cluster_strategy import (
    generate_description as _generate_description,
)
from desloppify.engine._plan.cluster_strategy import (
    grouping_key as _grouping_key,
)
from desloppify.engine._plan._sync_context import (
    has_objective_backlog as _has_objective_backlog,
)
from desloppify.engine._plan.constants import SUBJECTIVE_PREFIX
from desloppify.engine._plan.subjective_policy import SubjectiveVisibility
from desloppify.engine._plan.sync_auto_prune import prune_stale_clusters
from desloppify.engine._plan.sync_dimensions import (
    current_under_target_ids,
    current_unscored_ids,
)
from desloppify.engine._state.schema import StateModel

_MIN_CLUSTER_SIZE = 2
_STALE_KEY = "subjective::stale"
_STALE_NAME = "auto/stale-review"
_UNSCORED_KEY = "subjective::unscored"
_UNSCORED_NAME = "auto/initial-review"
_UNDER_TARGET_KEY = "subjective::under-target"
_UNDER_TARGET_NAME = "auto/under-target-review"
_MIN_UNSCORED_CLUSTER_SIZE = 1


def _manual_member_ids(clusters: dict) -> set[str]:
    """Collect all issue IDs belonging to manual (non-auto) clusters."""
    ids: set[str] = set()
    for cluster in clusters.values():
        if not cluster.get("auto"):
            ids.update(cluster.get("issue_ids", []))
    return ids


def _group_clusterable_issues(
    issues: dict,
    *,
    manual_member_ids: set[str],
) -> tuple[dict[str, list[str]], dict[str, dict]]:
    """Group open, non-suppressed, non-manual issues by detector/subtype key.

    Returns (groups_by_key, issue_data) where groups_by_key maps grouping keys
    to lists of issue IDs, filtered to clusters >= _MIN_CLUSTER_SIZE.
    """
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

    groups = {k: v for k, v in groups.items() if len(v) >= _MIN_CLUSTER_SIZE}
    return groups, issue_data


def _sync_user_modified_cluster_members(
    plan: dict,
    *,
    clusters: dict,
    existing_name: str,
    member_ids: list[str],
    now: str,
) -> int:
    """Sync member IDs for a user-modified cluster, returns count of changes."""
    cluster = clusters[existing_name]
    changes = 0
    existing_ids = set(cluster.get("issue_ids", []))
    new_ids = [fid for fid in member_ids if fid not in existing_ids]
    if new_ids:
        cluster["issue_ids"].extend(new_ids)
        cluster["updated_at"] = now
        changes = 1
    overrides = plan.get("overrides", {})
    for fid in member_ids:
        if fid not in overrides:
            overrides[fid] = {"issue_id": fid, "created_at": now}
        overrides[fid]["cluster"] = existing_name
        overrides[fid]["updated_at"] = now
    return changes


def _subjective_state_sets(
    state: StateModel,
    *,
    policy: SubjectiveVisibility | None,
    target_strict: float,
) -> tuple[set, set, set]:
    """Return (stale_ids, under_target_ids, unscored_ids) for subjective cluster logic."""
    if policy is not None:
        unscored_ids = policy.unscored_ids
        stale_ids = policy.stale_ids
        under_target_ids = policy.under_target_ids
    else:
        unscored_ids = current_unscored_ids(state)
        stale_ids = stale_policy_mod.current_stale_ids(state, subjective_prefix=SUBJECTIVE_PREFIX)
        under_target_ids = current_under_target_ids(state, target_strict=target_strict)
    return stale_ids, under_target_ids, unscored_ids


def _sync_auto_cluster(
    plan: dict,
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
    """Create or update an auto-cluster and sync its override entries."""
    changes = 0
    existing_name = existing_by_key.get(cluster_key)
    if existing_name and existing_name in clusters:
        cluster = clusters[existing_name]
        old_ids = set(cluster.get("issue_ids", []))
        new_ids_set = set(member_ids)
        if (
            old_ids != new_ids_set
            or cluster.get("description") != description
            or cluster.get("action") != action
        ):
            cluster["issue_ids"] = list(member_ids)
            cluster["description"] = description
            cluster["action"] = action
            cluster["updated_at"] = now
            changes = 1
    else:
        new_cluster = {
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

    overrides = plan.get("overrides", {})
    current_name = existing_by_key.get(cluster_key, cluster_name)
    for fid in member_ids:
        if fid not in overrides:
            overrides[fid] = {"issue_id": fid, "created_at": now}
        overrides[fid]["cluster"] = current_name
        overrides[fid]["updated_at"] = now

    return changes


def sync_issue_clusters(
    plan: dict,
    issues: dict,
    clusters: dict,
    existing_by_key: dict[str, str],
    active_auto_keys: set[str],
    now: str,
) -> int:
    """Group open issues by detector/subtype and sync auto-clusters."""
    changes = 0

    groups, issue_data = _group_clusterable_issues(
        issues, manual_member_ids=_manual_member_ids(clusters)
    )

    for key, member_ids in groups.items():
        active_auto_keys.add(key)
        cluster_name = _cluster_name_from_key(key)

        rep = issue_data.get(member_ids[0], {})
        detector = rep.get("detector", "")
        meta = DETECTORS.get(detector)
        members = [issue_data[fid] for fid in member_ids if fid in issue_data]

        key_parts = key.split("::")
        subtype = key_parts[2] if len(key_parts) >= 3 else None

        description = _generate_description(cluster_name, members, meta, subtype)
        action = _generate_action(meta, subtype)

        existing_name = existing_by_key.get(key)
        if existing_name and existing_name in clusters:
            cluster = clusters[existing_name]
            if cluster.get("user_modified"):
                changes += _sync_user_modified_cluster_members(
                    plan,
                    clusters=clusters,
                    existing_name=existing_name,
                    member_ids=member_ids,
                    now=now,
                )
                continue

        if cluster_name in clusters and clusters[cluster_name].get("cluster_key") != key:
            cluster_name = f"{cluster_name}-{len(member_ids)}"

        changes += _sync_auto_cluster(
            plan,
            clusters,
            existing_by_key,
            cluster_key=key,
            cluster_name=cluster_name,
            member_ids=member_ids,
            description=description,
            action=action,
            now=now,
        )

    return changes


def sync_subjective_clusters(
    plan: dict,
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

    stale_state_ids, under_target_ids, unscored_state_ids = _subjective_state_sets(
        state, policy=policy, target_strict=target_strict
    )

    unscored_queue_ids = sorted(
        fid for fid in all_subjective_ids if fid in unscored_state_ids
    )
    stale_queue_ids = sorted(
        fid for fid in all_subjective_ids
        if fid in stale_state_ids and fid not in unscored_state_ids
    )

    if len(unscored_queue_ids) >= _MIN_UNSCORED_CLUSTER_SIZE:
        active_auto_keys.add(_UNSCORED_KEY)
        cli_keys = [fid.removeprefix(SUBJECTIVE_PREFIX) for fid in unscored_queue_ids]
        description = (
            f"Initial review of {len(unscored_queue_ids)} unscored subjective dimensions"
        )
        action = f"desloppify review --prepare --dimensions {','.join(cli_keys)}"
        changes += _sync_auto_cluster(
            plan,
            clusters,
            existing_by_key,
            cluster_key=_UNSCORED_KEY,
            cluster_name=_UNSCORED_NAME,
            member_ids=unscored_queue_ids,
            description=description,
            action=action,
            now=now,
        )

    if len(stale_queue_ids) >= _MIN_CLUSTER_SIZE:
        active_auto_keys.add(_STALE_KEY)
        cli_keys = [fid.removeprefix(SUBJECTIVE_PREFIX) for fid in stale_queue_ids]
        description = f"Re-review {len(stale_queue_ids)} stale subjective dimensions"
        action = "desloppify review --prepare --dimensions " + ",".join(cli_keys)
        changes += _sync_auto_cluster(
            plan,
            clusters,
            existing_by_key,
            cluster_key=_STALE_KEY,
            cluster_name=_STALE_NAME,
            member_ids=stale_queue_ids,
            description=description,
            action=action,
            now=now,
        )

    under_target_queue_ids = sorted(under_target_ids)

    prev_ut_cluster = clusters.get(_UNDER_TARGET_NAME, {})
    prev_ut_ids = set(prev_ut_cluster.get("issue_ids", []))
    order = plan.get("queue_order", [])
    ut_prune = [
        fid for fid in prev_ut_ids
        if fid not in under_target_ids
        and fid not in stale_state_ids
        and fid not in unscored_state_ids
        and fid in order
    ]
    for fid in ut_prune:
        order.remove(fid)
        changes += 1

    has_objective_items = _has_objective_backlog(issues, policy)

    if not has_objective_items and len(under_target_queue_ids) >= _MIN_CLUSTER_SIZE:
        active_auto_keys.add(_UNDER_TARGET_KEY)
        cli_keys = [fid.removeprefix(SUBJECTIVE_PREFIX) for fid in under_target_queue_ids]
        description = (
            f"Consider re-reviewing {len(under_target_queue_ids)} "
            f"dimensions under target score"
        )
        action = "desloppify review --prepare --dimensions " + ",".join(cli_keys)
        changes += _sync_auto_cluster(
            plan,
            clusters,
            existing_by_key,
            cluster_key=_UNDER_TARGET_KEY,
            cluster_name=_UNDER_TARGET_NAME,
            member_ids=under_target_queue_ids,
            description=description,
            action=action,
            now=now,
            optional=True,
        )

        existing_order = set(order)
        for fid in under_target_queue_ids:
            if fid not in existing_order:
                order.append(fid)

    if has_objective_items and not cycle_just_completed:
        objective_evict = [
            fid for fid in order
            if fid in under_target_ids or fid in stale_state_ids
        ]
        for fid in objective_evict:
            order.remove(fid)
            changes += 1

    return changes


__all__ = ["prune_stale_clusters", "sync_issue_clusters", "sync_subjective_clusters"]
