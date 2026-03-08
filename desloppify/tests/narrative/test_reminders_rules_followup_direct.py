"""Direct coverage tests for follow-up reminder rule helpers."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime as _dt
from datetime import timedelta

import desloppify.intelligence.narrative.reminders_rules_followup as followup_mod


def test_review_queue_reminders_includes_pending_rereview_and_review_not_run() -> None:
    state = {
        "subjective_assessments": {"naming": {"score": 70}},
        "review_cache": {},
    }
    scoped_issues = {
        "a": {"status": "open", "detector": "review", "detail": {}},
        "b": {
            "status": "open",
            "detector": "review",
            "detail": {"investigation": "done"},
        },
    }

    reminders = followup_mod._review_queue_reminders(
        state,
        scoped_issues,
        command="resolve",
        strict_score=82.0,
    )

    types = {r["type"] for r in reminders}
    assert {"review_issues_pending", "rereview_needed", "review_not_run"} <= types


def test_stale_assessment_reminder_requires_no_open_issues() -> None:
    state_with_open = {
        "issues": {"i": {"status": "open", "suppressed": False}},
        "subjective_assessments": {
            "naming": {"needs_review_refresh": True},
        },
    }
    assert followup_mod._stale_assessment_reminder(state_with_open) == []

    state_closed = {
        "issues": {"i": {"status": "fixed", "suppressed": False}},
        "subjective_assessments": {
            "naming": {"needs_review_refresh": True},
            "error_handling": {"needs_review_refresh": True},
        },
    }
    reminders = followup_mod._stale_assessment_reminder(state_closed)
    assert reminders and reminders[0]["type"] == "stale_assessments"
    assert "naming,error_handling" in reminders[0]["command"]


def test_review_staleness_reminder_handles_old_and_invalid_timestamps(monkeypatch) -> None:
    old = (_dt.now(UTC) - timedelta(days=45)).isoformat()
    state = {
        "review_cache": {
            "files": {
                "a.py": {"reviewed_at": old},
            }
        }
    }

    reminders = followup_mod._review_staleness_reminder(state, {"review_max_age_days": 30})
    assert reminders and reminders[0]["type"] == "review_stale"

    called = {"count": 0}

    def _mark(*_args, **_kwargs) -> None:
        called["count"] += 1

    monkeypatch.setattr(followup_mod, "log_best_effort_failure", _mark)
    bad_state = {
        "review_cache": {
            "files": {
                "a.py": {"reviewed_at": "not-a-date"},
            }
        }
    }
    assert followup_mod._review_staleness_reminder(bad_state, {"review_max_age_days": 1}) == []
    assert called["count"] == 1


def test_feedback_reminder_branches(monkeypatch) -> None:
    monkeypatch.setattr(followup_mod, "_feedback_base_url", lambda: "https://example.invalid")

    assert followup_mod._feedback_reminder({}, "normal", "scan", {}) == []

    state = {"scan_history": [1, 2]}
    high_fp = followup_mod._feedback_reminder(
        state,
        phase="normal",
        command="scan",
        fp_rates={("smells", "core"): 0.5},
    )
    assert "smells" in high_fp[0]["message"]

    stagnant = followup_mod._feedback_reminder(
        state,
        phase="stagnation",
        command="scan",
        fp_rates={},
    )
    assert "plateaued" in stagnant[0]["message"]

    generic = followup_mod._feedback_reminder(
        state,
        phase="normal",
        command="scan",
        fp_rates={},
    )
    assert "doesn't detect" in generic[0]["message"]


def test_metadata_report_and_decay_helpers() -> None:
    decorated = followup_mod._decorate_reminder_metadata(
        [
            {"type": "unknown_type", "message": "u"},
            {"type": "fp_calibration_smells", "message": "f"},
            {"type": "review_not_run", "message": "r", "priority": 9},
        ]
    )
    assert [r["type"] for r in decorated] == [
        "fp_calibration_smells",
        "unknown_type",
        "review_not_run",
    ]
    assert decorated[0]["severity"] == "medium"
    assert decorated[2]["priority"] == 9

    report = followup_mod._report_scores_reminder("scan")
    assert report and report[0]["type"] == "report_scores"
    assert report[0]["no_decay"] is True
    assert followup_mod._report_scores_reminder("resolve") == []

    filtered, updated = followup_mod._apply_decay(
        [
            {"type": "feedback_nudge", "message": "a"},
            {"type": "review_not_run", "message": "b"},
            {"type": "report_scores", "message": "c", "no_decay": True},
        ],
        {"feedback_nudge": 3, "review_not_run": 2},
    )
    assert [r["type"] for r in filtered] == ["review_not_run", "report_scores"]
    assert updated["review_not_run"] == 3
    assert updated["report_scores"] == 1
