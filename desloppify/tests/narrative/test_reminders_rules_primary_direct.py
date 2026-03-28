"""Direct coverage tests for primary narrative reminder rule helpers."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime as _dt
from datetime import timedelta

import desloppify.intelligence.narrative.reminders_rules_primary as primary_mod


def test_compute_fp_rates_merges_structural_and_applies_threshold() -> None:
    issues = {
        "a": {"detector": "large", "zone": "production", "status": "false_positive"},
        "b": {"detector": "complexity", "zone": "production", "status": "false_positive"},
        "c": {"detector": "gods", "zone": "production", "status": "open"},
        "d": {"detector": "concerns", "zone": "production", "status": "open"},
        "e": {"detector": "concerns", "zone": "production", "status": "open"},
        "f": {"detector": "smells", "zone": "test", "status": "false_positive"},
    }

    rates = primary_mod._compute_fp_rates(issues)
    assert rates[("structural", "production")] == 2 / 5
    assert ("smells", "test") not in rates


def test_autofix_rescan_badge_and_dry_run_reminders() -> None:
    auto = primary_mod._auto_fixer_reminder(
        [
            {"type": "manual_fix", "count": 1},
            {"type": "auto_fix", "count": 3, "command": "desloppify autofix unused-imports --dry-run"},
            {"type": "auto_fix", "count": 2, "command": "x"},
        ]
    )
    assert auto and auto[0]["type"] == "auto_fixers_available"
    assert "5 issues" in auto[0]["message"]

    assert primary_mod._rescan_needed_reminder("resolve")
    assert primary_mod._rescan_needed_reminder("scan") == []

    badge = primary_mod._badge_reminder(
        strict_score=91.0,
        badge={"generated": True, "in_readme": False, "path": "scorecard.png"},
    )
    assert badge and badge[0]["type"] == "badge_recommendation"

    dry = primary_mod._dry_run_reminder([{"type": "auto_fix"}])
    assert dry and dry[0]["type"] == "dry_run_first"


def test_wontfix_debt_and_ignore_suppression_reminders(monkeypatch) -> None:
    old_date = (_dt.now(UTC) - timedelta(days=90)).isoformat()
    state = {
        "scan_history": list(range(25)),
        "issues": {
            "w": {"status": "wontfix", "resolved_at": old_date},
            "x": {"status": "open"},
        },
    }
    reminders = primary_mod._wontfix_debt_reminders(state, {"trend": "growing"}, "scan")
    types = {r["type"] for r in reminders}
    assert {"wontfix_growing", "wontfix_stale"} <= types

    called = {"count": 0}

    def _mark(*_args, **_kwargs) -> None:
        called["count"] += 1

    monkeypatch.setattr(primary_mod, "log_best_effort_failure", _mark)
    bad_state = {
        "scan_history": list(range(25)),
        "issues": {"w": {"status": "wontfix", "resolved_at": "bad-date"}},
    }
    assert primary_mod._wontfix_debt_reminders(bad_state, {}, "scan") == []
    assert called["count"] == 1

    ignore = primary_mod._ignore_suppression_reminder(
        {"ignore_integrity": {"ignored": 12, "suppressed_pct": 31.5}}
    )
    assert ignore and ignore[0]["type"] == "ignore_suppression_high"
    assert primary_mod._ignore_suppression_reminder({"ignore_integrity": {"ignored": 1}}) == []


def test_stagnation_zone_and_fp_calibration_reminders() -> None:
    stagnant = primary_mod._stagnation_reminders(
        {
            "stagnant_dimensions": [
                {"name": "naming", "strict": 75, "stuck_scans": 4},
                {"name": "clarity", "strict": 100, "stuck_scans": 6},
            ]
        }
    )
    assert len(stagnant) == 2
    assert "different angle" in stagnant[0]["message"]
    assert "wontfix" in stagnant[1]["message"]

    zone = primary_mod._zone_classification_reminder(
        {"zone_distribution": {"production": 8, "tests": 2, "scripts": 1}}
    )
    assert zone and zone[0]["type"] == "zone_classification"
    assert "3 of 11" in zone[0]["message"]

    fp = primary_mod._fp_calibration_reminders(
        {("smells", "tests"): 0.31, ("unused", "production"): 0.1}
    )
    assert len(fp) == 1
    assert fp[0]["type"] == "fp_calibration_smells_tests"


def test_feedback_base_url_passthrough() -> None:
    assert primary_mod._feedback_base_url() == primary_mod._FEEDBACK_URL

