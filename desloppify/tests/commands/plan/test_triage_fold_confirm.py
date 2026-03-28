"""Tests for fold-confirm shortcut in triage stages."""

from __future__ import annotations

import argparse

import desloppify.app.commands.plan.triage.command as triage_mod
from desloppify.app.commands.plan.triage.services import TriageServices
from desloppify.engine._plan.schema import empty_plan
from desloppify.engine._plan.constants import TRIAGE_STAGE_IDS

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


def _plan_with_stages(*stage_names: str, confirmed: bool = False) -> dict:
    plan = empty_plan()
    plan["queue_order"] = list(TRIAGE_STAGE_IDS)
    meta = plan.setdefault("epic_triage_meta", {})
    stages = meta.setdefault("triage_stages", {})
    for name in stage_names:
        stages[name] = {
            "stage": name,
            "report": (
                "A sufficiently long report for the stage that meets minimum "
                "length requirements and more text to ensure validation passes"
                " — covers r1 r2 r3 r4 r5"
            ),
            "cited_ids": ["r1", "r2", "r3"],
            "timestamp": "2025-06-01T00:00:00Z",
            "issue_count": 5,
        }
        if confirmed:
            stages[name]["confirmed_at"] = "2025-06-01T00:01:00Z"
            stages[name]["confirmed_text"] = (
                "I have thoroughly reviewed all the issues in naming dimension "
                "and this stage analysis is complete"
            )
    return plan


def _plan_with_enriched_clusters(stage_names, confirmed=False):
    """Plan with stages + enriched manual clusters (for organize tests)."""
    plan = _plan_with_stages(*stage_names, confirmed=confirmed)
    plan["clusters"]["fix-naming"] = {
        "name": "fix-naming",
        "issue_ids": ["r1", "r2", "r3", "r4", "r5"],
        "description": "Fix naming issues",
        "action_steps": ["step 1", "step 2", "step 3", "step 4", "step 5"],
        "auto": False,
        "user_modified": True,
        "created_at": "2025-06-01T00:00:00Z",
        "updated_at": "2025-06-01T00:00:00Z",
        "cluster_key": "",
        "action": None,
    }
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


def _fake_services(plan, state, save_plan_fn=None):
    """Build a fake TriageServices with test stubs."""
    return TriageServices(
        command_runtime=lambda args: _fake_runtime(state),
        load_plan=lambda *a, **kw: plan,
        save_plan=save_plan_fn or (lambda p, *a, **kw: None),
        collect_triage_input=lambda p, s: type("TI", (), {
            "open_issues": s.get("issues", {}),
            "resolved_issues": {},
            "new_since_last": [],
            "resolved_since_last": [],
            "existing_clusters": {},
        })(),
        detect_recurring_patterns=lambda _a, _b: {},
        append_log_entry=lambda *a, **kw: None,
        extract_issue_citations=lambda text, ids: set(),
        build_triage_prompt=lambda si: "prompt",
    )


def _patch_triage(monkeypatch, plan, state, save_plan_fn=None):
    """Apply standard triage monkeypatches."""
    monkeypatch.setattr(
        triage_mod, "default_triage_services",
        lambda: _fake_services(plan, state, save_plan_fn),
    )
    monkeypatch.setattr(triage_mod, "require_issue_inventory", lambda s: True)


# ---------------------------------------------------------------------------
# Tests: reflect auto-confirms observe
# ---------------------------------------------------------------------------

class TestReflectFoldConfirmObserve:
    def test_reflect_auto_confirms_observe_with_attestation(self, monkeypatch, capsys):
        """When observe is unconfirmed, --stage reflect with --attestation auto-confirms observe."""
        plan = _plan_with_stages("observe", confirmed=False)
        state = _state_with_issues("r1", "r2", "r3", "r4", "r5")

        _patch_triage(monkeypatch, plan, state)

        attestation = (
            "I have thoroughly reviewed all the naming dimension issues "
            "and the observation analysis is correct and complete"
        )
        reflect_report = (
            "No recurring patterns detected for r1 r2 r3 r4 r5. This is a first triage so "
            "the strategy is to address naming issues first. No prior completed "
            "work to compare against."
        )
        args = _fake_args(
            stage="reflect",
            report=reflect_report,
            attestation=attestation,
        )
        triage_mod.cmd_plan_triage(args)

        stages = plan["epic_triage_meta"]["triage_stages"]
        # Observe should now be confirmed
        assert stages["observe"].get("confirmed_at") is not None
        # Reflect should be recorded
        assert "reflect" in stages

        out = capsys.readouterr().out
        assert "auto-confirmed" in out.lower()

    def test_reflect_blocks_without_attestation_when_observe_unconfirmed(self, monkeypatch, capsys):
        """Without --attestation, reflect is blocked when observe isn't confirmed."""
        plan = _plan_with_stages("observe", confirmed=False)
        state = _state_with_issues("r1", "r2", "r3")

        _patch_triage(monkeypatch, plan, state)

        reflect_report = (
            "Strategy analysis of current issues with enough length to pass validation."
        )
        args = _fake_args(stage="reflect", report=reflect_report)
        triage_mod.cmd_plan_triage(args)

        out = capsys.readouterr().out
        assert "not confirmed" in out.lower()
        assert "attestation" in out.lower()
        # Reflect should NOT be recorded
        stages = plan["epic_triage_meta"]["triage_stages"]
        assert "reflect" not in stages

    def test_reflect_attestation_must_reference_dimension(self, monkeypatch, capsys):
        """Attestation must mention at least one dimension from the observe summary."""
        plan = _plan_with_stages("observe", confirmed=False)
        state = _state_with_issues("r1", "r2", "r3", "r4", "r5")

        _patch_triage(monkeypatch, plan, state)

        # Attestation that does NOT reference any dimension
        attestation = (
            "I have thoroughly reviewed the analysis and it appears to be "
            "complete and correct and covers all aspects adequately"
        )
        reflect_report = (
            "No recurring patterns detected. Strategy is to address all issues. "
            "No prior completed work to compare against."
        )
        args = _fake_args(
            stage="reflect",
            report=reflect_report,
            attestation=attestation,
        )
        triage_mod.cmd_plan_triage(args)

        # Observe should NOT be confirmed (bad attestation)
        stages = plan["epic_triage_meta"]["triage_stages"]
        assert stages["observe"].get("confirmed_at") is None


# ---------------------------------------------------------------------------
# Tests: organize auto-confirms reflect
# ---------------------------------------------------------------------------

class TestOrganizeFoldConfirmReflect:
    def test_organize_auto_confirms_reflect_with_attestation(self, monkeypatch, capsys):
        """When reflect is unconfirmed, --stage organize with --attestation auto-confirms reflect."""
        plan = _plan_with_enriched_clusters(
            ["observe", "reflect"], confirmed=False,
        )
        # Manually confirm observe (needed for reflect->organize flow)
        stages = plan["epic_triage_meta"]["triage_stages"]
        stages["observe"]["confirmed_at"] = "2025-06-01T00:01:00Z"
        stages["observe"]["confirmed_text"] = "confirmed"

        state = _state_with_issues("r1", "r2", "r3", "r4", "r5")

        _patch_triage(monkeypatch, plan, state)

        # Attestation references a cluster name
        attestation = (
            "I have thoroughly reviewed the strategy and the fix-naming cluster "
            "approach addresses the core naming dimension issues properly"
        )
        organize_report = (
            "Organized all issues r1 r2 r3 r4 r5 into fix-naming cluster. Priority is to "
            "address the naming conventions first as they affect readability. "
            "This is the primary focus and unblocks future work."
        )
        args = _fake_args(
            stage="organize",
            report=organize_report,
            attestation=attestation,
        )
        triage_mod.cmd_plan_triage(args)

        stages = plan["epic_triage_meta"]["triage_stages"]
        # Reflect should now be confirmed
        assert stages["reflect"].get("confirmed_at") is not None
        # Organize should be recorded
        assert "organize" in stages

        out = capsys.readouterr().out
        assert "auto-confirmed" in out.lower()


# ---------------------------------------------------------------------------
# Tests: complete auto-confirms organize
# ---------------------------------------------------------------------------

class TestCompleteFoldConfirmOrganize:
    def test_complete_auto_confirms_organize_with_attestation(self, monkeypatch, capsys):
        """When organize is unconfirmed, --complete with --attestation auto-confirms organize."""
        plan = _plan_with_enriched_clusters(
            ["observe", "reflect", "organize"], confirmed=False,
        )
        stages = plan["epic_triage_meta"]["triage_stages"]
        stages["observe"]["confirmed_at"] = "2025-06-01T00:01:00Z"
        stages["observe"]["confirmed_text"] = "confirmed"
        stages["reflect"]["confirmed_at"] = "2025-06-01T00:01:00Z"
        stages["reflect"]["confirmed_text"] = "confirmed"

        state = _state_with_issues("r1", "r2", "r3", "r4", "r5")

        _patch_triage(monkeypatch, plan, state)

        # Attestation references a cluster name
        attestation = (
            "I have thoroughly reviewed the prioritized plan and the fix-naming "
            "cluster is correctly organized with proper action steps"
        )
        strategy = (
            "Execute fix-naming cluster first to resolve all naming convention "
            "issues across the codebase. Start with the most impactful files "
            "and work outward. Verify each fix with a scan afterwards. "
            "The approach addresses root causes rather than symptoms. "
            "After naming is clean, move on to the next priority."
        )
        args = _fake_args(
            complete=True,
            strategy=strategy,
            attestation=attestation,
        )
        triage_mod.cmd_plan_triage(args)

        stages = plan["epic_triage_meta"]["triage_stages"]
        # Organize should have been confirmed before completion cleared stages
        # After completion, stages are reset
        out = capsys.readouterr().out
        assert "auto-confirmed" in out.lower()
        assert "complete" in out.lower()


# ---------------------------------------------------------------------------
# Tests: existing confirm path still works
# ---------------------------------------------------------------------------

class TestExistingConfirmPathUnchanged:
    def test_existing_confirm_path_still_works(self, monkeypatch, capsys):
        """The explicit --confirm observe path still works as before."""
        plan = _plan_with_stages("observe", confirmed=False)
        state = _state_with_issues("r1", "r2", "r3", "r4", "r5")

        _patch_triage(monkeypatch, plan, state)

        attestation = (
            "I have thoroughly reviewed all the naming dimension issues "
            "and the observation analysis is correct and complete"
        )
        args = _fake_args(confirm="observe", attestation=attestation)
        triage_mod.cmd_plan_triage(args)

        stages = plan["epic_triage_meta"]["triage_stages"]
        assert stages["observe"].get("confirmed_at") is not None
        out = capsys.readouterr().out
        assert "confirmed" in out.lower()


# ---------------------------------------------------------------------------
# Tests: completion archives stages
# ---------------------------------------------------------------------------

class TestCompleteArchivesStages:
    def test_complete_archives_stages(self, monkeypatch, capsys):
        """After --complete, last_triage contains the stage data."""
        plan = _plan_with_enriched_clusters(
            ["observe", "reflect", "organize", "enrich", "sense-check"], confirmed=True,
        )
        # Add review issues to queue_order and cluster so coverage check works
        plan["queue_order"] = [*TRIAGE_STAGE_IDS, "review::test.py::r1", "review::test.py::r2"]
        plan["clusters"]["fix-naming"]["issue_ids"] = ["review::test.py::r1", "review::test.py::r2"]
        state = _state_with_issues("review::test.py::r1", "review::test.py::r2")

        _patch_triage(monkeypatch, plan, state)

        strategy = (
            "Execute fix-naming cluster first to resolve all naming convention "
            "issues across the codebase. Start with the most impactful files "
            "and work outward. Verify each fix with a scan afterwards. "
            "The approach addresses root causes rather than symptoms. "
            "After naming is clean, reassess remaining issues."
        )
        args = _fake_args(complete=True, strategy=strategy)
        triage_mod.cmd_plan_triage(args)

        meta = plan["epic_triage_meta"]
        assert "last_triage" in meta
        last = meta["last_triage"]
        assert "completed_at" in last
        assert "stages" in last
        assert "observe" in last["stages"]
        assert "reflect" in last["stages"]
        assert "organize" in last["stages"]
        assert last["strategy"] == strategy
