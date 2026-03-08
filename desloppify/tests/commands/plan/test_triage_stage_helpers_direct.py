"""Direct coverage tests for triage stage helper utilities."""

from __future__ import annotations

import desloppify.app.commands.plan.triage.stage_helpers as stage_helpers_mod


def test_require_triage_pending_true_when_stage_present(capsys) -> None:
    plan = {"queue_order": ["triage::observe", "review::a"]}
    assert stage_helpers_mod._require_triage_pending(plan, action="run") is True
    assert capsys.readouterr().out == ""


def test_require_triage_pending_false_prints_guidance(capsys) -> None:
    plan = {"queue_order": ["review::a"]}
    assert stage_helpers_mod._require_triage_pending(plan, action="run") is False
    assert "No triage stage in the queue" in capsys.readouterr().out


def test_validate_stage_report_rejects_missing_report(capsys) -> None:
    result = stage_helpers_mod._validate_stage_report(
        None,
        stage="observe",
        min_chars=20,
        missing_guidance=["Provide concrete patterns."],
    )
    assert result is None
    out = capsys.readouterr().out
    assert "--report is required" in out
    assert "Provide concrete patterns." in out


def test_validate_stage_report_rejects_short_report(capsys) -> None:
    result = stage_helpers_mod._validate_stage_report(
        "  too short  ",
        stage="observe",
        min_chars=20,
        short_guidance=["Expand with evidence."],
    )
    assert result is None
    out = capsys.readouterr().out
    assert "Report too short" in out
    assert "Expand with evidence." in out


def test_validate_stage_report_accepts_and_strips_valid_report() -> None:
    result = stage_helpers_mod._validate_stage_report(
        "  this report is definitely long enough  ",
        stage="observe",
        min_chars=20,
    )
    assert result == "this report is definitely long enough"


def test_triage_coverage_delegates_to_primary_helper(monkeypatch) -> None:
    plan = {"queue_order": []}

    def fake_coverage(_plan):
        assert _plan is plan
        return (2, 5, {"cluster-a": {"issue_ids": ["review::x"]}})

    monkeypatch.setattr(stage_helpers_mod, "_triage_coverage_helper", fake_coverage)
    assert stage_helpers_mod.triage_coverage(plan) == (
        2,
        5,
        {"cluster-a": {"issue_ids": ["review::x"]}},
    )


def test_unenriched_clusters_flags_missing_requirements() -> None:
    plan = {
        "clusters": {
            "auto_cluster": {
                "auto": True,
                "issue_ids": ["review::auto"],
                "description": "ignored",
                "action_steps": ["ignored"],
            },
            "empty_cluster": {
                "auto": False,
                "issue_ids": [],
            },
            "needs_everything": {
                "auto": False,
                "issue_ids": ["review::a", "review::b"],
            },
            "small_needs_more_steps": {
                "auto": False,
                "issue_ids": ["review::c", "review::d", "review::e"],
                "description": "ok",
                "action_steps": ["one", "two"],
            },
            "large_has_steps": {
                "auto": False,
                "issue_ids": ["r1", "r2", "r3", "r4", "r5"],
                "description": "ok",
                "action_steps": ["cluster-level step"],
            },
        }
    }

    gaps = dict(stage_helpers_mod.unenriched_clusters(plan))

    assert "auto_cluster" not in gaps
    assert "empty_cluster" not in gaps
    assert gaps["needs_everything"] == ["description", "action_steps"]
    assert gaps["small_needs_more_steps"] == [
        "action_steps (have 2, need >= 3 for small cluster)"
    ]
    assert "large_has_steps" not in gaps


def test_unclustered_review_issues_uses_state_when_provided() -> None:
    plan = {
        "clusters": {
            "manual": {"auto": False, "issue_ids": ["review::clustered"]},
            "auto": {"auto": True, "issue_ids": ["review::auto"]},
        }
    }
    state = {
        "issues": {
            "review::clustered": {"status": "open", "detector": "review"},
            "review::leftover": {"status": "open", "detector": "review"},
            "concerns::leftover": {"status": "open", "detector": "concerns"},
            "subjective_review::placeholder": {
                "status": "open",
                "detector": "subjective_review",
            },
            "review::closed": {"status": "closed", "detector": "review"},
        }
    }

    assert stage_helpers_mod.unclustered_review_issues(plan, state) == [
        "review::leftover",
        "concerns::leftover",
    ]


def test_unclustered_review_issues_falls_back_to_queue_scan() -> None:
    plan = {
        "queue_order": [
            "triage::observe",
            "workflow::score-checkpoint",
            "review::clustered",
            "review::leftover",
            "concerns::leftover",
            "structural::ignored",
        ],
        "clusters": {
            "manual": {"auto": False, "issue_ids": ["review::clustered"]}
        },
    }

    assert stage_helpers_mod.unclustered_review_issues(plan) == [
        "review::leftover",
        "concerns::leftover",
    ]
