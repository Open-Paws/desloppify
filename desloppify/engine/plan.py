"""Public plan API facade.

Plan internals live in ``desloppify.engine._plan``; this module exposes
the stable, non-private API used by commands and rendering helpers.
"""

from __future__ import annotations

# --- schema -----------------------------------------------------------------
from desloppify.engine._plan.schema import (
    EPIC_PREFIX,
    ExecutionLogEntry,
    PLAN_VERSION,
    Cluster,
    CommitRecord,
    ItemOverride,
    PlanModel,
    SkipEntry,
    SupersededEntry,
    VALID_EPIC_DIRECTIONS,
    VALID_SKIP_KINDS,
    empty_plan,
    ensure_plan_defaults,
    triage_clusters,
    validate_plan,
)

# --- persistence ------------------------------------------------------------
from desloppify.engine._plan.persistence import (
    PLAN_FILE,
    has_living_plan,
    load_plan,
    plan_path_for_state,
    save_plan,
)

# --- operations -------------------------------------------------------------
from desloppify.engine._plan.operations import (
    add_to_cluster,
    annotate_issue,
    append_log_entry,
    clear_focus,
    create_cluster,
    delete_cluster,
    describe_issue,
    merge_clusters,
    move_cluster,
    move_items,
    purge_ids,
    remove_from_cluster,
    reset_plan,
    resurface_stale_skips,
    set_focus,
    skip_items,
    unskip_items,
)

# --- reconcile --------------------------------------------------------------
from desloppify.engine._plan.reconcile import (
    ReconcileResult,
    ReviewImportSyncResult,
    reconcile_plan_after_scan,
    sync_plan_after_review_import,
)

# --- auto-clustering --------------------------------------------------------
from desloppify.engine._plan.auto_cluster import (
    AUTO_PREFIX,
    auto_cluster_issues,
)

# --- commit tracking --------------------------------------------------------
from desloppify.engine._plan.commit_tracking import (
    add_uncommitted_issues,
    commit_tracking_summary,
    filter_issue_ids_by_pattern,
    find_commit_for_issue,
    generate_pr_body,
    get_uncommitted_issues,
    purge_uncommitted_ids,
    record_commit,
    suggest_commit_message,
)

# --- stale dimensions -------------------------------------------------------
from desloppify.engine._plan.stale_dimensions import (
    TRIAGE_ID,
    TRIAGE_IDS,
    TRIAGE_PREFIX,
    TRIAGE_STAGE_IDS,
    SYNTHETIC_PREFIXES,
    WORKFLOW_CREATE_PLAN_ID,
    WORKFLOW_PREFIX,
    CommunicateScoreSyncResult,
    StaleDimensionSyncResult,
    UnscoredDimensionSyncResult,
    TriageSyncResult,
    compute_new_issue_ids,
    current_unscored_ids,
    is_triage_stale,
    review_issue_snapshot_hash,
    sync_communicate_score_needed,
    sync_create_plan_needed,
    sync_score_checkpoint_needed,
    sync_stale_dimensions,
    sync_triage_needed,
    sync_unscored_dimensions,
)

# --- epic triage ------------------------------------------------------------
from desloppify.engine._plan.epic_triage import (
    build_triage_prompt,
    collect_triage_input,
    detect_recurring_patterns,
    extract_issue_citations,
)

# --- subjective policy ------------------------------------------------------
from desloppify.engine._plan.subjective_policy import (
    compute_subjective_visibility,
)

def triage_phase_banner(plan: PlanModel) -> str:
    """Return a banner string when triage stage IDs are in the queue."""
    ensure_plan_defaults(plan)
    order = set(plan.get("queue_order", []))
    has_triage = any(sid in order for sid in TRIAGE_IDS)
    if not has_triage:
        return ""
    meta = plan.get("epic_triage_meta", {})
    stages = meta.get("triage_stages", {})
    completed = [s for s in ("observe", "reflect", "organize") if s in stages]
    if completed:
        return (
            f"TRIAGE MODE ({len(completed)}/4 stages complete) — "
            "complete all stages to exit. Run: desloppify plan triage"
        )
    return (
        "TRIAGE MODE — review issues need analysis before fixing. "
        "Run: desloppify plan triage"
    )


__all__ = [
    # schema
    "EPIC_PREFIX",
    "ExecutionLogEntry",
    "PLAN_VERSION",
    "Cluster",
    "CommitRecord",
    "ItemOverride",
    "PlanModel",
    "SkipEntry",
    "SupersededEntry",
    "VALID_EPIC_DIRECTIONS",
    "VALID_SKIP_KINDS",
    "empty_plan",
    "ensure_plan_defaults",
    "triage_clusters",
    "validate_plan",
    # persistence
    "PLAN_FILE",
    "has_living_plan",
    "load_plan",
    "plan_path_for_state",
    "save_plan",
    # operations
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
    # reconcile
    "ReconcileResult",
    "ReviewImportSyncResult",
    "reconcile_plan_after_scan",
    "sync_plan_after_review_import",
    # commit tracking
    "add_uncommitted_issues",
    "commit_tracking_summary",
    "filter_issue_ids_by_pattern",
    "find_commit_for_issue",
    "generate_pr_body",
    "get_uncommitted_issues",
    "purge_uncommitted_ids",
    "record_commit",
    "suggest_commit_message",
    # auto-clustering
    "AUTO_PREFIX",
    "auto_cluster_issues",
    # stale dimensions
    "TRIAGE_ID",
    "TRIAGE_IDS",
    "TRIAGE_PREFIX",
    "TRIAGE_STAGE_IDS",
    "SYNTHETIC_PREFIXES",
    "WORKFLOW_CREATE_PLAN_ID",
    "WORKFLOW_PREFIX",
    "CommunicateScoreSyncResult",
    "StaleDimensionSyncResult",
    "TriageSyncResult",
    "UnscoredDimensionSyncResult",
    "compute_new_issue_ids",
    "current_unscored_ids",
    "is_triage_stale",
    "review_issue_snapshot_hash",
    "sync_communicate_score_needed",
    "sync_create_plan_needed",
    "sync_score_checkpoint_needed",
    "sync_stale_dimensions",
    "sync_triage_needed",
    "sync_unscored_dimensions",
    # epic triage
    "build_triage_prompt",
    "collect_triage_input",
    "detect_recurring_patterns",
    "extract_issue_citations",
    # subjective policy
    "compute_subjective_visibility",
    # triage
    "triage_phase_banner",
]
