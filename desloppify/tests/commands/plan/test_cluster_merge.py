"""Tests for cluster merge command."""

from __future__ import annotations

import pytest

from desloppify.engine._plan.operations.cluster import merge_clusters
from desloppify.engine._plan.schema import empty_plan, ensure_plan_defaults

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plan_with_clusters():
    """Build a plan with two clusters."""
    plan = empty_plan()
    ensure_plan_defaults(plan)
    plan["clusters"]["source-cluster"] = {
        "name": "source-cluster",
        "issue_ids": ["f1", "f2", "f3"],
        "description": "Source description",
        "action_steps": [{"title": "step A"}, {"title": "step B"}],
        "auto": False,
        "user_modified": False,
        "created_at": "2025-06-01T00:00:00Z",
        "updated_at": "2025-06-01T00:00:00Z",
        "cluster_key": "",
        "action": "source action",
    }
    plan["clusters"]["target-cluster"] = {
        "name": "target-cluster",
        "issue_ids": ["f4", "f5"],
        "description": "Target description",
        "action_steps": [{"title": "step X"}],
        "auto": False,
        "user_modified": False,
        "created_at": "2025-06-01T00:00:00Z",
        "updated_at": "2025-06-01T00:00:00Z",
        "cluster_key": "",
        "action": "target action",
    }
    return plan


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMergeClusters:
    def test_merge_moves_issues(self):
        """All source issues are moved to target."""
        plan = _plan_with_clusters()
        added, source_ids = merge_clusters(plan, "source-cluster", "target-cluster")

        target = plan["clusters"]["target-cluster"]
        assert "f1" in target["issue_ids"]
        assert "f2" in target["issue_ids"]
        assert "f3" in target["issue_ids"]
        assert added == 3
        assert sorted(source_ids) == ["f1", "f2", "f3"]

    def test_merge_deletes_source(self):
        """Source cluster is removed after merge."""
        plan = _plan_with_clusters()
        merge_clusters(plan, "source-cluster", "target-cluster")

        assert "source-cluster" not in plan["clusters"]

    def test_merge_preserves_target_metadata(self):
        """When target has metadata, it is NOT overwritten by source."""
        plan = _plan_with_clusters()
        merge_clusters(plan, "source-cluster", "target-cluster")

        target = plan["clusters"]["target-cluster"]
        assert target["description"] == "Target description"
        assert target["action_steps"] == [{"title": "step X"}]
        assert target["action"] == "target action"

    def test_merge_fills_missing_target_metadata(self):
        """When target is missing metadata, source values are copied."""
        plan = _plan_with_clusters()
        # Remove target metadata
        plan["clusters"]["target-cluster"]["description"] = ""
        plan["clusters"]["target-cluster"]["action_steps"] = []
        plan["clusters"]["target-cluster"]["action"] = None

        merge_clusters(plan, "source-cluster", "target-cluster")

        target = plan["clusters"]["target-cluster"]
        assert target["description"] == "Source description"
        assert target["action_steps"] == [{"title": "step A"}, {"title": "step B"}]
        assert target["action"] == "source action"

    def test_merge_nonexistent_source_raises(self):
        """Merging a nonexistent source raises ValueError."""
        plan = _plan_with_clusters()
        with pytest.raises(ValueError, match="does not exist"):
            merge_clusters(plan, "nonexistent", "target-cluster")

    def test_merge_nonexistent_target_raises(self):
        """Merging into a nonexistent target raises ValueError."""
        plan = _plan_with_clusters()
        with pytest.raises(ValueError, match="does not exist"):
            merge_clusters(plan, "source-cluster", "nonexistent")

    def test_merge_deduplicates(self):
        """Issues already in target are not duplicated."""
        plan = _plan_with_clusters()
        # Add f4 to source too (already in target)
        plan["clusters"]["source-cluster"]["issue_ids"].append("f4")

        added, source_ids = merge_clusters(plan, "source-cluster", "target-cluster")

        target = plan["clusters"]["target-cluster"]
        # f4 should appear only once
        assert target["issue_ids"].count("f4") == 1
        # 3 new (f1, f2, f3) — f4 already existed
        assert added == 3
        assert "f4" in source_ids

    def test_merge_updates_overrides(self):
        """Issue overrides are updated to point to the target cluster."""
        plan = _plan_with_clusters()
        merge_clusters(plan, "source-cluster", "target-cluster")

        for fid in ["f1", "f2", "f3"]:
            override = plan["overrides"].get(fid)
            assert override is not None
            assert override["cluster"] == "target-cluster"

    def test_merge_clears_active_cluster_if_source(self):
        """If source is the active_cluster, active_cluster is cleared."""
        plan = _plan_with_clusters()
        plan["active_cluster"] = "source-cluster"

        merge_clusters(plan, "source-cluster", "target-cluster")

        assert plan["active_cluster"] is None

    def test_merge_self_raises(self):
        """Merging a cluster into itself is rejected."""
        plan = _plan_with_clusters()
        with pytest.raises(ValueError, match="Cannot merge a cluster into itself"):
            merge_clusters(plan, "source-cluster", "source-cluster")
