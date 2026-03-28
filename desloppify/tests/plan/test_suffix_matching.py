"""Tests for 8-char hex suffix matching in _matches_pattern."""

from __future__ import annotations

from desloppify.engine._state.filtering import _matches_pattern

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_ID = "review::.::holistic::dim::name::f41b3eb7"
_SAMPLE_ISSUE = {"detector": "review", "file": "test.py"}


# ---------------------------------------------------------------------------
# Suffix match tests
# ---------------------------------------------------------------------------


def test_suffix_match_8char_hex():
    """8-char lowercase hex suffix matches a issue ID ending with ::suffix."""
    assert _matches_pattern(_SAMPLE_ID, _SAMPLE_ISSUE, "f41b3eb7") is True


def test_suffix_no_match_wrong_hex():
    """Different 8-char hex does not match."""
    assert _matches_pattern(_SAMPLE_ID, _SAMPLE_ISSUE, "00000000") is False


def test_suffix_no_match_too_short():
    """7-char pattern is not treated as a suffix match."""
    assert _matches_pattern(_SAMPLE_ID, _SAMPLE_ISSUE, "f41b3eb") is False


def test_suffix_no_match_non_hex():
    """Pattern with non-hex chars is not treated as a suffix match."""
    assert _matches_pattern(_SAMPLE_ID, _SAMPLE_ISSUE, "f41b3exz") is False


def test_suffix_no_match_uppercase():
    """Uppercase hex is not treated as suffix match (issue IDs use lowercase)."""
    assert _matches_pattern(_SAMPLE_ID, _SAMPLE_ISSUE, "F41B3EB7") is False


# ---------------------------------------------------------------------------
# End-to-end through match_issues
# ---------------------------------------------------------------------------


def test_match_issues_via_suffix():
    """Suffix matching works through the match_issues() public API."""
    from desloppify.engine._state.resolution import match_issues

    state = {
        "issues": {
            _SAMPLE_ID: {
                "id": _SAMPLE_ID,
                "status": "open",
                "detector": "review",
                "file": "test.py",
                "summary": "test",
                "confidence": "medium",
                "tier": 2,
                "detail": {},
            },
        },
        "config": {},
    }
    results = match_issues(state, "f41b3eb7")
    assert len(results) == 1
    assert results[0]["id"] == _SAMPLE_ID


def test_match_issues_suffix_no_match():
    """Suffix that doesn't match any issue returns empty."""
    from desloppify.engine._state.resolution import match_issues

    state = {
        "issues": {
            _SAMPLE_ID: {
                "id": _SAMPLE_ID,
                "status": "open",
                "detector": "review",
                "file": "test.py",
                "summary": "test",
                "confidence": "medium",
                "tier": 2,
                "detail": {},
            },
        },
        "config": {},
    }
    results = match_issues(state, "deadbeef")
    assert len(results) == 0


# ---------------------------------------------------------------------------
# Name-segment match tests
# ---------------------------------------------------------------------------

_NAME_SEG_ID = "review::src/auth/login.py::timing_attack"
_NAME_SEG_ISSUE = {"detector": "review", "file": "src/auth/login.py"}


def test_name_segment_exact_match():
    """Bare issue name matches the last ::segment of an ID."""
    assert _matches_pattern(_NAME_SEG_ID, _NAME_SEG_ISSUE, "timing_attack") is True


def test_name_segment_no_partial_match():
    """Partial name does NOT match (exact segment only)."""
    assert _matches_pattern(_NAME_SEG_ID, _NAME_SEG_ISSUE, "timing") is False


def test_name_segment_no_match_with_colons():
    """Pattern containing :: uses prefix rule, not name-segment."""
    assert _matches_pattern(_NAME_SEG_ID, _NAME_SEG_ISSUE, "review::timing_attack") is False


def test_name_segment_does_not_shadow_detector():
    """'review' still matches via detector rule even though it's also a prefix segment."""
    assert _matches_pattern(_NAME_SEG_ID, _NAME_SEG_ISSUE, "review") is True


# ---------------------------------------------------------------------------
# Second-to-last segment match for hashed IDs
# ---------------------------------------------------------------------------

_HASHED_ID = "review::.::holistic::concerns::facade_hub_coupling::7fd735cf"
_HASHED_ISSUE = {"detector": "review", "file": "."}


def test_descriptive_name_matches_hashed_id():
    """Descriptive name (second-to-last segment) matches when last segment is 8-char hex."""
    assert _matches_pattern(_HASHED_ID, _HASHED_ISSUE, "facade_hub_coupling") is True


def test_descriptive_name_no_partial():
    """Partial descriptive name does NOT match."""
    assert _matches_pattern(_HASHED_ID, _HASHED_ISSUE, "facade_hub") is False


def test_second_to_last_only_when_hex_suffix():
    """Second-to-last match is skipped when last segment is NOT 8-char hex."""
    non_hex_id = "review::.::holistic::concerns::facade_hub_coupling::not_hex_"
    issue = {"detector": "review", "file": "."}
    # "facade_hub_coupling" should NOT match because last segment isn't hex
    assert _matches_pattern(non_hex_id, issue, "facade_hub_coupling") is False
    # But exact last-segment match still works
    assert _matches_pattern(non_hex_id, issue, "not_hex_") is True
