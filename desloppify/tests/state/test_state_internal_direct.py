"""Direct tests for _state modules flagged as transitive-only."""

from __future__ import annotations

import json

import desloppify.engine._state.filtering as filtering_mod
import desloppify.engine._state.noise as noise_mod
import desloppify.engine._state.persistence as persistence_mod
import desloppify.engine._state.resolution as resolution_mod
import desloppify.engine._state.schema as schema_mod


def test_noise_budget_resolution_and_capping():
    per_budget, global_budget, warning = noise_mod.resolve_issue_noise_settings(
        {
            "issue_noise_budget": "bad",
            "issue_noise_global_budget": -5,
        }
    )

    assert per_budget == noise_mod.DEFAULT_ISSUE_NOISE_BUDGET
    assert global_budget == 0
    assert warning is not None
    assert "issue_noise_budget" in warning
    assert "issue_noise_global_budget" in warning

    issues = [
        {
            "id": "a1",
            "detector": "smells",
            "tier": 2,
            "confidence": "high",
            "file": "a.py",
        },
        {
            "id": "a2",
            "detector": "smells",
            "tier": 3,
            "confidence": "low",
            "file": "a.py",
        },
        {
            "id": "b1",
            "detector": "structural",
            "tier": 3,
            "confidence": "medium",
            "file": "b.py",
        },
    ]
    surfaced, hidden = noise_mod.apply_issue_noise_budget(
        issues, budget=1, global_budget=1
    )
    assert len(surfaced) == 1
    assert surfaced[0]["id"] in {"a1", "b1"}
    assert hidden["smells"] >= 1


def test_load_state_missing_and_backup_fallback(tmp_path):
    missing = tmp_path / "missing-state.json"
    loaded = persistence_mod.load_state(missing)
    assert isinstance(loaded, dict)
    assert loaded["version"] == schema_mod.CURRENT_VERSION
    assert loaded["issues"] == {}

    primary = tmp_path / "state.json"
    backup = tmp_path / "state.json.bak"
    primary.write_text("{not-json")
    backup.write_text(json.dumps(schema_mod.empty_state()))

    recovered = persistence_mod.load_state(primary)
    assert recovered["version"] == schema_mod.CURRENT_VERSION
    assert recovered["issues"] == {}
    assert recovered["strict_score"] == 0


def test_match_and_resolve_issues_updates_state():
    state = schema_mod.empty_state()
    open_issue = filtering_mod.make_issue(
        "unused",
        "pkg/a.py",
        "name",
        tier=2,
        confidence="high",
        summary="unused name",
    )
    hidden_issue = filtering_mod.make_issue(
        "unused",
        "pkg/b.py",
        "name",
        tier=2,
        confidence="high",
        summary="unused name",
    )
    hidden_issue["suppressed"] = True

    state["issues"] = {
        open_issue["id"]: open_issue,
        hidden_issue["id"]: hidden_issue,
    }

    matches = resolution_mod.match_issues(state, "unused", status_filter="open")
    assert len(matches) == 1
    assert matches[0]["id"] == open_issue["id"]

    resolved_ids = resolution_mod.resolve_issues(
        state,
        "unused",
        status="fixed",
        note="done",
        attestation="I fixed this",
    )

    assert resolved_ids == [open_issue["id"]]
    resolved = state["issues"][open_issue["id"]]
    assert resolved["status"] == "fixed"
    assert resolved["note"] == "done"
    assert resolved["resolved_at"] is not None
    assert resolved["resolution_attestation"]["text"] == "I fixed this"
    assert resolved["resolution_attestation"]["scan_verified"] is False


def test_open_scope_breakdown_splits_in_scope_and_out_of_scope():
    issues = {
        "smells::src/a.py::x": {
            "status": "open",
            "detector": "smells",
            "file": "src/a.py",
        },
        "smells::scripts/b.py::x": {
            "status": "open",
            "detector": "smells",
            "file": "scripts/b.py",
        },
        "subjective_review::.::holistic_unreviewed": {
            "status": "open",
            "detector": "subjective_review",
            "file": ".",
        },
        "smells::src/c.py::closed": {
            "status": "fixed",
            "detector": "smells",
            "file": "src/c.py",
        },
    }

    counts = filtering_mod.open_scope_breakdown(issues, "src")
    assert counts == {"in_scope": 2, "out_of_scope": 1, "global": 3}

    subjective_counts = filtering_mod.open_scope_breakdown(
        issues,
        "src",
        detector="subjective_review",
    )
    assert subjective_counts == {"in_scope": 1, "out_of_scope": 0, "global": 1}


def test_resolve_fixed_review_marks_assessment_stale_preserves_score():
    """Resolving a review issue as fixed marks assessment stale but keeps score."""
    state = schema_mod.empty_state()
    review_issue = filtering_mod.make_issue(
        "review",
        "pkg/a.py",
        "naming",
        tier=3,
        confidence="high",
        summary="naming issue",
        detail={"dimension": "naming_quality"},
    )
    state["issues"] = {review_issue["id"]: review_issue}
    state["subjective_assessments"] = {
        "naming_quality": {"score": 82, "source": "holistic"},
        "logic_clarity": {"score": 74, "source": "holistic"},
    }

    resolution_mod.resolve_issues(
        state,
        "review::",
        status="fixed",
        note="renamed symbols",
        attestation="I have actually fixed this and I am not gaming the score.",
    )

    naming = state["subjective_assessments"]["naming_quality"]
    logic = state["subjective_assessments"]["logic_clarity"]
    # Score preserved (not zeroed) — only a fresh review changes scores.
    assert naming["score"] == 82
    assert naming["needs_review_refresh"] is True
    assert naming["refresh_reason"] == "review_issue_fixed"
    assert naming["stale_since"] is not None
    # Untouched dimension is unchanged.
    assert logic["score"] == 74
    assert "needs_review_refresh" not in logic


def test_resolve_wontfix_review_marks_assessment_stale():
    """Resolving a review issue as wontfix also marks assessment stale."""
    state = schema_mod.empty_state()
    review_issue = filtering_mod.make_issue(
        "review",
        "pkg/a.py",
        "naming",
        tier=3,
        confidence="high",
        summary="naming issue",
        detail={"dimension": "naming_quality"},
    )
    state["issues"] = {review_issue["id"]: review_issue}
    state["subjective_assessments"] = {
        "naming_quality": {"score": 82, "source": "holistic"}
    }

    resolution_mod.resolve_issues(
        state,
        "review::",
        status="wontfix",
        note="intentional",
        attestation="I have actually reviewed this and I am not gaming the score.",
    )

    naming = state["subjective_assessments"]["naming_quality"]
    assert naming["score"] == 82
    assert naming["needs_review_refresh"] is True
    assert naming["refresh_reason"] == "review_issue_wontfix"
    assert naming["stale_since"] is not None


def test_resolve_false_positive_review_marks_assessment_stale():
    """Resolving a review issue as false_positive also marks assessment stale."""
    state = schema_mod.empty_state()
    review_issue = filtering_mod.make_issue(
        "review",
        "pkg/a.py",
        "naming",
        tier=3,
        confidence="high",
        summary="naming issue",
        detail={"dimension": "naming_quality"},
    )
    state["issues"] = {review_issue["id"]: review_issue}
    state["subjective_assessments"] = {
        "naming_quality": {"score": 82, "source": "holistic"}
    }

    resolution_mod.resolve_issues(
        state,
        "review::",
        status="false_positive",
        note="not a real issue",
        attestation="This is not an actual defect.",
    )

    naming = state["subjective_assessments"]["naming_quality"]
    assert naming["score"] == 82
    assert naming["needs_review_refresh"] is True
    assert naming["refresh_reason"] == "review_issue_false_positive"


def test_resolve_non_review_issue_does_not_mark_stale():
    """Resolving a non-review issue does not touch subjective assessments."""
    state = schema_mod.empty_state()
    issue = filtering_mod.make_issue(
        "unused",
        "pkg/a.py",
        "name",
        tier=2,
        confidence="high",
        summary="unused name",
    )
    state["issues"] = {issue["id"]: issue}
    state["subjective_assessments"] = {
        "naming_quality": {"score": 82, "source": "holistic"}
    }

    resolution_mod.resolve_issues(
        state,
        "unused",
        status="fixed",
        note="done",
        attestation="Fixed it.",
    )

    naming = state["subjective_assessments"]["naming_quality"]
    assert naming["score"] == 82
    assert "needs_review_refresh" not in naming


def test_resolve_wontfix_captures_snapshot_metadata():
    state = schema_mod.empty_state()
    state["scan_count"] = 17
    issue = filtering_mod.make_issue(
        "structural",
        "pkg/a.py",
        "",
        tier=3,
        confidence="medium",
        summary="large module",
        detail={"loc": 210, "complexity_score": 42},
    )
    state["issues"] = {issue["id"]: issue}

    resolution_mod.resolve_issues(
        state,
        "structural::",
        status="wontfix",
        note="intentional for now",
        attestation="I have actually reviewed this and I am not gaming the score.",
    )

    resolved = state["issues"][issue["id"]]
    assert resolved["status"] == "wontfix"
    assert resolved["wontfix_scan_count"] == 17
    assert resolved["wontfix_snapshot"]["scan_count"] == 17
    assert resolved["wontfix_snapshot"]["detail"]["loc"] == 210
    assert resolved["wontfix_snapshot"]["detail"]["complexity_score"] == 42


def test_resolve_open_reopens_non_open_issue_and_increments_reopen_count():
    state = schema_mod.empty_state()
    issue = filtering_mod.make_issue(
        "review",
        "pkg/a.py",
        "naming",
        tier=3,
        confidence="high",
        summary="naming issue",
        detail={"dimension": "naming_quality"},
    )
    issue["status"] = "fixed"
    issue["resolved_at"] = "2026-01-01T10:00:00+00:00"
    issue["note"] = "fixed earlier"
    issue["reopen_count"] = 2
    state["issues"] = {issue["id"]: issue}

    resolved_ids = resolution_mod.resolve_issues(
        state,
        "review::",
        status="open",
        note="needs deeper fix",
        attestation=None,
    )

    assert resolved_ids == [issue["id"]]
    reopened = state["issues"][issue["id"]]
    assert reopened["status"] == "open"
    assert reopened["resolved_at"] is None
    assert reopened["note"] == "needs deeper fix"
    assert reopened["reopen_count"] == 3
    attestation = reopened.get("resolution_attestation") or {}
    assert attestation.get("kind") == "manual_reopen"
    assert attestation.get("previous_status") == "fixed"
