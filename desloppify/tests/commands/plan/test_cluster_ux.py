"""Tests for cluster UX improvements: pattern hints, overlap warnings, step feedback."""

from __future__ import annotations

import argparse

import desloppify.app.commands.plan.cluster.dispatch as cluster_mod
import desloppify.app.commands.plan.cluster.update as cluster_update_mod
from desloppify.engine._plan.schema import empty_plan

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_with_issues(*ids: str) -> dict:
    issues = {}
    for fid in ids:
        issues[fid] = {
            "id": fid,
            "status": "open",
            "detector": "review",
            "file": "test.py",
            "summary": f"Issue {fid}",
            "confidence": "medium",
            "tier": 2,
            "detail": {},
        }
    return {"issues": issues, "scan_count": 5, "config": {}}


def _fake_runtime(state: dict):
    return type("Ctx", (), {"state": state, "config": {}})()


def _fake_args(**overrides) -> argparse.Namespace:
    defaults = {
        "lang": None,
        "path": ".",
        "cluster_name": "",
        "patterns": [],
        "cluster_action": None,
        "description": None,
        "action": None,
        "steps": None,
        "steps_file": None,
        "add_step": None,
        "detail": None,
        "update_step": None,
        "remove_step": None,
        "done_step": None,
        "undone_step": None,
        "priority": None,
        "position": "top",
        "target": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# Pattern hints on no match
# ---------------------------------------------------------------------------


class TestPatternHints:
    def test_cluster_add_no_match_shows_hints(self, monkeypatch, capsys):
        """When no issues match, pattern format hints are shown."""
        state = _state_with_issues("review::test.py::foo::abc12345")
        plan = empty_plan()
        plan["clusters"]["my-cluster"] = {
            "issue_ids": [],
            "description": "test",
        }

        monkeypatch.setattr(cluster_mod, "command_runtime", lambda args: _fake_runtime(state))
        monkeypatch.setattr(cluster_mod, "require_issue_inventory", lambda s: True)
        monkeypatch.setattr(cluster_mod, "load_plan", lambda *a, **kw: plan)

        args = _fake_args(cluster_name="my-cluster", patterns=["nonexistent_pattern"])
        cluster_mod._cmd_cluster_add(args)
        out = capsys.readouterr().out
        assert "No matching issues" in out
        assert "Valid patterns:" in out
        assert "8-char hash suffix" in out
        assert "ID prefix" in out

    def test_cluster_remove_no_match_shows_hints(self, monkeypatch, capsys):
        """Remove also shows pattern hints on no match."""
        state = _state_with_issues("review::test.py::foo::abc12345")
        plan = empty_plan()
        plan["clusters"]["my-cluster"] = {
            "issue_ids": ["review::test.py::foo::abc12345"],
            "description": "test",
        }

        monkeypatch.setattr(cluster_mod, "command_runtime", lambda args: _fake_runtime(state))
        monkeypatch.setattr(cluster_mod, "require_issue_inventory", lambda s: True)
        monkeypatch.setattr(cluster_mod, "load_plan", lambda *a, **kw: plan)

        args = _fake_args(cluster_name="my-cluster", patterns=["nonexistent_pattern"])
        cluster_mod._cmd_cluster_remove(args)
        out = capsys.readouterr().out
        assert "No matching issues" in out
        assert "Valid patterns:" in out


# ---------------------------------------------------------------------------
# Overlap warning
# ---------------------------------------------------------------------------


class TestOverlapWarning:
    def test_cluster_add_overlap_warning(self, monkeypatch, capsys):
        """Adding issues that overlap >50% with another cluster shows warning."""
        fid1 = "review::test.py::f1"
        fid2 = "review::test.py::f2"
        state = _state_with_issues(fid1, fid2)
        plan = empty_plan()
        plan["clusters"]["cluster-a"] = {
            "issue_ids": [fid1, fid2],
            "description": "first cluster",
        }
        plan["clusters"]["cluster-b"] = {
            "issue_ids": [],
            "description": "second cluster",
        }

        monkeypatch.setattr(cluster_mod, "command_runtime", lambda args: _fake_runtime(state))
        monkeypatch.setattr(cluster_mod, "require_issue_inventory", lambda s: True)
        monkeypatch.setattr(cluster_mod, "load_plan", lambda *a, **kw: plan)
        monkeypatch.setattr(cluster_mod, "save_plan", lambda p, *a, **kw: None)

        # Add both issues to cluster-b (100% overlap with cluster-a)
        args = _fake_args(cluster_name="cluster-b", patterns=["review"])
        cluster_mod._cmd_cluster_add(args)
        out = capsys.readouterr().out
        assert "overlap" in out.lower()
        assert "cluster-a" in out

    def test_cluster_add_no_overlap_warning_for_auto(self, monkeypatch, capsys):
        """Auto clusters are excluded from overlap checks."""
        fid1 = "review::test.py::f1"
        state = _state_with_issues(fid1)
        plan = empty_plan()
        plan["clusters"]["auto-cluster"] = {
            "issue_ids": [fid1],
            "description": "auto",
            "auto": True,
        }
        plan["clusters"]["manual-cluster"] = {
            "issue_ids": [],
            "description": "manual",
        }

        monkeypatch.setattr(cluster_mod, "command_runtime", lambda args: _fake_runtime(state))
        monkeypatch.setattr(cluster_mod, "require_issue_inventory", lambda s: True)
        monkeypatch.setattr(cluster_mod, "load_plan", lambda *a, **kw: plan)
        monkeypatch.setattr(cluster_mod, "save_plan", lambda p, *a, **kw: None)

        args = _fake_args(cluster_name="manual-cluster", patterns=["review"])
        cluster_mod._cmd_cluster_add(args)
        out = capsys.readouterr().out
        assert "overlap" not in out.lower()


# ---------------------------------------------------------------------------
# Step count feedback
# ---------------------------------------------------------------------------


class TestStepCountFeedback:
    def test_cluster_update_shows_step_count(self, monkeypatch, capsys):
        """Update with steps shows count and listing."""
        plan = empty_plan()
        plan["clusters"]["my-cluster"] = {
            "issue_ids": ["f1"],
            "description": "test",
        }

        monkeypatch.setattr(cluster_update_mod, "load_plan", lambda: plan)
        monkeypatch.setattr(cluster_update_mod, "save_plan", lambda p: None)
        monkeypatch.setattr(cluster_update_mod, "append_log_entry", lambda *a, **kw: None)

        args = _fake_args(
            cluster_name="my-cluster",
            steps=[{"title": "Rename variables"}, {"title": "Update imports"}],
        )
        cluster_mod._cmd_cluster_update(args)
        out = capsys.readouterr().out
        assert "Stored 2 action step(s)." in out
        assert "Rename variables" in out
        assert "Update imports" in out

    def test_cluster_update_with_add_step(self, monkeypatch, capsys):
        """--add-step appends a structured step."""
        plan = empty_plan()
        plan["clusters"]["my-cluster"] = {
            "issue_ids": ["f1"],
            "description": "test",
            "action_steps": [{"title": "existing"}],
        }

        monkeypatch.setattr(cluster_update_mod, "load_plan", lambda: plan)
        monkeypatch.setattr(cluster_update_mod, "save_plan", lambda p: None)
        monkeypatch.setattr(cluster_update_mod, "append_log_entry", lambda *a, **kw: None)

        args = _fake_args(cluster_name="my-cluster", add_step="New step", detail="Some detail")
        cluster_mod._cmd_cluster_update(args)
        out = capsys.readouterr().out
        assert "Added step 2: New step" in out
        steps = plan["clusters"]["my-cluster"]["action_steps"]
        assert len(steps) == 2
        assert steps[1]["title"] == "New step"
        assert steps[1]["detail"] == "Some detail"


# ---------------------------------------------------------------------------
# Overlap scoping — only new issues trigger warnings
# ---------------------------------------------------------------------------


class TestOverlapScoping:
    def test_no_false_overlap_from_existing_members(self, monkeypatch, capsys):
        """Adding a new issue to a cluster with pre-existing overlap doesn't re-warn."""
        fid_shared = "review::test.py::shared"
        fid_new = "review::test.py::new_issue"
        state = _state_with_issues(fid_shared, fid_new)
        plan = empty_plan()
        # cluster-a already has the shared issue
        plan["clusters"]["cluster-a"] = {
            "issue_ids": [fid_shared],
            "description": "first cluster",
        }
        # cluster-b already has the shared issue (pre-existing overlap)
        plan["clusters"]["cluster-b"] = {
            "issue_ids": [fid_shared],
            "description": "second cluster",
        }

        monkeypatch.setattr(cluster_mod, "command_runtime", lambda args: _fake_runtime(state))
        monkeypatch.setattr(cluster_mod, "require_issue_inventory", lambda s: True)
        monkeypatch.setattr(cluster_mod, "load_plan", lambda *a, **kw: plan)
        monkeypatch.setattr(cluster_mod, "save_plan", lambda p, *a, **kw: None)

        # Add only the NEW issue to cluster-b — the shared overlap is pre-existing
        args = _fake_args(cluster_name="cluster-b", patterns=[fid_new])
        cluster_mod._cmd_cluster_add(args)
        out = capsys.readouterr().out
        # Should NOT warn about overlap because the newly-added issue (fid_new)
        # is not in cluster-a
        assert "overlap" not in out.lower()


# ---------------------------------------------------------------------------
# Step display — no double numbering
# ---------------------------------------------------------------------------


class TestStepDisplayNumbering:
    def test_step_display_no_double_numbering(self, monkeypatch, capsys):
        """Steps with leading '1. ' prefix don't get '1. 1. ' in output."""
        plan = empty_plan()
        plan["clusters"]["my-cluster"] = {
            "issue_ids": ["f1"],
            "description": "test",
        }

        monkeypatch.setattr(cluster_update_mod, "load_plan", lambda: plan)
        monkeypatch.setattr(cluster_update_mod, "save_plan", lambda p: None)
        monkeypatch.setattr(cluster_update_mod, "append_log_entry", lambda *a, **kw: None)

        args = _fake_args(
            cluster_name="my-cluster",
            steps=[{"title": "1. Audit imports"}, {"title": "2. Remove unused"}],
        )
        cluster_mod._cmd_cluster_update(args)
        out = capsys.readouterr().out
        # Should show "1. Audit imports" not "1. 1. Audit imports"
        assert "1. Audit imports" in out
        assert "2. Remove unused" in out
        assert "1. 1." not in out
        assert "2. 2." not in out
