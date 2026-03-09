"""Tests for concern generator signal extraction from structural detail dicts.

Phase 1A: The concern generator was reading detail.get("signals", {}) but
structural issues use flat dicts with complexity_signals as string lists.
These tests verify the fix works with the real structural format.
"""

from __future__ import annotations

from desloppify.engine._concerns.signals import (
    _extract_signals,
    _has_elevated_signals,
    _parse_complexity_signals,
)
from desloppify.engine.detectors.base import (
    ELEVATED_LOC_THRESHOLD,
    ELEVATED_NESTING_THRESHOLD,
    ELEVATED_PARAMS_THRESHOLD,
)

# ── _parse_complexity_signals ────────────────────────────


class TestParseComplexitySignals:
    """Parse params/nesting values from complexity_signals string list."""

    def test_extracts_params_from_string(self):
        detail = {"complexity_signals": ["function with 12 params"]}
        result = _parse_complexity_signals(detail)
        assert result["max_params"] == 12

    def test_extracts_nesting_from_string(self):
        detail = {"complexity_signals": ["nesting depth 8"]}
        result = _parse_complexity_signals(detail)
        assert result["max_nesting"] == 8

    def test_extracts_both_params_and_nesting(self):
        detail = {
            "complexity_signals": [
                "function with 10 params",
                "nesting depth 5",
            ]
        }
        result = _parse_complexity_signals(detail)
        assert result["max_params"] == 10
        assert result["max_nesting"] == 5

    def test_takes_max_across_multiple_entries(self):
        detail = {
            "complexity_signals": [
                "function with 6 params",
                "function with 12 params",
                "nesting depth 3",
                "nesting depth 9",
            ]
        }
        result = _parse_complexity_signals(detail)
        assert result["max_params"] == 12
        assert result["max_nesting"] == 9

    def test_empty_signals_returns_empty(self):
        assert _parse_complexity_signals({}) == {}
        assert _parse_complexity_signals({"complexity_signals": []}) == {}

    def test_ignores_non_string_entries(self):
        detail = {"complexity_signals": [42, None, True]}
        assert _parse_complexity_signals(detail) == {}

    def test_ignores_unrelated_strings(self):
        detail = {"complexity_signals": ["high cyclomatic complexity"]}
        assert _parse_complexity_signals(detail) == {}


# ── _extract_signals with flat structural detail ──────────


class TestExtractSignalsFlat:
    """_extract_signals works with the real flat structural detail format."""

    def test_reads_loc_from_flat_detail(self):
        issues = [
            {
                "detector": "structural",
                "detail": {"loc": 450},
            }
        ]
        signals = _extract_signals(issues)
        assert signals.get("loc") == 450

    def test_reads_params_from_complexity_signals(self):
        issues = [
            {
                "detector": "structural",
                "detail": {
                    "loc": 200,
                    "complexity_signals": ["function with 12 params"],
                },
            }
        ]
        signals = _extract_signals(issues)
        assert signals.get("max_params") == 12

    def test_reads_nesting_from_complexity_signals(self):
        issues = [
            {
                "detector": "structural",
                "detail": {
                    "loc": 200,
                    "complexity_signals": ["nesting depth 8"],
                },
            }
        ]
        signals = _extract_signals(issues)
        assert signals.get("max_nesting") == 8

    def test_combines_flat_loc_and_complexity_signals(self):
        issues = [
            {
                "detector": "structural",
                "detail": {
                    "loc": 500,
                    "complexity_score": 42,
                    "complexity_signals": [
                        "function with 12 params",
                        "nesting depth 6",
                    ],
                },
            }
        ]
        signals = _extract_signals(issues)
        assert signals.get("loc") == 500
        assert signals.get("max_params") == 12
        assert signals.get("max_nesting") == 6


# ── _has_elevated_signals with flat structural detail ──────


class TestHasElevatedSignalsFlat:
    """_has_elevated_signals works with real flat structural format."""

    def test_elevated_loc_in_flat_detail(self):
        issues = [
            {
                "detector": "structural",
                "detail": {"loc": ELEVATED_LOC_THRESHOLD + 1},
            }
        ]
        assert _has_elevated_signals(issues) is True

    def test_below_threshold_loc_not_elevated(self):
        issues = [
            {
                "detector": "structural",
                "detail": {"loc": ELEVATED_LOC_THRESHOLD - 1},
            }
        ]
        assert _has_elevated_signals(issues) is False

    def test_elevated_params_from_complexity_signals(self):
        issues = [
            {
                "detector": "structural",
                "detail": {
                    "complexity_signals": [
                        f"function with {ELEVATED_PARAMS_THRESHOLD} params"
                    ],
                },
            }
        ]
        assert _has_elevated_signals(issues) is True

    def test_below_threshold_params_not_elevated(self):
        issues = [
            {
                "detector": "structural",
                "detail": {
                    "complexity_signals": [
                        f"function with {ELEVATED_PARAMS_THRESHOLD - 1} params"
                    ],
                },
            }
        ]
        assert _has_elevated_signals(issues) is False

    def test_elevated_nesting_from_complexity_signals(self):
        issues = [
            {
                "detector": "structural",
                "detail": {
                    "complexity_signals": [
                        f"nesting depth {ELEVATED_NESTING_THRESHOLD}"
                    ],
                },
            }
        ]
        assert _has_elevated_signals(issues) is True

    def test_monster_function_always_elevated(self):
        issues = [
            {
                "detector": "smells",
                "detail": {"smell_id": "monster_function", "loc": 100},
            }
        ]
        assert _has_elevated_signals(issues) is True

    def test_empty_detail_not_elevated(self):
        issues = [
            {
                "detector": "structural",
                "detail": {},
            }
        ]
        assert _has_elevated_signals(issues) is False


class TestParseComplexitySignalsEdgeCases:
    """Additional edge cases for the regex-based parser."""

    def test_label_without_number_ignored(self):
        detail = {"complexity_signals": ["function with params"]}
        assert _parse_complexity_signals(detail) == {}

    def test_zero_params_parsed_but_downstream_filters(self):
        detail = {"complexity_signals": ["function with 0 params"]}
        result = _parse_complexity_signals(detail)
        # _parse stores raw value; downstream _update_max_signal filters <= 0.
        assert result["max_params"] == 0
        # Verify that _has_elevated_signals correctly treats 0 params as not elevated.
        issues = [{"detector": "structural", "detail": detail}]
        assert _has_elevated_signals(issues) is False
