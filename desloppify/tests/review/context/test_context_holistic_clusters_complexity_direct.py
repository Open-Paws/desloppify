"""Direct coverage tests for holistic complexity cluster builder."""

from __future__ import annotations

from desloppify.intelligence.review.context_holistic.clusters.complexity import (
    _build_complexity_hotspots,
)


def test_build_complexity_hotspots_aggregates_signals_and_smells() -> None:
    by_detector = {
        "structural": [
            {
                "file": "src/a.py",
                "detail": {
                    "loc": 320,
                    "complexity_score": 9,
                    "max_params": 8,
                    "max_nesting": 6,
                    "function_count": 4,
                },
            },
            {
                "file": "src/b.py",
                "detail": {
                    "loc": 100,
                    "complexity_score": 2,
                    "component_count": 1,
                },
            },
        ],
        "smells": [
            {"file": "src/a.py", "detail": {"smell_id": "monster_function"}},
            {"file": "src/a.py", "detail": {"smell_id": "high_cyclomatic"}},
        ],
        "responsibility_cohesion": [
            {"file": "src/a.py", "detail": {"cluster_count": 5}},
        ],
    }

    hotspots = _build_complexity_hotspots(by_detector, by_file={})
    assert hotspots[0]["file"] == "src/a.py"
    assert hotspots[0]["monster_functions"] == 1
    assert hotspots[0]["cyclomatic_hotspots"] == 1
    assert hotspots[0]["component_count"] == 5
    assert "8 params" in hotspots[0]["signals"]
    assert "nesting depth 6" in hotspots[0]["signals"]


def test_build_complexity_hotspots_limits_to_top_twenty() -> None:
    by_detector = {
        "structural": [
            {
                "file": f"src/f{i}.py",
                "detail": {"loc": i * 10, "complexity_score": i},
            }
            for i in range(30)
        ]
    }

    hotspots = _build_complexity_hotspots(by_detector, by_file={})
    assert len(hotspots) == 20
    assert hotspots[0]["file"] == "src/f29.py"
    assert hotspots[-1]["file"] == "src/f10.py"
