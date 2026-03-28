"""Direct coverage tests for scan-coverage scoring projection helpers."""

from __future__ import annotations

import desloppify.engine._scoring.state_coverage as coverage_mod


def test_active_scan_coverage_prefers_state_lang_payload() -> None:
    state = {
        "lang": "python",
        "scan_coverage": {
            "python": {"detectors": {"security": {"status": "reduced"}}},
            "typescript": {"detectors": {"smells": {"status": "full"}}},
        },
    }

    payload = coverage_mod._active_scan_coverage(state)

    assert payload == {"detectors": {"security": {"status": "reduced"}}}


def test_active_scan_coverage_falls_back_when_only_one_entry() -> None:
    payload = coverage_mod._active_scan_coverage(
        {"scan_coverage": {"python": {"detectors": {"unused": {"status": "full"}}}}}
    )

    assert payload == {"detectors": {"unused": {"status": "full"}}}


def test_collect_reduced_detectors_filters_full_confident_entries() -> None:
    reduced = coverage_mod._collect_reduced_detectors(
        {
            "security": {"status": "reduced", "confidence": 0.72},
            "smells": {"status": "full", "confidence": 1.0},
            "unused": {"status": "full", "confidence": 0.9},
            "bad": "nope",
        }
    )

    assert reduced == {
        "security": {"status": "reduced", "confidence": 0.72},
        "unused": {"status": "full", "confidence": 0.9},
    }


def test_score_confidence_detector_entry_normalizes_and_rounds_fields() -> None:
    entry = coverage_mod._score_confidence_detector_entry(
        "security",
        {
            "status": "REDUCED",
            "confidence": 0.666,
            "summary": None,
            "impact": "x",
            "remediation": None,
            "tool": "bandit",
            "reason": 42,
        },
    )

    assert entry == {
        "detector": "security",
        "status": "REDUCED",
        "confidence": 0.67,
        "summary": "",
        "impact": "x",
        "remediation": "",
        "tool": "bandit",
        "reason": "42",
    }


def test_apply_scan_coverage_sets_full_payload_when_detector_map_missing() -> None:
    state = {"lang": "python", "scan_coverage": {"python": {"detectors": []}}}
    dimension_scores = {"Security": {"detectors": {"security": {}}}}

    coverage_mod.apply_scan_coverage_to_dimension_scores(
        state,
        dimension_scores=dimension_scores,
    )

    assert state["score_confidence"] == {
        "status": "full",
        "confidence": 1.0,
        "detectors": [],
        "dimensions": [],
    }


def test_apply_scan_coverage_projects_reduced_detector_into_dimensions() -> None:
    state = {
        "lang": "python",
        "scan_coverage": {
            "python": {
                "detectors": {
                    "security": {
                        "status": "reduced",
                        "confidence": 0.61,
                        "summary": "bandit unavailable",
                        "impact": "security checks reduced",
                        "remediation": "install bandit",
                        "tool": "bandit",
                        "reason": "missing dependency",
                    },
                    "unused": {"status": "full", "confidence": 1.0},
                }
            }
        },
    }
    dimension_scores = {
        "Security": {"detectors": {"security": {}}},
        "Dead code": {"detectors": {"unused": {"coverage_status": "stale"}}},
    }

    coverage_mod.apply_scan_coverage_to_dimension_scores(
        state,
        dimension_scores=dimension_scores,
    )

    security = dimension_scores["Security"]
    security_meta = security["detectors"]["security"]
    assert security_meta["coverage_status"] == "reduced"
    assert security_meta["coverage_confidence"] == 0.61
    assert security_meta["coverage_summary"] == "bandit unavailable"
    assert security["coverage_status"] == "reduced"
    assert security["coverage_confidence"] == 0.61

    dead_code_meta = dimension_scores["Dead code"]["detectors"]["unused"]
    assert "coverage_status" not in dead_code_meta
    assert state["score_confidence"]["status"] == "reduced"
    assert state["score_confidence"]["confidence"] == 0.61
    assert state["score_confidence"]["dimensions"] == ["Security"]
