"""Tests for auto-start triage on --stage observe."""

from __future__ import annotations

import argparse

import desloppify.app.commands.plan.triage_handlers as triage_mod
from desloppify.engine._plan.schema import empty_plan
from desloppify.engine._plan.stale_dimensions import TRIAGE_IDS, TRIAGE_STAGE_IDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_with_issues(*ids: str, dimension: str = "naming") -> dict:
    issues = {}
    for fid in ids:
        issues[fid] = {
            "status": "open",
            "detector": "review",
            "file": "test.py",
            "summary": f"Review issue {fid}",
            "confidence": "medium",
            "tier": 2,
            "detail": {"dimension": dimension},
        }
    return {"issues": issues, "scan_count": 5, "dimension_scores": {}}


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAutoStartTriage:
    def test_observe_auto_starts_triage(self, monkeypatch, capsys):
        """When no triage stages in queue, --stage observe auto-injects them."""
        plan = empty_plan()
        # No triage stage IDs in queue_order
        assert not any(sid in plan.get("queue_order", []) for sid in TRIAGE_IDS)

        state = _state_with_issues("r1", "r2", "r3", "r4", "r5")
        monkeypatch.setattr(triage_mod, "load_plan", lambda *a, **kw: plan)
        monkeypatch.setattr(triage_mod, "command_runtime", lambda args: _fake_runtime(state))
        monkeypatch.setattr(triage_mod, "require_completed_scan", lambda s: True)
        monkeypatch.setattr(triage_mod, "save_plan", lambda p: None)

        long_report = (
            "This is a thorough analysis of the naming and architecture issues. "
            "The main themes are inconsistent naming conventions across modules, "
            "and some architectural coupling between components."
        )
        args = _fake_args(stage="observe", report=long_report)
        triage_mod.cmd_plan_triage(args)

        # All 4 triage stage IDs should now be in queue
        assert all(sid in plan.get("queue_order", []) for sid in TRIAGE_STAGE_IDS)
        # Stage should be recorded
        stages = plan.get("epic_triage_meta", {}).get("triage_stages", {})
        assert "observe" in stages

    def test_observe_auto_start_prints_note(self, monkeypatch, capsys):
        """Auto-start prints a note about injecting triage::pending."""
        plan = empty_plan()
        state = _state_with_issues("r1", "r2", "r3", "r4", "r5")
        monkeypatch.setattr(triage_mod, "load_plan", lambda *a, **kw: plan)
        monkeypatch.setattr(triage_mod, "command_runtime", lambda args: _fake_runtime(state))
        monkeypatch.setattr(triage_mod, "require_completed_scan", lambda s: True)
        monkeypatch.setattr(triage_mod, "save_plan", lambda p: None)

        long_report = (
            "This is a thorough analysis of the naming and architecture issues. "
            "The main themes are inconsistent naming conventions across modules, "
            "and some architectural coupling between components."
        )
        args = _fake_args(stage="observe", report=long_report)
        triage_mod.cmd_plan_triage(args)

        out = capsys.readouterr().out
        assert "auto-started" in out.lower()

    def test_observe_works_normally_when_already_started(self, monkeypatch, capsys):
        """When triage stages already in queue, observe proceeds without double-injection."""
        plan = empty_plan()
        plan["queue_order"] = list(TRIAGE_STAGE_IDS)

        state = _state_with_issues("r1", "r2", "r3", "r4", "r5")
        monkeypatch.setattr(triage_mod, "load_plan", lambda *a, **kw: plan)
        monkeypatch.setattr(triage_mod, "command_runtime", lambda args: _fake_runtime(state))
        monkeypatch.setattr(triage_mod, "require_completed_scan", lambda s: True)
        monkeypatch.setattr(triage_mod, "save_plan", lambda p: None)

        long_report = (
            "This is a thorough analysis of the naming and architecture issues. "
            "The main themes are inconsistent naming conventions across modules, "
            "and some architectural coupling between components."
        )
        args = _fake_args(stage="observe", report=long_report)
        triage_mod.cmd_plan_triage(args)

        out = capsys.readouterr().out
        assert "auto-started" not in out.lower()
        # No duplicate stage IDs
        for sid in TRIAGE_STAGE_IDS:
            assert plan["queue_order"].count(sid) == 1
        # Stage should be recorded
        stages = plan.get("epic_triage_meta", {}).get("triage_stages", {})
        assert "observe" in stages
