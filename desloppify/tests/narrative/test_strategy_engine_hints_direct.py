"""Direct coverage tests for strategy engine hint helpers."""

from __future__ import annotations

import desloppify.intelligence.narrative.strategy_engine_hints as hints_mod


def test_compute_fixer_leverage_recommendation_branches() -> None:
    strong = hints_mod.compute_fixer_leverage(
        by_detector={"smells": 10},
        actions=[{"type": "auto_fix", "count": 5, "impact": 4.0}, {"type": "manual_fix", "count": 5, "impact": 2.0}],
        phase="middle_grind",
        _lang="python",
    )
    assert strong["recommendation"] == "strong"
    assert strong["coverage"] == 0.5

    moderate = hints_mod.compute_fixer_leverage(
        by_detector={"smells": 20},
        actions=[
            {"type": "auto_fix", "count": 3, "impact": 1.0},
            {"type": "manual_fix", "count": 17, "impact": 10.0},
        ],
        phase="middle_grind",
        _lang=None,
    )
    assert moderate["recommendation"] == "moderate"

    phase_strong = hints_mod.compute_fixer_leverage(
        by_detector={"smells": 10},
        actions=[{"type": "auto_fix", "count": 2, "impact": 0.2}],
        phase="stagnation",
        _lang=None,
    )
    assert phase_strong["recommendation"] == "strong"


def test_compute_strategy_hint_for_strong_leverage_paths() -> None:
    fixer = {"recommendation": "strong", "coverage": 0.42}
    lanes = {
        "fast_lane": {"run_first": False},
        "cleanup_lane": {"run_first": False},
        "debt_review": {"run_first": False},
    }

    parallel = hints_mod.compute_strategy_hint(
        fixer,
        lanes,
        can_parallelize=True,
        phase="middle_grind",
    )
    assert "fixers first" in parallel.lower()
    assert "parallelize" in parallel.lower()
    assert "2 independent workstreams" in parallel

    serial = hints_mod.compute_strategy_hint(
        fixer,
        lanes,
        can_parallelize=False,
        phase="middle_grind",
    )
    assert "fixers first" in serial.lower()
    assert "42%" in serial


def test_compute_strategy_hint_for_non_strong_paths() -> None:
    fixer = {"recommendation": "none", "coverage": 0.0}
    lanes = {"lane": {"run_first": False}}

    parallel = hints_mod.compute_strategy_hint(fixer, lanes, True, "middle_grind")
    assert "parallelize" in parallel.lower()

    maintenance = hints_mod.compute_strategy_hint(fixer, lanes, False, "maintenance")
    assert "maintenance mode" in maintenance.lower()

    stagnation = hints_mod.compute_strategy_hint(fixer, lanes, False, "stagnation")
    assert "plateau" in stagnation.lower()

    default = hints_mod.compute_strategy_hint(fixer, lanes, False, "middle_grind")
    assert "priority order" in default.lower()
