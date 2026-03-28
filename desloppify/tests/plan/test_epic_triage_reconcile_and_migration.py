"""Epic triage reconciliation, compatibility, and migration tests."""

from __future__ import annotations

from desloppify.engine._plan.triage.core import TriageResult, apply_triage_to_plan
from desloppify.engine._plan.scan_issue_reconcile import reconcile_plan_after_scan
from desloppify.engine._plan.schema import empty_plan, ensure_plan_defaults, triage_clusters


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
        from desloppify.engine._plan.operations.cluster import create_cluster
        plan = empty_plan()
        try:
            create_cluster(plan, "epic/test")
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "epic/" in str(e)

    def test_set_focus_with_epic(self):
        from desloppify.engine._plan.operations.lifecycle import set_focus
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
