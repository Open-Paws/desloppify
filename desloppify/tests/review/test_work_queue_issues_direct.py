"""Direct coverage tests for state-backed work queue issue helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import desloppify.engine._work_queue.issues as issues_mod


def test_impact_label_thresholds_and_invalid_values() -> None:
    assert issues_mod.impact_label(8) == "+++"
    assert issues_mod.impact_label(5) == "++"
    assert issues_mod.impact_label(4.9) == "+"
    assert issues_mod.impact_label("not-a-number") == "+"


def test_list_open_review_issues_filters_and_sorts_by_weight(monkeypatch) -> None:
    monkeypatch.setattr(
        issues_mod,
        "issue_weight",
        lambda issue: (issue["weight"], "impact", issue["id"]),
    )
    state = {
        "issues": {
            "a": {"id": "review::a", "status": "open", "detector": "review", "weight": 2.0},
            "b": {"id": "review::b", "status": "fixed", "detector": "review", "weight": 99.0},
            "c": {"id": "review::c", "status": "open", "detector": "concerns", "weight": 50.0},
            "d": {"id": "review::d", "status": "open", "detector": "review", "weight": 7.0},
        }
    }

    listed = issues_mod.list_open_review_issues(state)

    assert [item["id"] for item in listed] == ["review::d", "review::a"]


def test_update_investigation_persists_detail_and_timestamp() -> None:
    state = {
        "issues": {
            "review::a": {
                "status": "open",
                "detector": "review",
                "detail": {"existing": "value"},
            }
        }
    }

    updated = issues_mod.update_investigation(state, "review::a", "looked into this")

    assert updated is True
    detail = state["work_items"]["review::a"]["detail"]
    assert detail["existing"] == "value"
    assert detail["investigation"] == "looked into this"
    datetime.fromisoformat(detail["investigated_at"])


def test_update_investigation_returns_false_for_missing_or_closed_issue() -> None:
    state = {"issues": {"review::closed": {"status": "fixed", "detector": "review"}}}

    assert issues_mod.update_investigation(state, "missing", "x") is False
    assert issues_mod.update_investigation(state, "review::closed", "x") is False


def test_mark_stale_holistic_marks_old_entries_stale_only() -> None:
    stale = (datetime.now(UTC) - timedelta(days=45)).isoformat()
    fresh = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    state = {
        "issues": {
            "review::stale": {
                "status": "open",
                "detector": "review",
                "detail": {"holistic": True},
                "last_seen": stale,
            },
            "review::fresh": {
                "status": "open",
                "detector": "review",
                "detail": {"holistic": True},
                "last_seen": fresh,
            },
            "review::bad-time": {
                "status": "open",
                "detector": "review",
                "detail": {"holistic": True},
                "last_seen": "not-an-iso-date",
            },
            "review::non-holistic": {
                "status": "open",
                "detector": "review",
                "detail": {"holistic": False},
                "last_seen": stale,
            },
        }
    }

    expired = issues_mod.mark_stale_holistic(state, max_age_days=30)

    assert expired == ["review::stale"]
    stale_issue = state["work_items"]["review::stale"]
    assert stale_issue["status"] == "open"
    assert stale_issue["note"].startswith("holistic review stale")
    assert state["work_items"]["review::fresh"]["status"] == "open"
    assert state["work_items"]["review::bad-time"]["status"] == "open"
