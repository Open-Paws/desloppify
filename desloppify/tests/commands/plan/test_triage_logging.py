"""Tests for triage stage logging (execution_log entries)."""

from __future__ import annotations

import argparse

import desloppify.app.commands.plan.triage_handlers as triage_mod
from desloppify.engine._plan.schema import empty_plan
from desloppify.engine._plan.stale_dimensions import TRIAGE_STAGE_IDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_with_review_issues(*ids: str) -> dict:
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


def _plan_with_stages(*stage_names: str, confirmed: bool = False) -> dict:
    plan = empty_plan()
    plan["queue_order"] = list(TRIAGE_STAGE_IDS)
    meta = plan.setdefault("epic_triage_meta", {})
    stages = meta.setdefault("triage_stages", {})
    for name in stage_names:
        stages[name] = {
            "stage": name,
            "report": f"A sufficiently long report for {name} stage that meets minimum length requirements and more text",
            "cited_ids": ["r1", "r2", "r3"],
            "timestamp": "2025-06-01T00:00:00Z",
            "issue_count": 5,
        }
        if confirmed:
            stages[name]["confirmed_at"] = "2025-06-01T00:01:00Z"
            stages[name]["confirmed_text"] = "I have thoroughly reviewed all the issues in this stage"
    return plan


def _fake_runtime(state: dict):
    return type("Ctx", (), {"state": state, "config": {}})()


def _fake_args(**overrides) -> argparse.Namespace:
    defaults = {
        "lang": None,
        "path": ".",
        "confirm": None,
        "attestation": None,
        "confirmed": None,
        "stage": None,
        "report": None,
        "complete": False,
        "confirm_existing": False,
        "strategy": None,
        "note": None,
        "start": False,
        "dry_run": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _log_actions(plan: dict) -> list[str]:
    """Extract action names from execution log."""
    return [e.get("action", "") for e in plan.get("execution_log", [])]


# ---------------------------------------------------------------------------
# Observe stage logs entry
# ---------------------------------------------------------------------------

class TestObserveLogging:
    def test_observe_stage_logs_entry(self, monkeypatch, capsys):
        plan = _plan_with_stages()
        state = _state_with_review_issues("r1", "r2")

        monkeypatch.setattr(triage_mod, "load_plan", lambda *a, **kw: plan)
        monkeypatch.setattr(triage_mod, "command_runtime", lambda args: _fake_runtime(state))
        monkeypatch.setattr(triage_mod, "save_plan", lambda p, *a, **kw: None)
        monkeypatch.setattr(triage_mod, "require_completed_scan", lambda s: True)

        report = "A sufficiently long analysis of themes and root causes across the codebase with contradictions noted"
        args = _fake_args(stage="observe", report=report)
        triage_mod.cmd_plan_triage(args)
        assert "triage_observe" in _log_actions(plan)


# ---------------------------------------------------------------------------
# Confirm observe logs entry
# ---------------------------------------------------------------------------

class TestConfirmObserveLogging:
    def test_confirm_observe_logs_entry(self, monkeypatch, capsys):
        plan = _plan_with_stages("observe")
        state = _state_with_review_issues("r1", "r2")

        monkeypatch.setattr(triage_mod, "load_plan", lambda *a, **kw: plan)
        monkeypatch.setattr(triage_mod, "command_runtime", lambda args: _fake_runtime(state))
        monkeypatch.setattr(triage_mod, "save_plan", lambda p, *a, **kw: None)
        monkeypatch.setattr(triage_mod, "require_completed_scan", lambda s: True)

        attestation = "I have thoroughly reviewed all 2 issues across abstraction_fitness dimension and identified root causes in modules"
        args = _fake_args(confirm="observe", attestation=attestation)
        triage_mod.cmd_plan_triage(args)
        assert "triage_confirm_observe" in _log_actions(plan)


# ---------------------------------------------------------------------------
# Reflect stage logs entry
# ---------------------------------------------------------------------------

class TestReflectLogging:
    def test_reflect_stage_logs_entry(self, monkeypatch, capsys):
        plan = _plan_with_stages("observe", confirmed=True)
        state = _state_with_review_issues("r1", "r2")

        monkeypatch.setattr(triage_mod, "load_plan", lambda *a, **kw: plan)
        monkeypatch.setattr(triage_mod, "command_runtime", lambda args: _fake_runtime(state))
        monkeypatch.setattr(triage_mod, "save_plan", lambda p, *a, **kw: None)
        monkeypatch.setattr(triage_mod, "require_completed_scan", lambda s: True)

        report = "A sufficiently long report about strategy and comparing issues against completed work and more text"
        args = _fake_args(stage="reflect", report=report)
        triage_mod.cmd_plan_triage(args)
        assert "triage_reflect" in _log_actions(plan)


# ---------------------------------------------------------------------------
# Complete logs entry
# ---------------------------------------------------------------------------

class TestCompleteLogging:
    def test_complete_logs_entry(self, monkeypatch, capsys):
        plan = _plan_with_stages("observe", "reflect", "organize", "enrich", confirmed=True)
        plan["clusters"]["fix-names"] = {
            "name": "fix-names",
            "description": "Fix naming",
            "issue_ids": ["r1"],
            "action_steps": ["step 1"],
        }
        state = _state_with_review_issues("r1")

        monkeypatch.setattr(triage_mod, "load_plan", lambda *a, **kw: plan)
        monkeypatch.setattr(triage_mod, "command_runtime", lambda args: _fake_runtime(state))
        monkeypatch.setattr(triage_mod, "save_plan", lambda p, *a, **kw: None)
        monkeypatch.setattr(triage_mod, "require_completed_scan", lambda s: True)

        strategy = "A detailed strategy describing execution order, priorities, verification approach, " * 3
        args = _fake_args(complete=True, strategy=strategy)
        triage_mod.cmd_plan_triage(args)
        assert "triage_complete" in _log_actions(plan)
