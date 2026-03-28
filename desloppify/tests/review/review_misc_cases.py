"""Tests for the subjective code review system (review.py, commands/review/cmd.py)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from desloppify.intelligence.narrative.headline import compute_headline
from desloppify.intelligence.narrative.reminders import compute_reminders
from desloppify.intelligence.review.selection import (
    count_fresh,
    count_stale,
)


class TestStaleness:
    def test_stale_after_max_age(self):
        old = (datetime.now(UTC) - timedelta(days=60)).isoformat(
            timespec="seconds"
        )
        state = {
            "review_cache": {
                "files": {
                    "foo.ts": {
                        "content_hash": "abc",
                        "reviewed_at": old,
                        "issue_count": 0,
                    },
                }
            }
        }
        assert count_stale(state, 30) == 1
        assert count_fresh(state, 30) == 0

    def test_fresh_within_max_age(self):
        now = datetime.now(UTC).isoformat(timespec="seconds")
        state = {
            "review_cache": {
                "files": {
                    "foo.ts": {
                        "content_hash": "abc",
                        "reviewed_at": now,
                        "issue_count": 0,
                    },
                }
            }
        }
        assert count_stale(state, 30) == 0
        assert count_fresh(state, 30) == 1

    def test_mixed_fresh_and_stale(self):
        now = datetime.now(UTC).isoformat(timespec="seconds")
        old = (datetime.now(UTC) - timedelta(days=60)).isoformat(
            timespec="seconds"
        )
        state = {
            "review_cache": {
                "files": {
                    "fresh.ts": {
                        "content_hash": "abc",
                        "reviewed_at": now,
                        "issue_count": 0,
                    },
                    "stale.ts": {
                        "content_hash": "def",
                        "reviewed_at": old,
                        "issue_count": 1,
                    },
                }
            }
        }
        assert count_fresh(state, 30) == 1
        assert count_stale(state, 30) == 1


# ── Narrative integration tests ───────────────────────────────────


class TestNarrativeIntegration:
    def test_review_staleness_reminder(self):
        old = (datetime.now(UTC) - timedelta(days=60)).isoformat(
            timespec="seconds"
        )
        state = {
            "review_cache": {
                "files": {
                    "foo.ts": {
                        "content_hash": "abc",
                        "reviewed_at": old,
                        "issue_count": 0,
                    },
                }
            },
            "issues": {},
            "reminder_history": {},
            "strict_score": 80.0,
        }
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            debt={},
            actions=[],
            dimensions={},
            badge={},
            command="scan",
        )
        types = [r["type"] for r in reminders]
        assert "review_stale" in types

    def test_no_reminder_when_fresh(self):
        now = datetime.now(UTC).isoformat(timespec="seconds")
        state = {
            "review_cache": {
                "files": {
                    "foo.ts": {
                        "content_hash": "abc",
                        "reviewed_at": now,
                        "issue_count": 0,
                    },
                }
            },
            "issues": {},
            "reminder_history": {},
        }
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            debt={},
            actions=[],
            dimensions={},
            badge={},
            command="scan",
        )
        types = [r["type"] for r in reminders]
        assert "review_stale" not in types

    def test_no_reminder_when_no_cache(self):
        state = {"issues": {}, "reminder_history": {}}
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            debt={},
            actions=[],
            dimensions={},
            badge={},
            command="scan",
        )
        types = [r["type"] for r in reminders]
        assert "review_stale" not in types

    def test_review_not_run_reminder_when_score_high(self):
        """When score >= 80 and no review cache, suggest running review (#55)."""
        state = {
            "issues": {},
            "reminder_history": {},
            "strict_score": 85.0,
        }
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            debt={},
            actions=[],
            dimensions={},
            badge={},
            command="scan",
        )
        types = [r["type"] for r in reminders]
        assert "review_not_run" in types
        review_reminder = [r for r in reminders if r["type"] == "review_not_run"][0]
        assert "desloppify review --prepare" in review_reminder["message"]

    def test_review_not_run_no_reminder_when_score_low(self):
        """No review nudge when score is below 80 (#55)."""
        state = {
            "issues": {},
            "reminder_history": {},
            "strict_score": 60.0,
        }
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            debt={},
            actions=[],
            dimensions={},
            badge={},
            command="scan",
        )
        types = [r["type"] for r in reminders]
        assert "review_not_run" not in types

    def test_review_not_run_no_reminder_when_already_reviewed(self):
        """No review_not_run when review cache has files (#55)."""
        now = datetime.now(UTC).isoformat(timespec="seconds")
        state = {
            "review_cache": {
                "files": {
                    "foo.ts": {
                        "content_hash": "abc",
                        "reviewed_at": now,
                        "issue_count": 0,
                    },
                }
            },
            "issues": {},
            "reminder_history": {},
            "strict_score": 95.0,
        }
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            debt={},
            actions=[],
            dimensions={},
            badge={},
            command="scan",
        )
        types = [r["type"] for r in reminders]
        assert "review_not_run" not in types

    def test_headline_includes_review_in_maintenance(self):
        headline = compute_headline(
            "maintenance",
            {},
            {},
            None,
            None,
            95.0,
            96.0,
            {"open": 3},
            [],
            open_by_detector={"review": 3},
        )
        assert headline is not None
        assert "review work item" in headline.lower()

    def test_headline_no_review_in_early_momentum(self):
        headline = compute_headline(
            "early_momentum",
            {},
            {},
            None,
            None,
            75.0,
            78.0,
            {"open": 10},
            [],
            open_by_detector={"review": 2},
        )
        # review suffix only in maintenance/stagnation
        if headline:
            assert "design review" not in headline.lower()
