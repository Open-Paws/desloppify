"""Tests for desloppify.intelligence.narrative — pure narrative computation functions."""

from __future__ import annotations

from desloppify.intelligence.narrative._constants import _FEEDBACK_URL, STRUCTURAL_MERGE
from desloppify.intelligence.narrative.core import (
    _count_open_by_detector,
)
from desloppify.intelligence.narrative.dimensions import _analyze_debt
from desloppify.intelligence.narrative.phase import detect_milestone, detect_phase
from desloppify.intelligence.narrative.reminders import compute_reminders

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _issue(
    detector: str,
    *,
    status: str = "open",
    confidence: str = "high",
    file: str = "a.py",
    zone: str = "production",
) -> dict:
    """Build a minimal issue dict."""
    return {
        "detector": detector,
        "status": status,
        "confidence": confidence,
        "file": file,
        "zone": zone,
    }


def _issues_dict(*issues: dict) -> dict:
    """Wrap a list of issue dicts into an id-keyed dict."""
    return {str(i): f for i, f in enumerate(issues)}


def _history_entry(
    strict_score: float | None = None,
    objective_score: float | None = None,
    lang: str | None = None,
    dimension_scores: dict | None = None,
) -> dict:
    entry: dict = {}
    if strict_score is not None:
        entry["strict_score"] = strict_score
    if objective_score is not None:
        entry["objective_score"] = objective_score
        entry["overall_score"] = objective_score
    if lang is not None:
        entry["lang"] = lang
    if dimension_scores is not None:
        entry["dimension_scores"] = dimension_scores
    return entry


# ===================================================================
# _count_open_by_detector
# ===================================================================


class TestCountOpenByDetector:
    def test_empty_issues(self):
        assert _count_open_by_detector({}) == {}

    def test_only_open_counted(self):
        issues = _issues_dict(
            _issue("unused", status="open"),
            _issue("unused", status="resolved"),
            _issue("unused", status="wontfix"),
            _issue("unused", status="false_positive"),
        )
        result = _count_open_by_detector(issues)
        assert result == {"unused": 1}

    def test_multiple_detectors(self):
        issues = _issues_dict(
            _issue("unused", status="open"),
            _issue("unused", status="open"),
            _issue("logs", status="open"),
            _issue("smells", status="open"),
        )
        result = _count_open_by_detector(issues)
        assert result == {"unused": 2, "logs": 1, "smells": 1}

    def test_structural_merge_large(self):
        issues = _issues_dict(
            _issue("large", status="open"),
        )
        result = _count_open_by_detector(issues)
        assert result == {"structural": 1}

    def test_structural_merge_complexity(self):
        issues = _issues_dict(
            _issue("complexity", status="open"),
        )
        result = _count_open_by_detector(issues)
        assert result == {"structural": 1}

    def test_structural_merge_gods(self):
        issues = _issues_dict(
            _issue("gods", status="open"),
        )
        result = _count_open_by_detector(issues)
        assert result == {"structural": 1}

    def test_structural_merge_concerns(self):
        issues = _issues_dict(
            _issue("concerns", status="open"),
        )
        result = _count_open_by_detector(issues)
        assert result == {"structural": 1}

    def test_structural_merge_combines_all_subdetectors(self):
        """All four structural sub-detectors merge into a single count."""
        issues = _issues_dict(
            _issue("large", status="open"),
            _issue("complexity", status="open"),
            _issue("gods", status="open"),
            _issue("concerns", status="open"),
        )
        result = _count_open_by_detector(issues)
        assert result == {"structural": 4}

    def test_structural_merge_set_matches_constant(self):
        assert STRUCTURAL_MERGE == {"large", "complexity", "gods", "concerns"}

    def test_non_structural_not_merged(self):
        """Detectors not in STRUCTURAL_MERGE stay separate."""
        issues = _issues_dict(
            _issue("unused", status="open"),
            _issue("large", status="open"),
        )
        result = _count_open_by_detector(issues)
        assert result == {"unused": 1, "structural": 1}

    def test_missing_detector_key(self):
        issues = {"0": {"status": "open"}}
        result = _count_open_by_detector(issues)
        assert result == {"unknown": 1}

    def test_suppressed_issues_excluded(self):
        issues = _issues_dict(
            _issue("security", status="open"),
            {**_issue("security", status="open"), "suppressed": True},
            {**_issue("security", status="open"), "suppressed": True},
            _issue("unused", status="open"),
            {**_issue("unused", status="open"), "suppressed": True},
        )
        result = _count_open_by_detector(issues)
        assert result == {"security": 1, "unused": 1}

    def test_suppressed_review_uninvestigated_excluded(self):
        issues = {
            "a": {"status": "open", "detector": "review", "detail": {}},
            "b": {"status": "open", "detector": "review", "detail": {},
                   "suppressed": True},
        }
        result = _count_open_by_detector(issues)
        assert result["review"] == 1
        assert result["review_uninvestigated"] == 1


# ===================================================================
# detect_phase
# ===================================================================


class TestDetectPhase:
    def test_empty_history(self):
        assert detect_phase([], None) == "first_scan"

    def test_single_entry_history(self):
        history = [_history_entry(strict_score=50.0)]
        assert detect_phase(history, 50.0) == "first_scan"

    def test_regression_strict_dropped(self):
        """Strict dropped > 0.5 from previous scan."""
        history = [
            _history_entry(strict_score=80.0),
            _history_entry(strict_score=79.0),
        ]
        assert detect_phase(history, 79.0) == "regression"

    def test_regression_exact_half_point_no_regression(self):
        """Dropping exactly 0.5 is NOT regression (must exceed 0.5)."""
        history = [
            _history_entry(strict_score=80.0),
            _history_entry(strict_score=79.5),
        ]
        assert detect_phase(history, 79.5) != "regression"

    def test_stagnation_three_scans_unchanged(self):
        """Strict unchanged (spread <= 0.5) for 3+ scans."""
        history = [
            _history_entry(strict_score=75.0),
            _history_entry(strict_score=75.2),
            _history_entry(strict_score=75.3),
        ]
        assert detect_phase(history, 75.3) == "stagnation"

    def test_stagnation_requires_three_scans(self):
        """Only two scans with same score is not stagnation."""
        history = [
            _history_entry(strict_score=75.0),
            _history_entry(strict_score=75.0),
        ]
        # Two scans, same score but len(history) < 3 so no stagnation
        # This should trigger early_momentum check (len 2, and first==last)
        # Since first == last (not last > first), it won't be early_momentum
        # Falls through to score thresholds
        assert detect_phase(history, 75.0) != "stagnation"

    def test_early_momentum_scans_2_to_5_rising(self):
        """Scans 2-5, score rising from first to last."""
        history = [
            _history_entry(strict_score=60.0),
            _history_entry(strict_score=70.0),
        ]
        assert detect_phase(history, 70.0) == "early_momentum"

    def test_early_momentum_at_five_scans(self):
        history = [
            _history_entry(strict_score=50.0),
            _history_entry(strict_score=55.0),
            _history_entry(strict_score=60.0),
            _history_entry(strict_score=65.0),
            _history_entry(strict_score=70.0),
        ]
        assert detect_phase(history, 70.0) == "early_momentum"

    def test_early_momentum_not_at_six_scans(self):
        """More than 5 scans should not be early_momentum."""
        history = [
            _history_entry(strict_score=50.0),
            _history_entry(strict_score=55.0),
            _history_entry(strict_score=60.0),
            _history_entry(strict_score=65.0),
            _history_entry(strict_score=70.0),
            _history_entry(strict_score=75.0),
        ]
        # len=6, not in 2-5 range, falls through
        result = detect_phase(history, 75.0)
        assert result != "early_momentum"

    def test_declining_trajectory_not_early_momentum(self):
        """Score declining from first scan should NOT return early_momentum."""
        history = [
            _history_entry(strict_score=80.0),
            _history_entry(strict_score=75.0),
        ]
        # last (75) < first (80), so not early_momentum
        # Also triggers regression (80 - 75 = 5 > 0.5)
        result = detect_phase(history, 75.0)
        assert result != "early_momentum"
        assert result == "regression"

    def test_flat_trajectory_not_early_momentum(self):
        """Score equal from first scan should NOT return early_momentum."""
        history = [
            _history_entry(strict_score=70.0),
            _history_entry(strict_score=70.0),
        ]
        # last == first, not >
        result = detect_phase(history, 70.0)
        assert result != "early_momentum"

    def test_maintenance_above_93(self):
        """Score > 93 triggers maintenance phase."""
        history = [
            _history_entry(strict_score=85.0),
            _history_entry(strict_score=88.0),
            _history_entry(strict_score=90.0),
            _history_entry(strict_score=92.0),
            _history_entry(strict_score=93.5),
            _history_entry(strict_score=94.0),
        ]
        assert detect_phase(history, 94.0) == "maintenance"

    def test_refinement_above_80(self):
        """Score > 80 but <= 93 triggers refinement."""
        history = [
            _history_entry(strict_score=70.0),
            _history_entry(strict_score=75.0),
            _history_entry(strict_score=78.0),
            _history_entry(strict_score=81.0),
            _history_entry(strict_score=82.0),
            _history_entry(strict_score=85.0),
        ]
        assert detect_phase(history, 85.0) == "refinement"

    def test_middle_grind_below_80(self):
        """Score <= 80 with > 5 scans, no regression/stagnation."""
        history = [
            _history_entry(strict_score=40.0),
            _history_entry(strict_score=45.0),
            _history_entry(strict_score=50.0),
            _history_entry(strict_score=55.0),
            _history_entry(strict_score=60.0),
            _history_entry(strict_score=65.0),
        ]
        assert detect_phase(history, 65.0) == "middle_grind"

    def test_regression_takes_priority_over_stagnation(self):
        """Regression is checked before stagnation."""
        # Last 3 scans: 80, 80, 79 — stagnation spread 1.0 > 0.5 so not stagnant
        # But prev=80, curr=79 — drop is 1 > 0.5, so regression
        history = [
            _history_entry(strict_score=80.0),
            _history_entry(strict_score=80.0),
            _history_entry(strict_score=79.0),
        ]
        assert detect_phase(history, 79.0) == "regression"

    def test_stagnation_takes_priority_over_early_momentum(self):
        """Stagnation is checked before early_momentum for short histories."""
        history = [
            _history_entry(strict_score=70.0),
            _history_entry(strict_score=70.0),
            _history_entry(strict_score=70.0),
        ]
        assert detect_phase(history, 70.0) == "stagnation"

    def test_obj_strict_none_uses_last_history(self):
        """When obj_strict is None, fallback to history[-1].strict_score."""
        history = [
            _history_entry(strict_score=50.0),
            _history_entry(strict_score=55.0),
            _history_entry(strict_score=60.0),
            _history_entry(strict_score=65.0),
            _history_entry(strict_score=70.0),
            _history_entry(strict_score=75.0),
        ]
        # obj_strict None -> uses history[-1] = 75.0 -> refinement (> 80 would be, but 75 is not)
        # 75 <= 80 -> middle_grind
        result = detect_phase(history, None)
        assert result == "middle_grind"

    def test_regression_with_none_strict_values(self):
        """If prev or curr strict is None, regression check is skipped."""
        history = [
            _history_entry(),  # no strict_score
            _history_entry(strict_score=70.0),
        ]
        result = detect_phase(history, 70.0)
        # No prev strict to compare, regression check skipped
        # len=2, first has no strict -> early_momentum check: first is None -> skip
        # strict=70 -> not > 93, not > 80 -> middle_grind
        assert result == "middle_grind"


# ===================================================================
# detect_milestone
# ===================================================================


class TestDetectMilestone:
    def test_crossed_90_strict(self):
        state = {"strict_score": 91.0, "stats": {"by_tier": {}}}
        history = [
            _history_entry(strict_score=89.0),
            _history_entry(strict_score=91.0),
        ]
        result = detect_milestone(state, None, history)
        assert result == "Crossed 90% strict!"

    def test_crossed_80_strict(self):
        state = {"strict_score": 82.0, "stats": {"by_tier": {}}}
        history = [
            _history_entry(strict_score=78.0),
            _history_entry(strict_score=82.0),
        ]
        result = detect_milestone(state, None, history)
        assert result == "Crossed 80% strict!"

    def test_crossed_90_takes_priority_over_80(self):
        """If somehow both thresholds are crossed simultaneously, 90 wins."""
        state = {"strict_score": 91.0, "stats": {"by_tier": {}}}
        history = [
            _history_entry(strict_score=79.0),
            _history_entry(strict_score=91.0),
        ]
        result = detect_milestone(state, None, history)
        assert result == "Crossed 90% strict!"

    def test_already_above_90_no_milestone(self):
        """If already above 90, no crossing milestone."""
        state = {"strict_score": 95.0, "stats": {"by_tier": {}}}
        history = [
            _history_entry(strict_score=92.0),
            _history_entry(strict_score=95.0),
        ]
        result = detect_milestone(state, None, history)
        assert result is None

    def test_all_t1_t2_cleared(self):
        state = {
            "strict_score": 70.0,
            "stats": {
                "by_tier": {
                    "1": {"open": 0, "resolved": 5},
                    "2": {"open": 0, "resolved": 3},
                },
            },
        }
        history = [_history_entry(strict_score=70.0)]
        result = detect_milestone(state, None, history)
        assert result == "All T1 and T2 items cleared!"

    def test_all_t1_cleared_with_t2_remaining(self):
        state = {
            "strict_score": 70.0,
            "stats": {
                "by_tier": {
                    "1": {"open": 0, "resolved": 5},
                    "2": {"open": 2, "resolved": 1},
                },
            },
        }
        history = [_history_entry(strict_score=70.0)]
        result = detect_milestone(state, None, history)
        assert result == "All T1 items cleared!"

    def test_t1_still_open_no_milestone(self):
        state = {
            "strict_score": 70.0,
            "stats": {
                "by_tier": {
                    "1": {"open": 3, "resolved": 2},
                    "2": {"open": 1, "resolved": 0},
                },
            },
        }
        history = [_history_entry(strict_score=70.0)]
        result = detect_milestone(state, None, history)
        assert result is None

    def test_zero_open_issues(self):
        state = {
            "strict_score": 100.0,
            "stats": {
                "open": 0,
                "total": 10,
                "by_tier": {},
            },
        }
        history = [_history_entry(strict_score=100.0)]
        result = detect_milestone(state, None, history)
        assert result == "Zero open issues!"

    def test_zero_total_issues_no_milestone(self):
        """Zero open AND zero total means nothing was ever found -- no celebration."""
        state = {
            "strict_score": 100.0,
            "stats": {
                "open": 0,
                "total": 0,
                "by_tier": {},
            },
        }
        history = [_history_entry(strict_score=100.0)]
        result = detect_milestone(state, None, history)
        assert result is None

    def test_no_milestone_ordinary_case(self):
        state = {
            "strict_score": 70.0,
            "stats": {
                "open": 15,
                "total": 50,
                "by_tier": {
                    "1": {"open": 2},
                    "2": {"open": 3},
                },
            },
        }
        history = [_history_entry(strict_score=70.0)]
        result = detect_milestone(state, None, history)
        assert result is None

    def test_threshold_milestones_require_two_history_entries(self):
        """Single history entry cannot trigger 90/80 crossing."""
        state = {"strict_score": 95.0, "stats": {"by_tier": {}}}
        history = [_history_entry(strict_score=95.0)]
        result = detect_milestone(state, None, history)
        assert result is None

    def test_t1_t2_cleared_requires_prior_items(self):
        """If there were never T1/T2 items, no clearing milestone."""
        state = {
            "strict_score": 70.0,
            "stats": {
                "by_tier": {
                    "1": {"open": 0},  # totals sum to 0
                    "2": {"open": 0},
                },
            },
        }
        history = [_history_entry(strict_score=70.0)]
        result = detect_milestone(state, None, history)
        assert result is None


# ===================================================================
# _analyze_debt
# ===================================================================


class TestAnalyzeDebt:
    def test_empty_inputs(self):
        result = _analyze_debt({}, {}, [])
        assert result["overall_gap"] == 0.0
        assert result["wontfix_count"] == 0
        assert result["worst_dimension"] is None
        assert result["worst_gap"] == 0.0
        assert result["trend"] == "stable"

    def test_wontfix_count(self):
        issues = _issues_dict(
            _issue("unused", status="wontfix"),
            _issue("unused", status="wontfix"),
            _issue("logs", status="open"),
            _issue("smells", status="resolved"),
        )
        result = _analyze_debt({}, issues, [])
        assert result["wontfix_count"] == 2

    def test_worst_dimension_gap(self):
        dim_scores = {
            "Import hygiene": {"score": 90.0, "strict": 85.0, "tier": 1},
            "Debug cleanliness": {"score": 95.0, "strict": 80.0, "tier": 2},
        }
        result = _analyze_debt(dim_scores, {}, [])
        assert result["worst_dimension"] == "Debug cleanliness"
        assert result["worst_gap"] == 15.0

    def test_overall_gap_weighted(self):
        """Overall gap is tier-weighted average of (lenient - strict)."""
        dim_scores = {
            "Import hygiene": {"score": 90.0, "strict": 80.0, "tier": 1},
        }
        result = _analyze_debt(dim_scores, {}, [])
        # lenient=90, strict=80, gap=10
        assert result["overall_gap"] == 10.0

    def test_trend_growing(self):
        """Gap increased over history -> growing."""
        history = [
            _history_entry(strict_score=80.0, objective_score=82.0),
            _history_entry(strict_score=78.0, objective_score=84.0),
            _history_entry(strict_score=75.0, objective_score=85.0),
        ]
        # gaps: 2.0, 6.0, 10.0 -- last (10) > first (2) + 0.5 -> growing
        result = _analyze_debt({}, {}, history)
        assert result["trend"] == "growing"

    def test_trend_shrinking(self):
        """Gap decreased over history -> shrinking."""
        history = [
            _history_entry(strict_score=70.0, objective_score=80.0),
            _history_entry(strict_score=75.0, objective_score=80.0),
            _history_entry(strict_score=79.0, objective_score=80.0),
        ]
        # gaps: 10.0, 5.0, 1.0 -- last (1) < first (10) - 0.5 -> shrinking
        result = _analyze_debt({}, {}, history)
        assert result["trend"] == "shrinking"

    def test_trend_stable(self):
        """Gap unchanged -> stable."""
        history = [
            _history_entry(strict_score=75.0, objective_score=80.0),
            _history_entry(strict_score=75.0, objective_score=80.0),
            _history_entry(strict_score=75.0, objective_score=80.0),
        ]
        # gaps: 5.0, 5.0, 5.0 -- last == first -> stable
        result = _analyze_debt({}, {}, history)
        assert result["trend"] == "stable"

    def test_trend_requires_three_scans(self):
        """Fewer than 3 scans -> stable (no trend)."""
        history = [
            _history_entry(strict_score=70.0, objective_score=80.0),
            _history_entry(strict_score=60.0, objective_score=85.0),
        ]
        result = _analyze_debt({}, {}, history)
        assert result["trend"] == "stable"

    def test_no_gap_when_strict_equals_lenient(self):
        dim_scores = {
            "Import hygiene": {"score": 90.0, "strict": 90.0, "tier": 1},
        }
        result = _analyze_debt(dim_scores, {}, [])
        assert result["overall_gap"] == 0.0
        assert result["worst_dimension"] is None
        assert result["worst_gap"] == 0.0


# ===================================================================
# compute_reminders
# ===================================================================


class TestComputeReminders:
    def test_returns_tuple(self):
        """Must return (list, dict) tuple."""
        state = {"strict_score": 50.0}
        result = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            {},
            [],
            {},
            {},
            None,
        )
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], list)
        assert isinstance(result[1], dict)

    def test_decay_suppresses_after_three(self):
        """Reminders shown >= 3 times are suppressed."""
        state = {
            "strict_score": 50.0,
            "reminder_history": {"rescan_needed": 3},
        }
        reminders, history = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            {},
            [],
            {},
            {},
            "autofix",
        )
        # "rescan_needed" would fire for command="autofix" but history count=3 -> suppressed
        reminder_types = [r["type"] for r in reminders]
        assert "rescan_needed" not in reminder_types

    def test_decay_allows_below_threshold(self):
        """Reminders shown < 3 times are allowed through."""
        state = {
            "strict_score": 50.0,
            "reminder_history": {"rescan_needed": 2},
        }
        reminders, history = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            {},
            [],
            {},
            {},
            "autofix",
        )
        reminder_types = [r["type"] for r in reminders]
        assert "rescan_needed" in reminder_types

    def test_updated_history_increments_count(self):
        """Updated history increments count for shown reminders."""
        state = {
            "strict_score": 50.0,
            "reminder_history": {"rescan_needed": 1},
        }
        reminders, updated = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            {},
            [],
            {},
            {},
            "autofix",
        )
        assert updated["rescan_needed"] == 2

    def test_rescan_reminder_after_fix(self):
        state = {"strict_score": 50.0}
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            {},
            [],
            {},
            {},
            "autofix",
        )
        reminder_types = [r["type"] for r in reminders]
        assert "rescan_needed" in reminder_types

    def test_rescan_reminder_after_resolve(self):
        state = {"strict_score": 50.0}
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            {},
            [],
            {},
            {},
            "resolve",
        )
        reminder_types = [r["type"] for r in reminders]
        assert "rescan_needed" in reminder_types

    def test_no_rescan_reminder_after_scan(self):
        state = {"strict_score": 50.0}
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            {},
            [],
            {},
            {},
            "scan",
        )
        reminder_types = [r["type"] for r in reminders]
        assert "rescan_needed" not in reminder_types

    def test_ignore_suppression_reminder_when_high(self):
        state = {
            "strict_score": 50.0,
            "ignore_integrity": {"ignored": 12, "suppressed_pct": 42.0},
        }
        reminders, _ = compute_reminders(
            state, "typescript", "middle_grind", {},
            [], {}, {}, "scan",
        )
        reminder_types = [r["type"] for r in reminders]
        assert "ignore_suppression_high" in reminder_types

    def test_no_ignore_suppression_reminder_when_low(self):
        state = {
            "strict_score": 50.0,
            "ignore_integrity": {"ignored": 2, "suppressed_pct": 12.0},
        }
        reminders, _ = compute_reminders(
            state, "typescript", "middle_grind", {},
            [], {}, {}, "scan",
        )
        reminder_types = [r["type"] for r in reminders]
        assert "ignore_suppression_high" not in reminder_types

    def test_wontfix_growing_reminder(self):
        state = {"strict_score": 50.0}
        debt = {"trend": "growing"}
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            debt,
            [],
            {},
            {},
            None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "wontfix_growing" in reminder_types

    def test_badge_recommendation_above_90(self):
        state = {"strict_score": 92.0}
        badge = {"generated": True, "in_readme": False}
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "maintenance",
            {},
            [],
            {},
            badge,
            None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "badge_recommendation" in reminder_types

    def test_no_badge_recommendation_below_90(self):
        state = {"strict_score": 85.0}
        badge = {"generated": True, "in_readme": False}
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "refinement",
            {},
            [],
            {},
            badge,
            None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "badge_recommendation" not in reminder_types

    def test_no_badge_recommendation_already_in_readme(self):
        state = {"strict_score": 95.0}
        badge = {"generated": True, "in_readme": True}
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "maintenance",
            {},
            [],
            {},
            badge,
            None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "badge_recommendation" not in reminder_types

    def test_auto_fixers_available_typescript(self):
        state = {"strict_score": 50.0}
        actions = [
            {
                "type": "auto_fix",
                "count": 5,
                "command": "desloppify autofix unused-imports --dry-run",
            }
        ]
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            {},
            actions,
            {},
            {},
            None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "auto_fixers_available" in reminder_types

    def test_auto_fixers_reminder_depends_on_actions_not_lang(self):
        """Auto-fixer reminder follows action availability, not language name."""
        state = {"strict_score": 50.0}
        actions = [
            {
                "type": "auto_fix",
                "count": 5,
                "command": "desloppify autofix unused-imports --dry-run",
            }
        ]
        reminders, _ = compute_reminders(
            state,
            "python",
            "middle_grind",
            {},
            actions,
            {},
            {},
            None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "auto_fixers_available" in reminder_types

    def test_stagnant_dimension_reminder(self):
        state = {"strict_score": 70.0}
        dimensions = {
            "stagnant_dimensions": [
                {"name": "Import hygiene", "strict": 80.0, "stuck_scans": 4},
            ],
        }
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "stagnation",
            {},
            [],
            dimensions,
            {},
            None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "stagnant_nudge" in reminder_types

    def test_dry_run_first_reminder(self):
        state = {"strict_score": 50.0}
        actions = [
            {
                "type": "auto_fix",
                "count": 3,
                "command": "desloppify autofix unused-imports --dry-run",
            }
        ]
        reminders, _ = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            {},
            actions,
            {},
            {},
            None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "dry_run_first" in reminder_types

    def test_reminders_include_metadata_and_rank_high_priority_first(self):
        state = {"strict_score": 50.0}
        actions = [{"type": "auto_fix", "count": 3, "command": "desloppify autofix unused-imports --dry-run"}]
        reminders, _ = compute_reminders(
            state, "typescript", "middle_grind", {"trend": "growing"},
            actions, {}, {}, "autofix",
        )
        reminder_types = [r["type"] for r in reminders]
        assert "rescan_needed" in reminder_types
        assert "wontfix_growing" in reminder_types
        assert reminder_types.index("rescan_needed") < reminder_types.index("wontfix_growing")
        assert all("priority" in r for r in reminders)
        assert all("severity" in r for r in reminders)

    def test_does_not_mutate_state(self):
        """The reminder_history on state must not be mutated."""
        original_history = {"rescan_needed": 1}
        state = {
            "strict_score": 50.0,
            "reminder_history": original_history,
        }
        _, updated = compute_reminders(
            state,
            "typescript",
            "middle_grind",
            {},
            [],
            {},
            {},
            "autofix",
        )
        # Original should be unchanged
        assert original_history == {"rescan_needed": 1}
        # Updated should have incremented
        assert updated["rescan_needed"] == 2

    def test_feedback_nudge_after_two_scans(self):
        """General feedback nudge appears after 2+ scans with command=scan."""
        state = {
            "strict_score": 50.0,
            "scan_history": [{"strict_score": 45.0}, {"strict_score": 50.0}],
        }
        reminders, _ = compute_reminders(
            state,
            "python",
            "middle_grind",
            {},
            [],
            {},
            {},
            "scan",
        )
        nudge_types = [r["type"] for r in reminders if r["type"] == "feedback_nudge"]
        assert len(nudge_types) == 1
        msg = next(r["message"] for r in reminders if r["type"] == "feedback_nudge")
        assert "issue" in msg.lower()

    def test_no_feedback_nudge_on_first_scan(self):
        """No feedback nudge on the very first scan."""
        state = {
            "strict_score": 50.0,
            "scan_history": [{"strict_score": 50.0}],
        }
        reminders, _ = compute_reminders(
            state,
            "python",
            "first_scan",
            {},
            [],
            {},
            {},
            "scan",
        )
        nudge_types = [r["type"] for r in reminders if r["type"] == "feedback_nudge"]
        assert len(nudge_types) == 0

    def test_no_feedback_nudge_on_non_scan_command(self):
        """Feedback nudge only fires on scan, not fix/show/next."""
        state = {
            "strict_score": 50.0,
            "scan_history": [{"strict_score": 45.0}, {"strict_score": 50.0}],
        }
        for cmd in ("autofix", "resolve", "show", "next", None):
            reminders, _ = compute_reminders(
                state,
                "python",
                "middle_grind",
                {},
                [],
                {},
                {},
                cmd,
            )
            nudge_types = [
                r["type"] for r in reminders if r["type"] == "feedback_nudge"
            ]
            assert len(nudge_types) == 0, f"nudge fired for command={cmd!r}"

    def test_feedback_nudge_stagnation_variant(self):
        """Stagnation phase triggers the stagnation-specific message."""
        state = {
            "strict_score": 70.0,
            "scan_history": [{"strict_score": 70.0}] * 4,
        }
        reminders, _ = compute_reminders(
            state,
            "python",
            "stagnation",
            {},
            [],
            {},
            {},
            "scan",
        )
        nudge = next((r for r in reminders if r["type"] == "feedback_nudge"), None)
        assert nudge is not None
        assert "plateau" in nudge["message"].lower()

    def test_feedback_nudge_fp_variant(self):
        """High FP rate triggers the FP-specific message."""
        # Need 5+ issues per (detector, zone) with >30% FP rate
        issues = {}
        for i in range(4):
            issues[str(i)] = _issue("unused", status="open")
        for i in range(4, 7):
            issues[str(i)] = _issue("unused", status="false_positive")
        # 7 total, 3 FP → 43% FP rate
        state = {
            "strict_score": 50.0,
            "scan_history": [{"strict_score": 45.0}, {"strict_score": 50.0}],
            "issues": issues,
        }
        reminders, _ = compute_reminders(
            state,
            "python",
            "middle_grind",
            {},
            [],
            {},
            {},
            "scan",
        )
        nudge = next((r for r in reminders if r["type"] == "feedback_nudge"), None)
        assert nudge is not None
        assert "false-positive" in nudge["message"].lower()

    def test_feedback_nudge_shared_decay(self):
        """All variants share one decay counter — 3 total then suppressed."""
        state = {
            "strict_score": 50.0,
            "scan_history": [{"strict_score": 45.0}, {"strict_score": 50.0}],
            "reminder_history": {"feedback_nudge": 3},
        }
        # Generic variant
        reminders, _ = compute_reminders(
            state,
            "python",
            "middle_grind",
            {},
            [],
            {},
            {},
            "scan",
        )
        assert not any(r["type"] == "feedback_nudge" for r in reminders)
        # Stagnation variant — still suppressed because same key
        reminders, _ = compute_reminders(
            state,
            "python",
            "stagnation",
            {},
            [],
            {},
            {},
            "scan",
        )
        assert not any(r["type"] == "feedback_nudge" for r in reminders)

    def test_feedback_nudge_contains_url(self):
        """Feedback nudge message includes the issue tracker URL."""
        state = {
            "strict_score": 50.0,
            "scan_history": [{"strict_score": 45.0}, {"strict_score": 50.0}],
        }
        reminders, _ = compute_reminders(
            state,
            "python",
            "middle_grind",
            {},
            [],
            {},
            {},
            "scan",
        )
        nudge = next((r for r in reminders if r["type"] == "feedback_nudge"), None)
        assert nudge is not None
        assert _FEEDBACK_URL in nudge["message"]


# ===================================================================
