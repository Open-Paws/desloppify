"""Tests for post-scan plan reconciliation logging."""

from __future__ import annotations

from desloppify.engine._plan.operations.meta import append_log_entry
from desloppify.engine._plan.schema import empty_plan

# ---------------------------------------------------------------------------
# append_log_entry basics
# ---------------------------------------------------------------------------

class TestAppendLogEntry:
    def test_appends_entry(self):
        plan = empty_plan()
        append_log_entry(plan, "sync_unscored", actor="system",
                         detail={"changes": True})
        log = plan.get("execution_log", [])
        assert len(log) == 1
        assert log[0]["action"] == "sync_unscored"
        assert log[0]["actor"] == "system"
        assert log[0]["detail"]["changes"] is True

    def test_auto_cluster_logged(self):
        plan = empty_plan()
        append_log_entry(plan, "auto_cluster", actor="system",
                         detail={"changes": True})
        actions = [e["action"] for e in plan.get("execution_log", [])]
        assert "auto_cluster" in actions

    def test_sync_operations_logged(self):
        plan = empty_plan()
        append_log_entry(plan, "sync_stale", actor="system",
                         detail={"changes": True})
        append_log_entry(plan, "sync_triage", actor="system",
                         detail={"injected": True})
        append_log_entry(plan, "seed_start_scores", actor="system",
                         detail={})
        actions = [e["action"] for e in plan.get("execution_log", [])]
        assert "sync_stale" in actions
        assert "sync_triage" in actions
        assert "seed_start_scores" in actions

    def test_entry_has_timestamp(self):
        plan = empty_plan()
        append_log_entry(plan, "test_action", actor="system")
        log = plan.get("execution_log", [])
        assert log[0]["timestamp"]

    def test_multiple_entries_accumulate(self):
        plan = empty_plan()
        for action in ["sync_unscored", "sync_stale", "auto_cluster"]:
            append_log_entry(plan, action, actor="system",
                             detail={"changes": True})
        log = plan.get("execution_log", [])
        assert len(log) == 3
