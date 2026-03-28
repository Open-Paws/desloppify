"""Unit tests for plan commit-tracking helpers."""

from __future__ import annotations

import desloppify.engine._plan.commit_tracking as commit_tracking_mod


def test_record_commit_moves_uncommitted_items_into_log() -> None:
    plan = {"uncommitted_issues": ["issue::a", "issue::b"], "commit_log": []}

    record = commit_tracking_mod.record_commit(
        plan,
        sha="abcdef123456",
        branch="main",
        note="batch",
    )

    assert record["sha"] == "abcdef123456"
    assert record["issue_ids"] == ["issue::a", "issue::b"]
    assert plan["uncommitted_issues"] == []
    assert len(plan["commit_log"]) == 1


def test_commit_tracking_summary_counts_committed_and_uncommitted() -> None:
    plan = {
        "uncommitted_issues": ["issue::x"],
        "commit_log": [
            {"issue_ids": ["issue::a", "issue::b"]},
            {"issue_ids": ["issue::c"]},
        ],
    }

    summary = commit_tracking_mod.commit_tracking_summary(plan)
    assert summary == {"uncommitted": 1, "committed": 3, "total": 4}


def test_filter_issue_ids_by_pattern_uses_glob_matching() -> None:
    issue_ids = [
        "smells::src/a.py::x",
        "large::src/b.py::y",
        "smells::src/c.py::z",
    ]

    filtered = commit_tracking_mod.filter_issue_ids_by_pattern(
        issue_ids,
        ["smells::*", "*b.py*"],
    )

    assert filtered == issue_ids


def test_generate_pr_body_includes_score_delta(monkeypatch) -> None:
    from desloppify.engine._scoring.results import core as scoring_core

    monkeypatch.setattr(
        scoring_core,
        "compute_health_score",
        lambda _dim, score_key="strict": 95.0,
    )
    plan = {
        "commit_log": [
            {
                "sha": "abcdef123456",
                "issue_ids": ["issue::a"],
                "note": "cleanup",
                "recorded_at": "2026-03-03T10:00:00+00:00",
            }
        ],
        "plan_start_scores": {"strict": 90.0},
    }
    state = {
        "issues": {"issue::a": {"summary": "Remove dead code"}},
        "dimension_scores": {"code_quality": {"strict": 95.0}},
    }

    body = commit_tracking_mod.generate_pr_body(plan, state)
    assert "Code Health Improvements" in body
    assert "Score: 90.0 → 95.0 strict (+5.0)" in body
    assert "Remove dead code" in body

