"""Tests for cluster completion guard in plan resolve."""

from __future__ import annotations

from desloppify.app.commands.plan.override_resolve_helpers import (
    _CLUSTER_INDIVIDUAL_THRESHOLD,
    check_cluster_guard as _check_cluster_guard,
)
from desloppify.engine._plan.schema import empty_plan, ensure_plan_defaults

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plan_with_cluster(name: str, issue_ids: list[str]) -> dict:
    plan = empty_plan()
    ensure_plan_defaults(plan)
    plan["clusters"][name] = {
        "name": name,
        "issue_ids": issue_ids,
        "auto": True,
        "cluster_key": f"auto::{name}",
        "action": "autofix",
        "user_modified": False,
    }
    return plan


def _state_with_issues(*ids: str) -> dict:
    issues = {}
    for fid in ids:
        issues[fid] = {
            "id": fid,
            "status": "open",
            "detector": "test",
            "file": "test.py",
            "tier": 1,
            "confidence": "high",
            "summary": f"Issue {fid}",
        }
    return {"issues": issues}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cluster_guard_blocks_small_cluster():
    """Clusters with <= threshold items should be blocked."""
    ids = [f"f{i}" for i in range(5)]
    plan = _plan_with_cluster("auto/test", ids)
    state = _state_with_issues(*ids)

    blocked = _check_cluster_guard(["auto/test"], plan, state)
    assert blocked is True


def test_cluster_guard_blocks_empty_cluster(capsys):
    """Empty clusters should be blocked — must add items first."""
    plan = _plan_with_cluster("auto/test", [])
    state = _state_with_issues()

    blocked = _check_cluster_guard(["auto/test"], plan, state)
    assert blocked is True

    captured = capsys.readouterr()
    assert "empty" in captured.out.lower()
    assert "add items" in captured.out.lower()


def test_cluster_guard_allows_large_cluster():
    """Clusters with > threshold items should be allowed."""
    ids = [f"f{i}" for i in range(_CLUSTER_INDIVIDUAL_THRESHOLD + 1)]
    plan = _plan_with_cluster("auto/test", ids)
    state = _state_with_issues(*ids)

    blocked = _check_cluster_guard(["auto/test"], plan, state)
    assert blocked is False


def test_cluster_guard_allows_non_cluster_pattern():
    """Non-cluster patterns should not be blocked."""
    plan = _plan_with_cluster("auto/test", ["f1", "f2"])
    state = _state_with_issues("f1", "f2")

    blocked = _check_cluster_guard(["f1"], plan, state)
    assert blocked is False


def test_cluster_guard_at_threshold_boundary():
    """Exactly threshold items should be blocked."""
    ids = [f"f{i}" for i in range(_CLUSTER_INDIVIDUAL_THRESHOLD)]
    plan = _plan_with_cluster("auto/test", ids)
    state = _state_with_issues(*ids)

    blocked = _check_cluster_guard(["auto/test"], plan, state)
    assert blocked is True


def test_cluster_guard_prints_items(capsys):
    """Guard should print the items in the cluster."""
    plan = _plan_with_cluster("auto/test", ["f1", "f2"])
    state = _state_with_issues("f1", "f2")

    _check_cluster_guard(["auto/test"], plan, state)
    captured = capsys.readouterr()
    assert "f1" in captured.out
    assert "f2" in captured.out
    assert "individually" in captured.out
