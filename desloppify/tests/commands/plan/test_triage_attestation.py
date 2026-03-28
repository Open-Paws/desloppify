"""Tests for smart attestation validation in triage stages."""

from __future__ import annotations

import argparse

import desloppify.app.commands.plan.triage.command as triage_mod
from desloppify.app.commands.plan.triage.confirmations.basic import (
    MIN_ATTESTATION_LEN,
    validate_attestation,
)
from desloppify.app.commands.plan.triage.services import TriageServices
from desloppify.engine._plan.schema import empty_plan
from desloppify.engine._plan.constants import TRIAGE_STAGE_IDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_with_issues(*ids: str, dimension: str = "naming") -> dict:
    """Build minimal state with open review issues in a given dimension."""
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
            "report": f"A sufficiently long report for {name} stage that meets minimum length requirements and more text",
            "cited_ids": ["r1", "r2", "r3"],
            "timestamp": "2025-06-01T00:00:00Z",
            "issue_count": 5,
        }
        if name == "observe":
            stages[name]["dimension_names"] = ["naming"]
            stages[name]["dimension_counts"] = {"naming": 5}
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
# Unit tests for validate_attestation
# ---------------------------------------------------------------------------


class TestValidateAttestation:
    def test_validate_observe_requires_dimension(self):
        """Generic text without dimension name is rejected for observe."""
        err = validate_attestation(
            "I have reviewed all issues thoroughly and carefully considered every aspect of the codebase",
            "observe",
            dimensions=["naming", "coupling", "abstraction_fitness"],
        )
        assert err is not None
        assert "dimension" in err.lower()

    def test_validate_observe_accepts_dimension(self):
        """Text mentioning a dimension name passes for observe."""
        err = validate_attestation(
            "I reviewed the naming dimension issues and identified root causes across the codebase modules",
            "observe",
            dimensions=["naming", "coupling"],
        )
        assert err is None

    def test_validate_observe_accepts_underscored_dimension(self):
        """'abstraction fitness' matches dimension 'abstraction_fitness'."""
        err = validate_attestation(
            "I analyzed the abstraction fitness issues carefully and identified patterns across modules in the code",
            "observe",
            dimensions=["abstraction_fitness", "coupling"],
        )
        assert err is None

    def test_validate_reflect_requires_ref(self):
        """Generic text without dimension or cluster name is rejected for reflect."""
        err = validate_attestation(
            "I have formed a strategy that accounts for all issues and patterns in the codebase thoroughly",
            "reflect",
            dimensions=["naming"],
            cluster_names=["fix-naming"],
        )
        assert err is not None

    def test_validate_reflect_accepts_cluster_name(self):
        """Text with cluster name passes for reflect."""
        err = validate_attestation(
            "My strategy accounts for the fix-naming cluster and addresses root causes across the codebase modules",
            "reflect",
            dimensions=["naming"],
            cluster_names=["fix-naming"],
        )
        assert err is None

    def test_validate_reflect_accepts_dimension(self):
        """Text with dimension name passes for reflect."""
        err = validate_attestation(
            "My strategy addresses the naming dimension patterns and recurring issues across the codebase modules",
            "reflect",
            dimensions=["naming"],
            cluster_names=["fix-naming"],
        )
        assert err is None

    def test_validate_organize_requires_cluster(self):
        """Generic text without cluster name is rejected for organize."""
        err = validate_attestation(
            "This plan is correct and I have verified all clusters are properly ordered and enriched thoroughly",
            "organize",
            cluster_names=["fix-naming", "reduce-coupling"],
        )
        assert err is not None
        assert "cluster" in err.lower()

    def test_validate_organize_accepts_cluster(self):
        """Text with cluster name passes for organize."""
        err = validate_attestation(
            "This plan correctly prioritizes fix-naming first and I verified all clusters have steps and descriptions",
            "organize",
            cluster_names=["fix-naming", "reduce-coupling"],
        )
        assert err is None

    def test_validate_organize_accepts_substantive_work_product_without_cluster_name(self):
        """Organize can pass without an exact cluster name when the attestation describes the organized work."""
        err = validate_attestation(
            "I organized all review issues into clusters with clear priority ordering, action steps, and dependency decisions grounded in the code.",
            "organize",
            cluster_names=["fix-naming", "reduce-coupling"],
        )
        assert err is None

    def test_validate_enrich_accepts_substantive_work_product_without_cluster_name(self):
        """Enrich can pass without an exact cluster name when executor-ready details are described."""
        err = validate_attestation(
            "The planned steps are executor-ready with concrete file paths, issue refs, detailed instructions, and effort tags verified against the codebase.",
            "enrich",
            cluster_names=["fix-naming", "reduce-coupling"],
        )
        assert err is None

    def test_validate_sense_check_accepts_substantive_work_product_without_cluster_name(self):
        """Sense-check can pass without an exact cluster name when the verification work is explicit."""
        err = validate_attestation(
            "I verified content and structure, checked cross-cluster dependencies, and confirmed value decisions are safe and accurately recorded.",
            "sense-check",
            cluster_names=["fix-naming", "reduce-coupling"],
        )
        assert err is None

    def test_validate_no_data_passes(self):
        """When no dimensions/clusters provided, validation passes (nothing to check)."""
        err = validate_attestation(
            "I have reviewed everything thoroughly and carefully",
            "observe",
            dimensions=[],
        )
        assert err is None

    def test_attestation_min_length_80(self):
        """Verify MIN_ATTESTATION_LEN is 80."""
        assert MIN_ATTESTATION_LEN == 80

    def test_validate_reflect_accepts_observe_dimension(self):
        """Observe-stage dimension (not recurring) passes for reflect attestation."""
        # 'naming' is an observe dimension, not in recurring — should still pass
        err = validate_attestation(
            "My strategy addresses the naming dimension patterns and recurring issues across the codebase modules",
            "reflect",
            dimensions=["naming", "coupling"],
            cluster_names=[],
        )
        assert err is None

    def test_validate_reflect_error_shows_dims_and_clusters(self):
        """Error message for reflect clearly separates dimensions vs cluster names."""
        err = validate_attestation(
            "I have reviewed everything thoroughly and carefully and formed a solid strategy for the codebase issues",
            "reflect",
            dimensions=["naming", "coupling"],
            cluster_names=["fix-naming"],
        )
        assert err is not None
        assert "Valid dimensions:" in err
        assert "Valid clusters:" in err
        assert "naming" in err
        assert "fix-naming" in err


# ---------------------------------------------------------------------------
# Integration tests through _confirm_observe
# ---------------------------------------------------------------------------


class TestConfirmObserveValidation:
    def test_confirm_observe_rejects_generic_attestation(self, monkeypatch, capsys):
        """Attestation of 80+ chars that doesn't mention any dimension is rejected."""
        plan = _plan_with_stages("observe")
        state = _state_with_issues("r1", "r2", "r3", dimension="naming")

        _patch_triage(monkeypatch, plan, state)

        # 80+ chars but no dimension name
        attestation = "I have thoroughly reviewed all the issues in this codebase and considered every aspect of the analysis carefully"
        assert len(attestation) >= 80
        args = _fake_args(confirm="observe", attestation=attestation)
        triage_mod.cmd_plan_triage(args)
        out = capsys.readouterr().out
        assert "dimension" in out.lower()
        # Should NOT have confirmed
        obs = plan["epic_triage_meta"]["triage_stages"]["observe"]
        assert "confirmed_at" not in obs

    def test_confirm_observe_accepts_specific_attestation(self, monkeypatch, capsys):
        """Attestation of 80+ chars that mentions a dimension name is accepted."""
        plan = _plan_with_stages("observe")
        state = _state_with_issues("r1", "r2", "r3", dimension="naming")
        saved = []

        _patch_triage(monkeypatch, plan, state, save_plan_fn=lambda p, *a, **kw: saved.append(True))

        attestation = "I reviewed the naming dimension issues and identified 3 root causes across the codebase test modules thoroughly"
        assert len(attestation) >= 80
        args = _fake_args(confirm="observe", attestation=attestation)
        triage_mod.cmd_plan_triage(args)
        out = capsys.readouterr().out
        assert "confirmed" in out.lower()
        obs = plan["epic_triage_meta"]["triage_stages"]["observe"]
        assert obs.get("confirmed_at")
