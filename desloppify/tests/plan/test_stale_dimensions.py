"""Tests for stale and unscored subjective dimension sync in the plan."""

from __future__ import annotations

from desloppify.engine._plan.reconcile import reconcile_plan_after_scan
from desloppify.engine._plan.schema import empty_plan
from desloppify.engine._plan.sync_dimensions import (
    sync_stale_dimensions,
    sync_unscored_dimensions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plan_with_queue(*ids: str) -> dict:
    plan = empty_plan()
    plan["queue_order"] = list(ids)
    return plan


def _state_with_stale_dimensions(*dim_keys: str, score: float = 50.0) -> dict:
    """Build a minimal state with stale subjective dimensions."""
    dim_scores: dict = {}
    assessments: dict = {}
    for dim_key in dim_keys:
        dim_scores[dim_key] = {
            "score": score,
            "strict": score,
            "checks": 1,
            "failing": 0,
            "detectors": {
                "subjective_assessment": {
                    "dimension_key": dim_key,
                    "placeholder": False,
                }
            },
        }
        assessments[dim_key] = {
            "score": score,
            "needs_review_refresh": True,
            "refresh_reason": "mechanical_issues_changed",
            "stale_since": "2025-01-01T00:00:00+00:00",
        }
    return {
        "issues": {},
        "scan_count": 5,
        "dimension_scores": dim_scores,
        "subjective_assessments": assessments,
    }


def _state_with_unscored_dimensions(*dim_keys: str) -> dict:
    """Build a minimal state with unscored (placeholder) subjective dimensions."""
    dim_scores: dict = {}
    assessments: dict = {}
    for dim_key in dim_keys:
        dim_scores[dim_key] = {
            "score": 0,
            "strict": 0,
            "checks": 1,
            "failing": 0,
            "detectors": {
                "subjective_assessment": {
                    "dimension_key": dim_key,
                    "placeholder": True,
                }
            },
        }
        assessments[dim_key] = {
            "score": 0.0,
            "source": "scan_reset_subjective",
            "placeholder": True,
        }
    return {
        "issues": {},
        "scan_count": 1,
        "dimension_scores": dim_scores,
        "subjective_assessments": assessments,
    }


def _state_with_mixed_dimensions(
    unscored: list[str],
    stale: list[str],
) -> dict:
    """Build a state with both unscored and stale dimensions."""
    state = _state_with_unscored_dimensions(*unscored)
    stale_state = _state_with_stale_dimensions(*stale)
    state["dimension_scores"].update(stale_state["dimension_scores"])
    state["subjective_assessments"].update(stale_state["subjective_assessments"])
    return state


# ---------------------------------------------------------------------------
# Unscored dimension sync
# ---------------------------------------------------------------------------

def test_unscored_injected_at_back():
    """Unscored IDs are appended after existing items."""
    plan = _plan_with_queue("some_issue::file.py::abc123")
    state = _state_with_unscored_dimensions("design_coherence", "error_consistency")

    result = sync_unscored_dimensions(plan, state)
    assert len(result.injected) == 2
    # Existing item keeps its position; unscored dims appended at back
    assert plan["queue_order"][0] == "some_issue::file.py::abc123"
    assert plan["queue_order"][1].startswith("subjective::")
    assert plan["queue_order"][2].startswith("subjective::")


def test_unscored_injection_unconditional():
    """Unscored dims inject even when objective items exist in queue."""
    plan = _plan_with_queue(
        "some_issue::file.py::abc123",
        "another::file.py::def456",
    )
    state = _state_with_unscored_dimensions("design_coherence")

    result = sync_unscored_dimensions(plan, state)
    assert len(result.injected) == 1
    assert plan["queue_order"][-1] == "subjective::design_coherence"
    assert len(plan["queue_order"]) == 3  # 2 existing + 1 unscored


def test_unscored_pruned_after_review():
    """Once a dimension is scored, it is removed from the queue."""
    plan = _plan_with_queue(
        "subjective::design_coherence",
        "subjective::error_consistency",
        "some_issue::file.py::abc123",
    )
    # Only error_consistency is still unscored; design_coherence was scored
    state = _state_with_unscored_dimensions("error_consistency")

    result = sync_unscored_dimensions(plan, state)
    assert "subjective::design_coherence" in result.pruned
    assert "subjective::error_consistency" in plan["queue_order"]
    assert "subjective::design_coherence" not in plan["queue_order"]


def test_stale_sync_does_not_prune_unscored_ids():
    """Stale sync must not remove IDs that are still unscored."""
    plan = _plan_with_queue(
        "subjective::design_coherence",  # unscored
        "subjective::error_consistency",  # stale
    )
    state = _state_with_mixed_dimensions(
        unscored=["design_coherence"],
        stale=["error_consistency"],
    )

    result = sync_stale_dimensions(plan, state)
    # design_coherence is unscored (not stale), but stale sync should NOT prune it
    assert "subjective::design_coherence" not in result.pruned
    assert "subjective::design_coherence" in plan["queue_order"]
    assert "subjective::error_consistency" in plan["queue_order"]


def test_unscored_sync_does_not_prune_stale_ids():
    """Unscored sync must not remove IDs that are stale."""
    plan = _plan_with_queue(
        "subjective::design_coherence",  # unscored
        "subjective::error_consistency",  # stale
    )
    state = _state_with_mixed_dimensions(
        unscored=["design_coherence"],
        stale=["error_consistency"],
    )

    result = sync_unscored_dimensions(plan, state)
    assert "subjective::error_consistency" not in result.pruned
    assert "subjective::error_consistency" in plan["queue_order"]


def test_unscored_no_injection_when_no_dimension_scores():
    plan = _plan_with_queue()
    state = {"issues": {}, "scan_count": 1}

    result = sync_unscored_dimensions(plan, state)
    assert result.injected == []
    assert result.pruned == []


def test_unscored_no_duplicates():
    """Already-present unscored IDs are not duplicated."""
    plan = _plan_with_queue("subjective::design_coherence")
    state = _state_with_unscored_dimensions("design_coherence")

    result = sync_unscored_dimensions(plan, state)
    assert result.injected == []
    assert plan["queue_order"].count("subjective::design_coherence") == 1


# ---------------------------------------------------------------------------
# Injection: empty queue + stale dimensions
# ---------------------------------------------------------------------------

def test_injects_when_queue_empty():
    plan = _plan_with_queue()
    state = _state_with_stale_dimensions("design_coherence", "error_consistency")

    result = sync_stale_dimensions(plan, state)
    assert len(result.injected) == 2
    assert "subjective::design_coherence" in plan["queue_order"]
    assert "subjective::error_consistency" in plan["queue_order"]
    assert result.changes == 2


def test_no_injection_when_queue_has_real_items():
    plan = _plan_with_queue("some_issue::file.py::abc123")
    state = _state_with_stale_dimensions("design_coherence")
    # Add an actual open objective issue to state (source of truth)
    state["issues"]["some_issue::file.py::abc123"] = {
        "id": "some_issue::file.py::abc123",
        "status": "open",
        "detector": "smells",
    }

    result = sync_stale_dimensions(plan, state)
    assert result.injected == []
    assert "subjective::design_coherence" not in plan["queue_order"]


def test_stale_ids_evicted_when_objective_backlog_exists():
    """Stale IDs should be removed from queue_order when objective work exists."""
    plan = _plan_with_queue(
        "subjective::design_coherence",
        "subjective::error_consistency",
        "some_issue::file.py::abc123",
    )
    state = _state_with_stale_dimensions("design_coherence", "error_consistency")
    state["issues"]["some_issue::file.py::abc123"] = {
        "id": "some_issue::file.py::abc123",
        "status": "open",
        "detector": "smells",
    }

    result = sync_stale_dimensions(plan, state)
    # Stale IDs are evicted while objective backlog exists
    assert "subjective::design_coherence" in result.pruned
    assert "subjective::error_consistency" in result.pruned
    assert "subjective::design_coherence" not in plan["queue_order"]
    assert "subjective::error_consistency" not in plan["queue_order"]
    # No new injection either (objective backlog blocks new injections)
    assert result.injected == []


def test_stale_ids_inject_when_backlog_clears():
    """Stale IDs inject when objective backlog clears."""
    plan = _plan_with_queue("some_issue::file.py::abc123")
    state = _state_with_stale_dimensions("design_coherence")
    state["issues"]["some_issue::file.py::abc123"] = {
        "id": "some_issue::file.py::abc123",
        "status": "open",
        "detector": "smells",
    }

    # Mid-cycle: no injection
    r1 = sync_stale_dimensions(plan, state)
    assert r1.injected == []

    # Objective backlog clears
    state["issues"]["some_issue::file.py::abc123"]["status"] = "done"

    r2 = sync_stale_dimensions(plan, state)
    assert "subjective::design_coherence" in r2.injected
    assert "subjective::design_coherence" in plan["queue_order"]


def test_no_injection_when_no_stale_or_under_target_dimensions():
    plan = _plan_with_queue()
    state = _state_with_stale_dimensions("design_coherence", score=100.0)
    state["subjective_assessments"]["design_coherence"]["needs_review_refresh"] = False

    result = sync_stale_dimensions(plan, state)
    assert result.injected == []
    assert plan["queue_order"] == []


def test_no_injection_when_no_dimension_scores():
    plan = _plan_with_queue()
    state = {"issues": {}, "scan_count": 5}

    result = sync_stale_dimensions(plan, state)
    assert result.injected == []
    assert result.pruned == []


# ---------------------------------------------------------------------------
# Cleanup: prune resolved stale IDs
# ---------------------------------------------------------------------------

def test_prunes_resolved_dimension_ids():
    plan = _plan_with_queue(
        "subjective::design_coherence",
        "subjective::error_consistency",
    )
    # Only design_coherence is still stale; error_consistency was refreshed
    state = _state_with_stale_dimensions("design_coherence")

    result = sync_stale_dimensions(plan, state)
    assert result.pruned == ["subjective::error_consistency"]
    assert plan["queue_order"] == ["subjective::design_coherence"]


def test_prune_does_not_touch_real_issue_ids():
    plan = _plan_with_queue(
        "structural::file.py::abc123",
        "subjective::design_coherence",
    )
    # design_coherence is no longer stale
    state = {"issues": {}, "scan_count": 5, "dimension_scores": {}}

    result = sync_stale_dimensions(plan, state)
    assert "subjective::design_coherence" in result.pruned
    assert plan["queue_order"] == ["structural::file.py::abc123"]


# ---------------------------------------------------------------------------
# Full lifecycle: inject → refresh → prune → re-inject
# ---------------------------------------------------------------------------

def test_full_lifecycle():
    plan = _plan_with_queue()
    state = _state_with_stale_dimensions("design_coherence", "error_consistency")

    # 1. Empty queue, stale dims → inject both
    r1 = sync_stale_dimensions(plan, state)
    assert len(r1.injected) == 2
    assert plan["queue_order"] == [
        "subjective::design_coherence",
        "subjective::error_consistency",
    ]

    # 2. User refreshes design_coherence (no longer stale, but still under target)
    state["subjective_assessments"]["design_coherence"]["needs_review_refresh"] = False

    r2 = sync_stale_dimensions(plan, state)
    # Not pruned: still under target (score=50)
    assert r2.pruned == []
    assert "subjective::design_coherence" in plan["queue_order"]
    assert "subjective::error_consistency" in plan["queue_order"]

    # 3. User raises both scores above target → queue empties
    state["subjective_assessments"]["error_consistency"]["needs_review_refresh"] = False
    for key in ("design_coherence", "error_consistency"):
        state["dimension_scores"][key]["score"] = 100.0
        state["dimension_scores"][key]["strict"] = 100.0
        state["subjective_assessments"][key]["score"] = 100.0

    r3 = sync_stale_dimensions(plan, state)
    assert len(r3.pruned) == 2
    assert plan["queue_order"] == []
    assert r3.injected == []

    # 4. New mechanical change makes design_coherence stale again
    state["dimension_scores"]["design_coherence"]["score"] = 50.0
    state["dimension_scores"]["design_coherence"]["strict"] = 50.0
    state["subjective_assessments"]["design_coherence"]["score"] = 50.0
    state["subjective_assessments"]["design_coherence"]["needs_review_refresh"] = True

    r4 = sync_stale_dimensions(plan, state)
    assert r4.injected == ["subjective::design_coherence"]
    assert plan["queue_order"] == ["subjective::design_coherence"]


# ---------------------------------------------------------------------------
# Reconcile must not supersede synthetic IDs
# ---------------------------------------------------------------------------

def test_reconcile_ignores_synthetic_ids():
    """Reconciliation must not treat subjective::* IDs as dead issues."""
    plan = _plan_with_queue("subjective::design_coherence")
    state = _state_with_stale_dimensions("design_coherence")

    result = reconcile_plan_after_scan(plan, state)
    assert result.superseded == []
    assert "subjective::design_coherence" in plan["queue_order"]
    assert "subjective::design_coherence" not in plan.get("superseded", {})


# ---------------------------------------------------------------------------
# Injection: only subjective items in queue (relaxed condition)
# ---------------------------------------------------------------------------

def test_injection_when_only_subjective_in_queue():
    """New stale dims are injected when only subjective IDs remain in queue."""
    plan = _plan_with_queue("subjective::design_coherence")
    state = _state_with_stale_dimensions("design_coherence", "error_consistency")

    result = sync_stale_dimensions(plan, state)
    assert "subjective::error_consistency" in result.injected
    assert "subjective::design_coherence" not in result.injected  # already there
    assert set(plan["queue_order"]) == {
        "subjective::design_coherence",
        "subjective::error_consistency",
    }


# ---------------------------------------------------------------------------
# Auto-clustering of stale subjective dimensions
# ---------------------------------------------------------------------------

def test_stale_cluster_created():
    """When >=2 stale dims exist, auto_cluster_issues creates a cluster."""
    from desloppify.engine._plan.auto_cluster import auto_cluster_issues

    plan = _plan_with_queue(
        "subjective::design_coherence",
        "subjective::error_consistency",
    )
    state = _state_with_stale_dimensions("design_coherence", "error_consistency")

    changes = auto_cluster_issues(plan, state)
    assert changes >= 1
    assert "auto/stale-review" in plan["clusters"]

    cluster = plan["clusters"]["auto/stale-review"]
    assert cluster["auto"] is True
    assert cluster["cluster_key"] == "subjective::stale"
    assert set(cluster["issue_ids"]) == {
        "subjective::design_coherence",
        "subjective::error_consistency",
    }
    assert "Re-review 2 stale" in cluster["description"]
    assert "desloppify review --prepare --dimensions" in cluster["action"]
    assert "design_coherence" in cluster["action"]
    assert "error_consistency" in cluster["action"]
    assert "--force-review-rerun" not in cluster["action"]


def test_stale_cluster_deleted_when_fresh():
    """When all dims are refreshed, the stale cluster is deleted."""
    from desloppify.engine._plan.auto_cluster import auto_cluster_issues

    plan = _plan_with_queue(
        "subjective::design_coherence",
        "subjective::error_consistency",
    )
    state = _state_with_stale_dimensions("design_coherence", "error_consistency")

    # Create the cluster
    auto_cluster_issues(plan, state)
    assert "auto/stale-review" in plan["clusters"]

    # Now remove subjective IDs from queue (simulating refresh + prune)
    plan["queue_order"] = []

    auto_cluster_issues(plan, state)
    assert "auto/stale-review" not in plan["clusters"]


def test_stale_cluster_updated():
    """When the stale set changes, the cluster membership updates."""
    from desloppify.engine._plan.auto_cluster import auto_cluster_issues

    plan = _plan_with_queue(
        "subjective::design_coherence",
        "subjective::error_consistency",
    )
    state = _state_with_stale_dimensions("design_coherence", "error_consistency")

    auto_cluster_issues(plan, state)
    assert set(plan["clusters"]["auto/stale-review"]["issue_ids"]) == {
        "subjective::design_coherence",
        "subjective::error_consistency",
    }

    # A third dimension becomes stale — must also appear in state
    plan["queue_order"].append("subjective::convention_drift")
    state2 = _state_with_stale_dimensions(
        "design_coherence", "error_consistency", "convention_drift",
    )
    changes = auto_cluster_issues(plan, state2)
    assert changes >= 1
    assert "subjective::convention_drift" in plan["clusters"]["auto/stale-review"]["issue_ids"]
    assert "Re-review 3 stale" in plan["clusters"]["auto/stale-review"]["description"]


def test_single_stale_dim_no_cluster():
    """Only 1 stale dim → no cluster created (below _MIN_CLUSTER_SIZE)."""
    from desloppify.engine._plan.auto_cluster import auto_cluster_issues

    plan = _plan_with_queue("subjective::design_coherence")
    state = _state_with_stale_dimensions("design_coherence")

    auto_cluster_issues(plan, state)
    assert "auto/stale-review" not in plan["clusters"]


# ---------------------------------------------------------------------------
# Promoted items: system insertions go after user-moved items
# ---------------------------------------------------------------------------

def test_unscored_appends_after_existing():
    """Unscored dims append to back, never reorder existing items."""
    plan = _plan_with_queue("issue_a", "issue_b")
    plan["promoted_ids"] = ["issue_a"]
    state = _state_with_unscored_dimensions("design_coherence")

    result = sync_unscored_dimensions(plan, state)
    assert len(result.injected) == 1
    assert plan["queue_order"][0] == "issue_a"
    assert plan["queue_order"][1] == "issue_b"
    assert plan["queue_order"][2] == "subjective::design_coherence"


def test_unscored_multiple_append_to_back():
    """Multiple unscored dims all append to back."""
    plan = _plan_with_queue("issue_a", "issue_b", "issue_c")
    state = _state_with_unscored_dimensions("design_coherence", "error_consistency")

    result = sync_unscored_dimensions(plan, state)
    assert len(result.injected) == 2
    # Existing items keep their positions
    assert plan["queue_order"][0] == "issue_a"
    assert plan["queue_order"][1] == "issue_b"
    assert plan["queue_order"][2] == "issue_c"
    # Unscored dims appended at back
    assert all(
        fid.startswith("subjective::")
        for fid in plan["queue_order"][3:5]
    )


# ---------------------------------------------------------------------------
# Post-cycle injection: cycle_just_completed overrides objective gate
# ---------------------------------------------------------------------------

def test_cycle_completed_injects_stale_despite_objective_backlog():
    """After a completed cycle, stale dims inject even with new objective issues."""
    plan = _plan_with_queue("some_issue::file.py::abc123")
    state = _state_with_stale_dimensions("design_coherence", "error_consistency")
    state["issues"]["some_issue::file.py::abc123"] = {
        "id": "some_issue::file.py::abc123",
        "status": "open",
        "detector": "smells",
    }

    # Without cycle_just_completed: no injection (existing behavior)
    result_normal = sync_stale_dimensions(plan, state)
    assert result_normal.injected == []

    # With cycle_just_completed: inject at back (never reorder existing queue)
    plan2 = _plan_with_queue("some_issue::file.py::abc123")
    result_cycle = sync_stale_dimensions(plan2, state, cycle_just_completed=True)
    assert len(result_cycle.injected) == 2
    # Existing item keeps position; stale dims appended at back
    assert plan2["queue_order"][0] == "some_issue::file.py::abc123"
    assert plan2["queue_order"][1].startswith("subjective::")
    assert plan2["queue_order"][2].startswith("subjective::")


def test_cycle_completed_appends_to_back():
    """Post-cycle stale injection appends to back, preserving existing order."""
    plan = _plan_with_queue("issue_a", "issue_b")
    state = _state_with_stale_dimensions("design_coherence")
    state["issues"]["issue_a"] = {
        "id": "issue_a", "status": "open", "detector": "smells",
    }

    result = sync_stale_dimensions(plan, state, cycle_just_completed=True)
    assert len(result.injected) == 1
    assert plan["queue_order"][0] == "issue_a"
    assert plan["queue_order"][1] == "issue_b"
    assert plan["queue_order"][2] == "subjective::design_coherence"


def test_cycle_completed_injects_under_target_dims():
    """After a completed cycle, under-target (non-stale) dims are also injected."""
    plan = _plan_with_queue("some_issue::file.py::abc123")
    # Dimension is below target but NOT stale (no needs_review_refresh)
    state = _state_with_stale_dimensions("design_coherence")
    state["subjective_assessments"]["design_coherence"]["needs_review_refresh"] = False
    state["issues"]["some_issue::file.py::abc123"] = {
        "id": "some_issue::file.py::abc123",
        "status": "open",
        "detector": "smells",
    }

    # Without cycle_just_completed: no injection (under-target gated by backlog)
    result_normal = sync_stale_dimensions(plan, state)
    assert result_normal.injected == []

    # With cycle_just_completed: under-target dim injected at back
    plan2 = _plan_with_queue("some_issue::file.py::abc123")
    result_cycle = sync_stale_dimensions(plan2, state, cycle_just_completed=True)
    assert len(result_cycle.injected) == 1
    assert plan2["queue_order"][0] == "some_issue::file.py::abc123"
    assert plan2["queue_order"][1] == "subjective::design_coherence"


def test_under_target_injected_when_no_objective_backlog():
    """Under-target dims inject when queue has no objective items (same as stale)."""
    plan = _plan_with_queue()
    state = _state_with_stale_dimensions("design_coherence")
    state["subjective_assessments"]["design_coherence"]["needs_review_refresh"] = False

    result = sync_stale_dimensions(plan, state)
    assert "subjective::design_coherence" in result.injected


def test_cycle_completed_no_stale_dims_no_injection():
    """cycle_just_completed has no effect when no stale dims exist."""
    plan = _plan_with_queue("some_issue::file.py::abc123")
    state = {"issues": {}, "scan_count": 5}

    result = sync_stale_dimensions(plan, state, cycle_just_completed=True)
    assert result.injected == []
    assert plan["queue_order"] == ["some_issue::file.py::abc123"]


def test_cycle_completed_no_objective_appends_to_back():
    """When cycle completed but no objective backlog, stale dims still go to back."""
    plan = _plan_with_queue()
    state = _state_with_stale_dimensions("design_coherence")

    result = sync_stale_dimensions(plan, state, cycle_just_completed=True)
    assert len(result.injected) == 1
    assert plan["queue_order"] == ["subjective::design_coherence"]


def test_plan_reset_does_not_trigger_cycle_completed():
    """After plan reset, stale dims should NOT be front-loaded.

    reset_plan() sets plan_start_scores to {"reset": True} so that
    _cycle_just_completed = not plan.get("plan_start_scores") is False.
    The next scan seeds real scores over the sentinel.
    """
    from desloppify.engine._plan.operations_lifecycle import reset_plan

    plan = _plan_with_queue("some_issue::file.py::abc123")
    plan["plan_start_scores"] = {"strict": 80.0, "overall": 80.0}
    reset_plan(plan)

    # Sentinel should be set
    assert plan["plan_start_scores"] == {"reset": True}
    # Truthiness check — this is what scan_workflow uses
    assert plan.get("plan_start_scores")  # truthy, so cycle_just_completed=False


def test_triage_appends_to_back():
    """Triage stage IDs append to back, never reorder existing items."""
    from desloppify.engine._plan.constants import TRIAGE_STAGE_IDS
    from desloppify.engine._plan.sync_triage import sync_triage_needed

    plan = _plan_with_queue("issue_a", "issue_b")
    plan["epic_triage_meta"] = {"issue_snapshot_hash": "old_hash"}
    state = {
        "issues": {
            "review::file.py::abc": {"status": "open", "detector": "review"},
        },
        "scan_count": 5,
    }

    result = sync_triage_needed(plan, state)
    assert result.injected  # non-empty list of injected stage IDs
    # Existing items keep their positions
    assert plan["queue_order"][0] == "issue_a"
    assert plan["queue_order"][1] == "issue_b"
    # Triage stages appended at back
    assert plan["queue_order"][2] == "triage::observe"
    assert all(sid in plan["queue_order"] for sid in TRIAGE_STAGE_IDS)
