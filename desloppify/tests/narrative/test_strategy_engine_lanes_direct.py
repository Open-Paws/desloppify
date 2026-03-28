"""Direct coverage tests for strategy execution lane helpers."""

from __future__ import annotations

import desloppify.intelligence.narrative.strategy_engine_lanes as lanes_mod


def test_compute_lanes_builds_cleanup_refactor_and_test_coverage_lanes() -> None:
    actions = [
        {"priority": 1, "type": "auto_fix", "detector": "logs", "impact": 0.9},
        {"priority": 2, "type": "refactor", "detector": "smells", "impact": 0.8},
        {"priority": 3, "type": "manual_fix", "detector": "test_coverage", "impact": 0.6},
        {"priority": 4, "type": "reorganize", "detector": "large", "impact": 0.4},
        {"priority": 5, "type": "debt_review", "detector": None, "impact": 0.0},
    ]
    files_by_detector = {
        "logs": {"src/a.ts", "src/b.ts"},
        "smells": {"src/a.ts", "src/c.ts"},
        "test_coverage": {"tests/a.test.ts", "tests/b.test.ts"},
        "large": {"src/huge.ts"},
    }

    lanes = lanes_mod.compute_lanes(actions, files_by_detector)

    assert set(lanes) >= {"cleanup", "restructure", "refactor", "test_coverage", "debt_review"}
    assert lanes["cleanup"]["run_first"] is True
    assert lanes["test_coverage"]["actions"] == [3]
    assert lanes["restructure"]["file_count"] == 1


def test_refactor_lanes_split_by_file_overlap() -> None:
    refactor_actions = [
        {"priority": 11, "detector": "smells", "impact": 1.2},
        {"priority": 12, "detector": "deps", "impact": 0.7},
    ]
    files_by_detector = {
        "smells": {"src/a.ts"},
        "deps": {"src/b.ts"},
    }

    lanes = lanes_mod._refactor_lanes(refactor_actions, files_by_detector)
    assert set(lanes) == {"refactor_0", "refactor_1"}
    priorities = sorted([p for lane in lanes.values() for p in lane["actions"]])
    assert priorities == [11, 12]


def test_significant_lane_filters_debt_and_run_first() -> None:
    assert lanes_mod.significant_lane("debt_review", {"file_count": 10, "total_impact": 5.0}) is False
    assert lanes_mod.significant_lane("cleanup", {"run_first": True, "file_count": 99, "total_impact": 10}) is False
    assert lanes_mod.significant_lane("refactor", {"run_first": False, "file_count": 5, "total_impact": 0.1}) is True
    assert lanes_mod.significant_lane("refactor", {"run_first": False, "file_count": 1, "total_impact": 1.0}) is True
    assert lanes_mod.significant_lane("refactor", {"run_first": False, "file_count": 1, "total_impact": 0.2}) is False

