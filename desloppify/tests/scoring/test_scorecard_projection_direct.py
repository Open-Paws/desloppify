"""Direct tests for scorecard projection helpers."""

from __future__ import annotations

from desloppify.engine.planning.scorecard_projection import (
    dimension_cli_key,
    scorecard_dimension_cli_keys,
    scorecard_dimensions_payload,
    scorecard_subjective_entries,
)


def test_dimension_cli_key_maps_display_name():
    assert dimension_cli_key("Logic clarity") == "logic_clarity"
    assert dimension_cli_key("Custom Dimension!") == "custom_dimension"


def test_elegance_dimension_cli_keys_use_components():
    keys = scorecard_dimension_cli_keys(
        "Elegance",
        {
            "detectors": {
                "subjective_assessment": {
                    "components": ["High elegance", "Mid elegance"],
                }
            }
        },
    )
    assert keys == ["high_level_elegance", "mid_level_elegance"]


def test_abstraction_dimension_cli_keys_use_components():
    keys = scorecard_dimension_cli_keys(
        "Abstraction fit",
        {
            "detectors": {
                "subjective_assessment": {
                    "components": [
                        "Abstraction Leverage",
                        "Delegation Density",
                        "Definition Directness",
                        "Type Discipline",
                    ],
                }
            }
        },
    )
    assert keys == ["abstraction_fitness"]


def test_scorecard_payload_includes_subjective_rows():
    state = {
        "scan_history": [{"lang": "python"}],
        "dimension_scores": {
            "File health": {
                "score": 98.0,
                "strict": 98.0,
                "checks": 10,
                "failing": 1,
                "tier": 3,
                "detectors": {"structural": {}},
            },
            "Naming quality": {
                "score": 96.0,
                "strict": 95.0,
                "checks": 50,
                "failing": 2,
                "tier": 4,
                "detectors": {
                    "subjective_assessment": {
                        "potential": 50,
                        "pass_rate": 0.96,
                        "failing": 2,
                        "weighted_failures": 2.0,
                        "components": [],
                    }
                },
            },
        },
    }
    entries = scorecard_subjective_entries(state)
    assert any(entry["name"] == "Naming quality" for entry in entries)

    payload = scorecard_dimensions_payload(state)
    naming = next(row for row in payload if row["name"] == "Naming quality")
    assert naming["subjective"] is True
    assert naming["cli_keys"] == ["naming_quality"]
