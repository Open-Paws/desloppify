"""Tests that review issues are excluded from detection-side scoring."""

from __future__ import annotations

import pytest

from desloppify.engine._scoring.detection import (
    detector_pass_rate,
    detector_stats_by_mode,
)
from desloppify.engine._scoring.policy.core import SCORING_MODES
from desloppify.engine._scoring.results.core import compute_score_bundle


def _issue(
    detector: str,
    *,
    status: str = "open",
    confidence: str = "high",
    file: str = "a.py",
    zone: str = "production",
    detail: dict | None = None,
) -> dict:
    return {
        "detector": detector,
        "status": status,
        "confidence": confidence,
        "file": file,
        "zone": zone,
        "detail": detail or {},
    }


def _issues_dict(*issues: dict) -> dict:
    return {str(i): f for i, f in enumerate(issues)}


class TestReviewIssuesExcludedFromScoring:
    """Review issues must not contribute to detection-side scores."""

    def test_review_detector_returns_perfect_pass_rate(self):
        """detector_pass_rate('review', ...) always returns (1.0, 0, 0.0)."""
        f = _issue("review", confidence="high", file=".")
        f["detail"] = {"holistic": True}
        issues = _issues_dict(f)

        rate, issues, weighted = detector_pass_rate("review", issues, 60)
        assert rate == 1.0
        assert issues == 0
        assert weighted == 0.0

    def test_review_stats_by_mode_all_perfect(self):
        """All scoring modes return perfect scores for review detector."""
        f = _issue("review", confidence="high", file=".")
        f["detail"] = {"holistic": True}
        issues = _issues_dict(f)

        result = detector_stats_by_mode("review", issues, 60)
        for mode in SCORING_MODES:
            rate, issues, weighted = result[mode]
            assert rate == 1.0
            assert issues == 0
            assert weighted == 0.0

    def test_open_review_issues_do_not_affect_score_bundle(self):
        """Open review issues don't change objective/strict scores."""
        potentials = {"unused": 100, "review": 10}

        # No review issues
        baseline = compute_score_bundle({}, potentials)

        # Add open review issues
        review_f = _issue("review", confidence="high", file=".")
        review_f["detail"] = {"holistic": True, "dimension": "naming_quality"}
        result = compute_score_bundle(_issues_dict(review_f), potentials)

        # Scores should be identical — review issues don't affect scoring
        assert result.overall_score == baseline.overall_score
        assert result.strict_score == baseline.strict_score
        assert result.objective_score == baseline.objective_score

    def test_resolving_review_issue_does_not_change_scores(self):
        """Resolving a review issue results in identical scores."""
        review_open = _issue("review", status="open", confidence="high", file=".")
        review_open["detail"] = {"holistic": True, "dimension": "naming_quality"}
        potentials = {"unused": 100, "review": 10}

        open_result = compute_score_bundle(
            _issues_dict(review_open), potentials
        )

        review_fixed = _issue("review", status="fixed", confidence="high", file=".")
        review_fixed["detail"] = {"holistic": True, "dimension": "naming_quality"}

        fixed_result = compute_score_bundle(
            _issues_dict(review_fixed), potentials
        )

        assert open_result.overall_score == fixed_result.overall_score
        assert open_result.strict_score == fixed_result.strict_score

    def test_non_review_detectors_still_scored_normally(self):
        """Other detectors are unaffected by the review exclusion."""
        f = _issue("unused", confidence="high")
        issues = _issues_dict(f)

        rate, issues, weighted = detector_pass_rate("unused", issues, 100)
        assert issues == 1
        assert weighted == pytest.approx(1.0)
        assert rate < 1.0

    def test_stale_assessment_surfaces_in_scorecard_entries(self):
        """Stale subjective assessments are flagged in scorecard entries."""
        from desloppify.app.commands.scan.reporting.dimensions import (
            scorecard_dimension_entries,
        )

        state = {
            "potentials": {"python": {"unused": 10}},
            "dimension_scores": {
                "Naming quality": {
                    "score": 75.0,
                    "strict": 75.0,
                    "tier": 4,
                    "checks": 100,
                    "failing": 0,
                    "detectors": {
                        "subjective_assessment": {
                            "dimension_key": "naming_quality",
                            "placeholder": False,
                        }
                    },
                }
            },
            "subjective_assessments": {
                "naming_quality": {
                    "score": 75.0,
                    "needs_review_refresh": True,
                    "refresh_reason": "review_issue_fixed",
                }
            },
        }

        entries = scorecard_dimension_entries(state)
        naming = [e for e in entries if e["name"] == "Naming quality"]
        assert len(naming) == 1
        assert naming[0]["stale"] is True

    def test_fresh_assessment_not_marked_stale(self):
        """Non-stale subjective assessments have stale=False."""
        from desloppify.app.commands.scan.reporting.dimensions import (
            scorecard_dimension_entries,
        )

        state = {
            "potentials": {"python": {"unused": 10}},
            "dimension_scores": {
                "Naming quality": {
                    "score": 75.0,
                    "strict": 75.0,
                    "tier": 4,
                    "checks": 100,
                    "failing": 0,
                    "detectors": {
                        "subjective_assessment": {
                            "dimension_key": "naming_quality",
                            "placeholder": False,
                        }
                    },
                }
            },
            "subjective_assessments": {
                "naming_quality": {"score": 75.0}
            },
        }

        entries = scorecard_dimension_entries(state)
        naming = [e for e in entries if e["name"] == "Naming quality"]
        assert len(naming) == 1
        assert naming[0]["stale"] is False

    def test_assessment_scores_drive_subjective_dimensions(self):
        """Subjective assessment scores still affect overall score."""
        potentials = {"unused": 100}
        assessments = {"naming_quality": {"score": 60.0, "source": "holistic"}}

        result_low = compute_score_bundle(
            {}, potentials, subjective_assessments=assessments
        )

        assessments_high = {"naming_quality": {"score": 95.0, "source": "holistic"}}
        result_high = compute_score_bundle(
            {}, potentials, subjective_assessments=assessments_high
        )

        # Higher assessment → higher overall score
        assert result_high.overall_score > result_low.overall_score
