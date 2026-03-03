"""Direct tests for stale-wontfix augmentation in scan workflow."""

from types import SimpleNamespace

import desloppify.app.commands.scan.scan_workflow as scan_workflow_mod
from desloppify.app.commands.scan.scan_workflow import (
    ScanStateContractError,
    ScanRuntime,
    _expire_provisional_manual_override_assessments,
    _augment_with_stale_wontfix_issues,
    _reset_subjective_assessments_for_scan_reset,
)


def test_stale_wontfix_adds_decay_and_drift_issue(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_workflow_mod, "PROJECT_ROOT", tmp_path)

    runtime = ScanRuntime(
        args=SimpleNamespace(),
        state_path=None,
        state={
            "scan_count": 25,
            "issues": {
                "structural::a.py::": {
                    "id": "structural::a.py::",
                    "status": "wontfix",
                    "detector": "structural",
                    "file": "a.py",
                    "wontfix_scan_count": 1,
                    "wontfix_snapshot": {
                        "scan_count": 1,
                        "detail": {"loc": 220, "complexity_score": 35},
                    },
                }
            },
        },
        path=tmp_path,
        config={},
        lang=None,
        lang_label="",
        profile="full",
        effective_include_slow=True,
        zone_overrides=None,
    )

    issues = [
        {
            "id": "structural::a.py::",
            "detector": "structural",
            "file": "a.py",
            "detail": {"loc": 290, "complexity_score": 48},
        }
    ]

    augmented, monitored = _augment_with_stale_wontfix_issues(
        issues,
        runtime,
        decay_scans=20,
    )

    assert monitored == 1
    stale = [issue for issue in augmented if issue.get("detector") == "stale_wontfix"]
    assert len(stale) == 1
    reasons = stale[0]["detail"]["reasons"]
    assert "scan_decay" in reasons
    assert "severity_drift" in reasons
    assert stale[0]["tier"] == 4


def test_stale_wontfix_not_added_when_recent_and_stable(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_workflow_mod, "PROJECT_ROOT", tmp_path)

    runtime = ScanRuntime(
        args=SimpleNamespace(),
        state_path=None,
        state={
            "scan_count": 10,
            "issues": {
                "structural::a.py::": {
                    "id": "structural::a.py::",
                    "status": "wontfix",
                    "detector": "structural",
                    "file": "a.py",
                    "wontfix_scan_count": 9,
                    "wontfix_snapshot": {
                        "scan_count": 9,
                        "detail": {"loc": 220, "complexity_score": 35},
                    },
                }
            },
        },
        path=tmp_path,
        config={},
        lang=None,
        lang_label="",
        profile="full",
        effective_include_slow=True,
        zone_overrides=None,
    )

    issues = [
        {
            "id": "structural::a.py::",
            "detector": "structural",
            "file": "a.py",
            "detail": {"loc": 225, "complexity_score": 36},
        }
    ]

    augmented, monitored = _augment_with_stale_wontfix_issues(
        issues,
        runtime,
        decay_scans=20,
    )

    assert monitored == 1
    stale = [issue for issue in augmented if issue.get("detector") == "stale_wontfix"]
    assert stale == []


def test_scan_reset_zeroes_existing_subjective_scores():
    state = {
        "subjective_assessments": {
            "high_level_elegance": {
                "score": 98.8,
                "source": "holistic",
                "components": ["a"],
                "component_scores": {"a": 98.8},
            },
            "custom_dimension": 71.0,
        }
    }

    reset_count = _reset_subjective_assessments_for_scan_reset(state)

    assessments = state["subjective_assessments"]
    assert reset_count >= 10
    assert assessments["high_level_elegance"]["score"] == 0.0
    assert assessments["high_level_elegance"]["source"] == "scan_reset_subjective"
    assert assessments["high_level_elegance"]["reset_by"] == "scan_reset_subjective"
    assert assessments["high_level_elegance"]["placeholder"] is True
    assert "assessed_at" in assessments["high_level_elegance"]
    assert "components" not in assessments["high_level_elegance"]
    assert "component_scores" not in assessments["high_level_elegance"]
    assert assessments["custom_dimension"]["score"] == 0.0
    assert assessments["custom_dimension"]["source"] == "scan_reset_subjective"
    assert assessments["custom_dimension"]["placeholder"] is True


def test_scan_reset_seeds_subjective_dimensions_when_missing():
    state = {"subjective_assessments": {}}

    reset_count = _reset_subjective_assessments_for_scan_reset(state)

    assessments = state["subjective_assessments"]
    assert reset_count == 12
    assert assessments["naming_quality"]["score"] == 0.0
    assert assessments["package_organization"]["score"] == 0.0
    assert assessments["high_level_elegance"]["score"] == 0.0
    assert assessments["low_level_elegance"]["reset_by"] == "scan_reset_subjective"
    assert assessments["low_level_elegance"]["placeholder"] is True


def test_expire_provisional_manual_override_assessments_resets_scores():
    state = {
        "subjective_assessments": {
            "naming_quality": {
                "score": 98.0,
                "source": "manual_override",
                "provisional_override": True,
                "provisional_until_scan": 4,
                "components": ["foo"],
                "component_scores": {"foo": 98.0},
            },
            "logic_clarity": {
                "score": 80.0,
                "source": "holistic",
            },
        }
    }

    expired = _expire_provisional_manual_override_assessments(state)

    assert expired == 1
    naming = state["subjective_assessments"]["naming_quality"]
    assert naming["score"] == 0.0
    assert naming["source"] == "manual_override_expired"
    assert naming["reset_by"] == "manual_override_expired"
    assert naming["placeholder"] is True
    assert "provisional_override" not in naming
    assert "provisional_until_scan" not in naming
    assert "components" not in naming
    assert "component_scores" not in naming
    assert state["subjective_assessments"]["logic_clarity"]["score"] == 80.0


def test_expire_provisional_manual_override_assessments_noop_when_absent():
    state = {
        "subjective_assessments": {
            "naming_quality": {
                "score": 88.0,
                "source": "holistic",
            }
        }
    }

    expired = _expire_provisional_manual_override_assessments(state)

    assert expired == 0
    assert state["subjective_assessments"]["naming_quality"]["score"] == 88.0


def test_scan_reset_raises_when_subjective_assessments_not_object():
    state = {"subjective_assessments": []}
    try:
        _reset_subjective_assessments_for_scan_reset(state)
    except ScanStateContractError as exc:
        assert "subjective_assessments" in str(exc)
    else:
        raise AssertionError("expected ScanStateContractError")
