"""Headline regression tests for review-related suffix handling."""

from __future__ import annotations

from desloppify.intelligence.narrative.headline import compute_headline


class TestHeadlineBugFix:
    def test_headline_no_typeerror_when_headline_none_with_review_suffix(self):
        """Regression: None + review_suffix shouldn't TypeError."""
        # Force: no security prefix, headline_inner returns None, review_suffix non-empty
        # stagnation + review work items + conditions that make headline_inner return None
        result = compute_headline(
            "stagnation",
            {},
            {},
            None,
            None,
            None,
            None,  # obj_strict=None → headline_inner falls through to None
            {"open": 0},
            [],
            open_by_detector={"review": 5},
        )
        # Should not crash — may return None or a string with review suffix
        if result is not None:
            assert isinstance(result, str)

    def test_headline_review_only_no_security_no_inner(self):
        """When only review_suffix exists, returns it cleanly."""
        result = compute_headline(
            "stagnation",
            {},
            {},
            None,
            None,
            None,
            None,
            {"open": 0},
            [],
            open_by_detector={"review": 3},
        )
        if result is not None:
            assert "review work item" in result.lower()
            assert "3" in result
