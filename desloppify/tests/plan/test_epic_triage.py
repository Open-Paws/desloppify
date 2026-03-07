"""Tests for epic triage: schema, sync injection, queue items, parsing, and plan mutation."""

from __future__ import annotations

from desloppify.engine._plan.epic_triage import (
    DismissedIssue,
    TriageResult,
    apply_triage_to_plan,
    collect_triage_input,
    parse_triage_result,
)
from desloppify.engine._plan.reconcile import reconcile_plan_after_scan
from desloppify.engine._plan.schema import (
    EPIC_PREFIX,
    VALID_EPIC_DIRECTIONS,
    VALID_SKIP_KINDS,
    empty_plan,
    ensure_plan_defaults,
    triage_clusters,
)
from desloppify.engine._plan.stale_dimensions import (
    TRIAGE_STAGE_IDS,
    is_triage_stale,
    review_issue_snapshot_hash,
    sync_triage_needed,
)
from desloppify.engine._work_queue.synthetic import build_triage_stage_items

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_with_review_issues(*ids: str) -> dict:
    """Build minimal state with open review issues."""
    issues = {}
    for fid in ids:
        issues[fid] = {
            "status": "open",
            "detector": "review",
            "file": "test.py",
            "summary": f"Review issue {fid}",
            "confidence": "medium",
            "tier": 2,
            "detail": {"dimension": "abstraction_fitness"},
        }
    return {"issues": issues, "scan_count": 5, "dimension_scores": {}}


def _state_empty() -> dict:
    return {"issues": {}, "scan_count": 1, "dimension_scores": {}}


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestSchemaDefaults:
    def test_empty_plan_has_triage_meta(self):
        plan = empty_plan()
        assert "epics" not in plan
        assert "epic_triage_meta" in plan
        assert isinstance(plan["epic_triage_meta"], dict)

    def test_plan_version_is_current(self):
        plan = empty_plan()
        from desloppify.engine._plan.schema import PLAN_VERSION
        assert plan["version"] == PLAN_VERSION

    def test_ensure_defaults_adds_meta_to_old_plan(self):
        old = {"version": 2, "created": "x", "updated": "x"}
        ensure_plan_defaults(old)
        assert "epics" not in old
        assert isinstance(old["epic_triage_meta"], dict)

    def test_triaged_out_is_valid_skip_kind(self):
        assert "triaged_out" in VALID_SKIP_KINDS

    def test_epic_prefix(self):
        assert EPIC_PREFIX == "epic/"

    def test_valid_epic_directions(self):
        assert "delete" in VALID_EPIC_DIRECTIONS
        assert "merge" in VALID_EPIC_DIRECTIONS
        assert len(VALID_EPIC_DIRECTIONS) == 8


# ---------------------------------------------------------------------------
# Snapshot hash tests
# ---------------------------------------------------------------------------

class TestSnapshotHash:
    def test_empty_state_returns_empty_hash(self):
        assert review_issue_snapshot_hash(_state_empty()) == ""

    def test_hash_changes_with_issues(self):
        s1 = _state_with_review_issues("a", "b")
        h1 = review_issue_snapshot_hash(s1)
        assert h1 != ""

        s2 = _state_with_review_issues("a", "b", "c")
        h2 = review_issue_snapshot_hash(s2)
        assert h2 != h1

    def test_hash_stable_for_same_issues(self):
        s = _state_with_review_issues("x", "y")
        assert review_issue_snapshot_hash(s) == review_issue_snapshot_hash(s)

    def test_hash_ignores_non_review(self):
        state = {
            "issues": {
                "unused::a": {"status": "open", "detector": "unused"},
                "review::b": {"status": "open", "detector": "review"},
            }
        }
        h = review_issue_snapshot_hash(state)
        assert h != ""
        # Should only include review::b
        state2 = _state_with_review_issues("review::b")
        assert review_issue_snapshot_hash(state2) == h

    def test_hash_ignores_closed(self):
        state = {
            "issues": {
                "review::a": {"status": "fixed", "detector": "review"},
            }
        }
        assert review_issue_snapshot_hash(state) == ""


# ---------------------------------------------------------------------------
# Sync triage needed tests
# ---------------------------------------------------------------------------

class TestSyncTriageNeeded:
    def test_injects_on_new_issues(self):
        plan = empty_plan()
        state = _state_with_review_issues("r1", "r2")
        result = sync_triage_needed(plan, state)
        assert result.injected
        # All 4 stage IDs injected
        assert all(sid in plan["queue_order"] for sid in TRIAGE_STAGE_IDS)

    def test_no_injection_when_hash_up_to_date(self):
        """No injection when snapshot hash matches (review issues unchanged)."""
        state = _state_with_review_issues("r1")
        h = review_issue_snapshot_hash(state)
        plan = empty_plan()
        plan["queue_order"] = list(TRIAGE_STAGE_IDS)
        plan["epic_triage_meta"] = {"issue_snapshot_hash": h}
        result = sync_triage_needed(plan, state)
        assert not result.pruned
        # Stage IDs remain untouched
        assert all(sid in plan["queue_order"] for sid in TRIAGE_STAGE_IDS)

    def test_stages_preserved_when_no_review_issues(self):
        """Triage stages preserved even if review issues vanish."""
        plan = empty_plan()
        plan["queue_order"] = list(TRIAGE_STAGE_IDS)
        state = _state_empty()
        result = sync_triage_needed(plan, state)
        assert not result.pruned
        # Never auto-prunes — stages stay
        assert all(sid in plan["queue_order"] for sid in TRIAGE_STAGE_IDS)

    def test_no_changes_when_already_injected(self):
        plan = empty_plan()
        plan["queue_order"] = list(TRIAGE_STAGE_IDS)
        state = _state_with_review_issues("r1")
        result = sync_triage_needed(plan, state)
        assert not result.injected  # Already present
        assert not result.pruned

    def test_re_triggers_on_resolved_issue(self):
        state = _state_with_review_issues("r1", "r2")
        h = review_issue_snapshot_hash(state)
        plan = empty_plan()
        plan["epic_triage_meta"] = {"issue_snapshot_hash": h}
        # Resolve r2
        state["issues"]["r2"]["status"] = "fixed"
        result = sync_triage_needed(plan, state)
        assert result.injected

    def test_injects_at_front(self):
        plan = empty_plan()
        plan["queue_order"] = ["existing_item"]
        state = _state_with_review_issues("r1")
        sync_triage_needed(plan, state)
        assert plan["queue_order"][0] == "triage::observe"
        assert plan["queue_order"][-1] == "existing_item"

    def test_skips_confirmed_stages(self):
        """Stages already confirmed in meta are not injected."""
        plan = empty_plan()
        plan["epic_triage_meta"] = {
            "triage_stages": {"observe": {"report": "analysis..."}},
        }
        state = _state_with_review_issues("r1")
        sync_triage_needed(plan, state)
        assert "triage::observe" not in plan["queue_order"]
        assert "triage::reflect" in plan["queue_order"]
        assert "triage::organize" in plan["queue_order"]
        assert "triage::commit" in plan["queue_order"]

    def test_preserves_when_stages_in_progress_no_issues(self):
        """Triage stages preserved even if all review issues vanish mid-triage."""
        plan = empty_plan()
        plan["queue_order"] = list(TRIAGE_STAGE_IDS)
        plan["epic_triage_meta"] = {
            "triage_stages": {"observe": {"report": "x"}, "reflect": {"report": "y"}},
        }
        state = _state_empty()
        result = sync_triage_needed(plan, state)
        assert not result.pruned
        # All IDs remain (sync never prunes)
        assert all(sid in plan["queue_order"] for sid in TRIAGE_STAGE_IDS)

    def test_no_auto_prune_when_new_issues_remain(self):
        """Stages not pruned when genuinely new issues still exist."""
        state = _state_with_review_issues("r1")
        h = review_issue_snapshot_hash(state)
        plan = empty_plan()
        plan["queue_order"] = list(TRIAGE_STAGE_IDS)
        plan["epic_triage_meta"] = {
            "issue_snapshot_hash": h,
            "triaged_ids": [],  # r1 not triaged
            "triage_stages": {},
        }
        result = sync_triage_needed(plan, state)
        assert not result.pruned
        assert all(sid in plan["queue_order"] for sid in TRIAGE_STAGE_IDS)

    def test_auto_prune_when_new_issues_resolved(self):
        """Stages auto-pruned when all new issues that triggered injection
        have been resolved and triage was completed before (hash exists)."""
        # Start: r1 was triaged, then r2 appeared (triggering injection),
        # then r2 was resolved. Stages should be pruned.
        state = _state_with_review_issues("r1")
        plan = empty_plan()
        plan["queue_order"] = list(TRIAGE_STAGE_IDS) + ["item1"]
        plan["epic_triage_meta"] = {
            "issue_snapshot_hash": "stale_hash",
            "triaged_ids": ["r1"],  # r1 was triaged, r2 was new
            "triage_stages": {},  # no in-progress triage work
        }
        result = sync_triage_needed(plan, state)
        assert result.pruned
        assert not any(sid in plan["queue_order"] for sid in TRIAGE_STAGE_IDS)
        assert "item1" in plan["queue_order"]  # other items preserved

    def test_no_prune_during_initial_triage(self):
        """Stages NOT pruned during initial triage (no prior hash)."""
        plan = empty_plan()
        plan["queue_order"] = list(TRIAGE_STAGE_IDS)
        # No issue_snapshot_hash — this is the initial triage
        state = _state_empty()
        result = sync_triage_needed(plan, state)
        assert not result.pruned
        assert all(sid in plan["queue_order"] for sid in TRIAGE_STAGE_IDS)

    def test_no_prune_when_triage_in_progress(self):
        """Stages NOT pruned when user has started triage work."""
        state = _state_with_review_issues("r1")
        plan = empty_plan()
        plan["queue_order"] = list(TRIAGE_STAGE_IDS)
        plan["epic_triage_meta"] = {
            "issue_snapshot_hash": "prev_hash",
            "triaged_ids": ["r1"],
            "triage_stages": {"observe": {"report": "analysis..."}},
        }
        result = sync_triage_needed(plan, state)
        assert not result.pruned
        assert all(sid in plan["queue_order"] for sid in TRIAGE_STAGE_IDS)


# ---------------------------------------------------------------------------
# is_triage_stale tests
# ---------------------------------------------------------------------------

class TestIsTriageStale:
    def test_not_stale_when_no_issues_and_no_stages(self):
        plan = empty_plan()
        state = _state_empty()
        assert not is_triage_stale(plan, state)

    def test_stale_when_new_issues_exist(self):
        state = _state_with_review_issues("r1")
        plan = empty_plan()
        plan["epic_triage_meta"] = {
            "issue_snapshot_hash": "prev_hash",
            "triaged_ids": [],
        }
        assert is_triage_stale(plan, state)

    def test_not_stale_when_stages_present_but_no_new_issues(self):
        """Stages in queue alone should NOT make triage stale if all
        new issues that triggered injection have been resolved."""
        state = _state_with_review_issues("r1")
        plan = empty_plan()
        plan["queue_order"] = list(TRIAGE_STAGE_IDS)
        plan["epic_triage_meta"] = {
            "issue_snapshot_hash": "prev_hash",
            "triaged_ids": ["r1"],
            "triage_stages": {},
        }
        assert not is_triage_stale(plan, state)

    def test_stale_when_stages_present_with_in_progress_work(self):
        """Stages in queue ARE stale when user has started triage work."""
        state = _state_with_review_issues("r1")
        plan = empty_plan()
        plan["queue_order"] = list(TRIAGE_STAGE_IDS)
        plan["epic_triage_meta"] = {
            "triaged_ids": ["r1"],
            "triage_stages": {"observe": {"report": "analysis"}},
        }
        assert is_triage_stale(plan, state)

    def test_not_stale_when_only_resolutions(self):
        """Resolving triaged issues should not trigger staleness."""
        state = _state_with_review_issues("r1")
        # Add r2 to triaged_ids but r2 has been resolved (not in current state)
        plan = empty_plan()
        plan["epic_triage_meta"] = {
            "issue_snapshot_hash": "different_hash",
            "triaged_ids": ["r1", "r2"],
        }
        assert not is_triage_stale(plan, state)


# ---------------------------------------------------------------------------
# Build triage item tests
# ---------------------------------------------------------------------------

class TestBuildTriageStageItems:
    def test_returns_empty_when_not_in_queue(self):
        plan = empty_plan()
        state = _state_with_review_issues("r1")
        assert build_triage_stage_items(plan, state) == []

    def test_returns_items_for_each_stage(self):
        plan = empty_plan()
        plan["queue_order"] = list(TRIAGE_STAGE_IDS)
        state = _state_with_review_issues("r1", "r2")
        items = build_triage_stage_items(plan, state)
        assert len(items) == 5
        assert all(it["tier"] == 1 for it in items)
        assert all(it["kind"] == "workflow_stage" for it in items)
        assert items[0]["id"] == "triage::observe"
        assert items[0]["primary_command"] == "desloppify plan triage --stage observe"

    def test_counts_issues(self):
        plan = empty_plan()
        plan["queue_order"] = list(TRIAGE_STAGE_IDS)
        state = _state_with_review_issues("r1", "r2", "r3")
        items = build_triage_stage_items(plan, state)
        assert items[0]["detail"]["total_review_issues"] == 3

    def test_blocked_by_chain(self):
        plan = empty_plan()
        plan["queue_order"] = list(TRIAGE_STAGE_IDS)
        state = _state_with_review_issues("r1")
        items = build_triage_stage_items(plan, state)
        # observe has no dependencies
        assert items[0]["blocked_by"] == []
        assert not items[0]["is_blocked"]
        # reflect depends on observe
        assert "triage::observe" in items[1]["blocked_by"]
        assert items[1]["is_blocked"]

    def test_skips_confirmed_stages(self):
        plan = empty_plan()
        plan["queue_order"] = list(TRIAGE_STAGE_IDS)
        plan["epic_triage_meta"] = {
            "triage_stages": {"observe": {"report": "done"}},
        }
        state = _state_with_review_issues("r1")
        items = build_triage_stage_items(plan, state)
        ids = [it["id"] for it in items]
        assert "triage::observe" not in ids
        assert "triage::reflect" in ids


# ---------------------------------------------------------------------------
# Collect triage input tests
# ---------------------------------------------------------------------------

class TestCollectTriageInput:
    def test_collects_open_review_issues(self):
        plan = empty_plan()
        state = _state_with_review_issues("r1", "r2")
        state["issues"]["u1"] = {"status": "open", "detector": "unused"}
        si = collect_triage_input(plan, state)
        assert len(si.open_issues) == 2
        assert "r1" in si.open_issues
        assert len(si.mechanical_issues) == 1
        assert "u1" in si.mechanical_issues

    def test_includes_existing_epics(self):
        plan = empty_plan()
        plan["clusters"]["epic/test"] = {
            "name": "epic/test", "thesis": "test", "direction": "delete",
            "issue_ids": [], "auto": True, "cluster_key": "epic::epic/test",
        }
        state = _state_with_review_issues("r1")
        si = collect_triage_input(plan, state)
        assert "epic/test" in si.existing_epics

    def test_tracks_new_since_last(self):
        plan = empty_plan()
        plan["epic_triage_meta"] = {"triaged_ids": ["r1"]}
        state = _state_with_review_issues("r1", "r2")
        si = collect_triage_input(plan, state)
        assert si.new_since_last == {"r2"}
        assert si.resolved_since_last == set()


# ---------------------------------------------------------------------------
# Parse triage result tests
# ---------------------------------------------------------------------------

class TestParseTriageResult:
    def test_parses_valid_result(self):
        valid_ids = {"r1", "r2", "r3"}
        raw = {
            "strategy_summary": "Test strategy",
            "epics": [
                {
                    "name": "test-epic",
                    "thesis": "Do the thing",
                    "direction": "delete",
                    "root_cause": "legacy code",
                    "issue_ids": ["r1", "r2"],
                    "dismissed": [],
                    "agent_safe": True,
                    "dependency_order": 1,
                    "action_steps": ["step 1"],
                    "status": "pending",
                }
            ],
            "dismissed_issues": [
                {"issue_id": "r3", "reason": "false positive"}
            ],
            "priority_rationale": "because",
        }
        result = parse_triage_result(raw, valid_ids)
        assert result.strategy_summary == "Test strategy"
        assert len(result.epics) == 1
        assert result.epics[0]["issue_ids"] == ["r1", "r2"]
        assert len(result.dismissed_issues) == 1

    def test_rejects_invalid_issue_ids(self):
        valid_ids = {"r1"}
        raw = {
            "epics": [
                {
                    "name": "test",
                    "thesis": "x",
                    "direction": "delete",
                    "issue_ids": ["r1", "invalid"],
                }
            ]
        }
        result = parse_triage_result(raw, valid_ids)
        assert result.epics[0]["issue_ids"] == ["r1"]

    def test_rejects_invalid_direction(self):
        raw = {
            "epics": [
                {
                    "name": "test",
                    "thesis": "x",
                    "direction": "invalid_direction",
                    "issue_ids": [],
                }
            ]
        }
        result = parse_triage_result(raw, set())
        assert result.epics[0]["direction"] == "simplify"  # fallback

    def test_dismissed_issue_requires_valid_id(self):
        raw = {
            "dismissed_issues": [
                {"issue_id": "valid", "reason": "x"},
                {"issue_id": "invalid", "reason": "x"},
            ]
        }
        result = parse_triage_result(raw, {"valid"})
        assert len(result.dismissed_issues) == 1


# ---------------------------------------------------------------------------
# Apply triage to plan tests
# ---------------------------------------------------------------------------

class TestApplyTriageToPlan:
    def test_creates_epics(self):
        plan = empty_plan()
        state = _state_with_review_issues("r1", "r2")
        triage_result = TriageResult(
            strategy_summary="Test strategy",
            epics=[
                {
                    "name": "test-cleanup",
                    "thesis": "Clean up test code",
                    "direction": "delete",
                    "issue_ids": ["r1", "r2"],
                    "agent_safe": True,
                    "dependency_order": 1,
                    "action_steps": ["step 1"],
                    "status": "pending",
                }
            ],
        )
        result = apply_triage_to_plan(plan, state, triage_result)
        assert result.epics_created == 1
        assert "epic/test-cleanup" in plan["clusters"]
        epic = plan["clusters"]["epic/test-cleanup"]
        assert epic["thesis"] == "Clean up test code"
        assert epic["auto"] is True

    def test_updates_existing_epics(self):
        plan = empty_plan()
        plan["clusters"]["epic/test"] = {
            "name": "epic/test",
            "thesis": "old",
            "direction": "delete",
            "issue_ids": ["r1"],
            "status": "pending",
            "created_at": "2025-01-01",
            "updated_at": "2025-01-01",
            "auto": True,
            "cluster_key": "epic::epic/test",
        }
        state = _state_with_review_issues("r1", "r2")
        triage_result = TriageResult(
            strategy_summary="Updated",
            epics=[
                {
                    "name": "epic/test",
                    "thesis": "new thesis",
                    "direction": "merge",
                    "issue_ids": ["r1", "r2"],
                    "dependency_order": 1,
                    "status": "pending",
                }
            ],
        )
        result = apply_triage_to_plan(plan, state, triage_result)
        assert result.epics_updated == 1
        assert plan["clusters"]["epic/test"]["thesis"] == "new thesis"

    def test_preserves_in_progress_status(self):
        plan = empty_plan()
        plan["clusters"]["epic/active"] = {
            "name": "epic/active",
            "thesis": "working on it",
            "direction": "delete",
            "issue_ids": ["r1"],
            "status": "in_progress",
            "created_at": "2025-01-01",
            "updated_at": "2025-01-01",
            "auto": True,
            "cluster_key": "epic::epic/active",
        }
        state = _state_with_review_issues("r1")
        triage_result = TriageResult(
            strategy_summary="x",
            epics=[
                {
                    "name": "epic/active",
                    "thesis": "updated",
                    "direction": "delete",
                    "issue_ids": ["r1"],
                    "dependency_order": 1,
                    "status": "pending",  # LLM says pending but we keep in_progress
                }
            ],
        )
        apply_triage_to_plan(plan, state, triage_result)
        assert plan["clusters"]["epic/active"]["status"] == "in_progress"

    def test_dismisses_issues(self):
        plan = empty_plan()
        plan["queue_order"] = ["r1", "r2", "r3"]
        state = _state_with_review_issues("r1", "r2", "r3")
        triage_result = TriageResult(
            strategy_summary="x",
            epics=[],
            dismissed_issues=[
                DismissedIssue(issue_id="r3", reason="false positive"),
            ],
        )
        result = apply_triage_to_plan(plan, state, triage_result)
        assert result.issues_dismissed == 1
        assert "r3" in plan["skipped"]
        assert plan["skipped"]["r3"]["kind"] == "triaged_out"
        assert "r3" not in plan["queue_order"]

    def test_updates_snapshot_hash(self):
        plan = empty_plan()
        state = _state_with_review_issues("r1")
        triage_result = TriageResult(strategy_summary="x", epics=[])
        apply_triage_to_plan(plan, state, triage_result)
        meta = plan["epic_triage_meta"]
        assert meta["issue_snapshot_hash"] == review_issue_snapshot_hash(state)
        assert meta["strategy_summary"] == "x"
        assert meta["version"] == 1

    def test_reorders_queue_by_dependency(self):
        plan = empty_plan()
        plan["queue_order"] = ["r1", "r2", "r3", "other"]
        state = _state_with_review_issues("r1", "r2", "r3")
        triage_result = TriageResult(
            strategy_summary="x",
            epics=[
                {
                    "name": "second",
                    "thesis": "second",
                    "direction": "merge",
                    "issue_ids": ["r2"],
                    "dependency_order": 2,
                    "status": "pending",
                },
                {
                    "name": "first",
                    "thesis": "first",
                    "direction": "delete",
                    "issue_ids": ["r1", "r3"],
                    "dependency_order": 1,
                    "status": "pending",
                },
            ],
        )
        apply_triage_to_plan(plan, state, triage_result)
        # Epic issues ordered by dependency: r1, r3 (dep 1), r2 (dep 2), then non-epic
        assert plan["queue_order"] == ["r1", "r3", "r2", "other"]


# ---------------------------------------------------------------------------
# Reconciliation tests
# ---------------------------------------------------------------------------

class TestReconcileWithEpics:
    def test_removes_dead_issues_from_epics(self):
        plan = empty_plan()
        plan["clusters"]["epic/test"] = {
            "name": "epic/test",
            "thesis": "x",
            "direction": "delete",
            "issue_ids": ["r1", "r2"],
            "dismissed": [],
            "status": "pending",
            "auto": True,
            "cluster_key": "epic::epic/test",
        }
        # r1 still alive, r2 gone
        state = _state_with_review_issues("r1")
        result = reconcile_plan_after_scan(plan, state)
        assert plan["clusters"]["epic/test"]["issue_ids"] == ["r1"]
        assert result.changes > 0

    def test_deletes_empty_epics(self):
        plan = empty_plan()
        plan["clusters"]["epic/dead"] = {
            "name": "epic/dead",
            "thesis": "x",
            "direction": "delete",
            "issue_ids": ["r1"],
            "dismissed": [],
            "status": "pending",
            "auto": True,
            "cluster_key": "epic::epic/dead",
        }
        state = _state_empty()
        reconcile_plan_after_scan(plan, state)
        assert "epic/dead" not in plan["clusters"]

    def test_marks_completed_epics(self):
        plan = empty_plan()
        plan["clusters"]["epic/done"] = {
            "name": "epic/done",
            "thesis": "x",
            "direction": "delete",
            "issue_ids": ["r1"],
            "dismissed": ["r2"],
            "status": "pending",
            "auto": True,
            "cluster_key": "epic::epic/done",
        }
        # r1 resolved, r2 still alive (dismissed)
        state = {"issues": {
            "r2": {"status": "open", "detector": "review"},
        }}
        reconcile_plan_after_scan(plan, state)
        # r1 is gone → epic has no issue_ids → gets deleted
        assert "epic/done" not in plan["clusters"]


# ---------------------------------------------------------------------------
# Operations compatibility tests
# ---------------------------------------------------------------------------

class TestOperationsCompat:
    def test_create_cluster_rejects_epic_prefix(self):
        from desloppify.engine._plan.operations_cluster import create_cluster
        plan = empty_plan()
        try:
            create_cluster(plan, "epic/test")
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "epic/" in str(e)

    def test_set_focus_with_epic(self):
        from desloppify.engine._plan.operations_lifecycle import set_focus
        plan = empty_plan()
        plan["clusters"]["epic/test"] = {
            "name": "epic/test",
            "thesis": "x",
            "direction": "delete",
            "issue_ids": ["r1"],
            "auto": True,
            "cluster_key": "epic::epic/test",
            "created_at": "2025-01-01",
            "updated_at": "2025-01-01",
        }
        set_focus(plan, "epic/test")
        assert plan["active_cluster"] == "epic/test"
        assert "epic/test" in plan["clusters"]


# ---------------------------------------------------------------------------
# Idempotency test
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_reapply_same_triage(self):
        plan = empty_plan()
        state = _state_with_review_issues("r1", "r2")
        triage_result = TriageResult(
            strategy_summary="test",
            epics=[
                {
                    "name": "test",
                    "thesis": "x",
                    "direction": "delete",
                    "issue_ids": ["r1", "r2"],
                    "dependency_order": 1,
                    "status": "pending",
                }
            ],
        )
        r1 = apply_triage_to_plan(plan, state, triage_result)
        assert r1.epics_created == 1

        # Apply same triage again
        r2 = apply_triage_to_plan(plan, state, triage_result)
        assert r2.epics_updated == 1
        assert r2.epics_created == 0
        # Epic should still exist with same data
        assert "epic/test" in plan["clusters"]


# ---------------------------------------------------------------------------
# Migration test (v3 epics → v4 clusters)
# ---------------------------------------------------------------------------

class TestEpicMigration:
    def test_migrates_epics_to_clusters(self):
        plan = {
            "version": 3,
            "created": "2025-01-01",
            "updated": "2025-01-01",
            "epics": {
                "epic/cleanup": {
                    "name": "epic/cleanup",
                    "thesis": "Clean up dead code",
                    "direction": "delete",
                    "issue_ids": ["r1", "r2"],
                    "status": "pending",
                    "agent_safe": True,
                    "dependency_order": 1,
                    "action_steps": ["step 1"],
                    "dismissed": ["r3"],
                    "supersedes": [],
                    "source_clusters": [],
                    "triage_version": 1,
                    "created_at": "2025-01-01",
                    "updated_at": "2025-01-01",
                }
            },
        }
        ensure_plan_defaults(plan)
        # Epics key should be removed entirely
        assert "epics" not in plan
        # Epic should now be in clusters
        assert "epic/cleanup" in plan["clusters"]
        cluster = plan["clusters"]["epic/cleanup"]
        assert cluster["thesis"] == "Clean up dead code"
        assert cluster["direction"] == "delete"
        assert cluster["issue_ids"] == ["r1", "r2"]
        assert cluster["auto"] is True
        assert cluster["cluster_key"] == "epic::epic/cleanup"
        assert cluster["agent_safe"] is True
        assert cluster["status"] == "pending"

    def test_migration_does_not_overwrite_existing_cluster(self):
        plan = {
            "version": 3,
            "created": "2025-01-01",
            "updated": "2025-01-01",
            "clusters": {
                "epic/existing": {
                    "name": "epic/existing",
                    "description": "Already here",
                    "issue_ids": ["r1"],
                    "auto": True,
                    "cluster_key": "epic::epic/existing",
                    "thesis": "Already migrated",
                }
            },
            "epics": {
                "epic/existing": {
                    "name": "epic/existing",
                    "thesis": "Old thesis",
                    "direction": "merge",
                    "issue_ids": ["r1", "r2"],
                    "status": "pending",
                }
            },
        }
        ensure_plan_defaults(plan)
        assert "epics" not in plan
        # Should keep existing cluster, not overwrite
        assert plan["clusters"]["epic/existing"]["thesis"] == "Already migrated"

    def test_triage_clusters_helper(self):
        plan = empty_plan()
        plan["clusters"]["epic/a"] = {
            "name": "epic/a", "thesis": "do thing", "issue_ids": [],
            "auto": True, "cluster_key": "epic::epic/a",
        }
        plan["clusters"]["auto/b"] = {
            "name": "auto/b", "issue_ids": [], "auto": True, "cluster_key": "auto::b",
        }
        result = triage_clusters(plan)
        assert "epic/a" in result
        assert "auto/b" not in result
