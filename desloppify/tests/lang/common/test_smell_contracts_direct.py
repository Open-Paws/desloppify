"""Direct tests for typed smell boundary normalization helpers."""

from __future__ import annotations

import pytest

from desloppify.languages._framework.base.smell_contracts import (
    normalize_smell_entries,
    normalize_smell_matches,
)


def test_normalize_smell_entries_valid_payload() -> None:
    normalized = normalize_smell_entries(
        [
            {
                "id": "empty_catch",
                "label": "Empty catch blocks",
                "severity": "high",
                "matches": [{"file": "src/a.ts", "line": 7, "content": "catch"}],
            }
        ]
    )
    assert len(normalized) == 1
    assert normalized[0].smell_id == "empty_catch"
    assert normalized[0].matches[0].line == 7


def test_normalize_smell_entries_rejects_invalid_severity() -> None:
    with pytest.raises(ValueError, match="invalid severity"):
        normalize_smell_entries(
            [
                {
                    "id": "x",
                    "label": "bad",
                    "severity": "critical",
                    "matches": [],
                }
            ]
        )


def test_normalize_smell_matches_supports_alternate_content_keys() -> None:
    matches = normalize_smell_matches(
        [{"file": "src/a.ts", "line": 12, "after": "return"}],
        content_key="after",
        default_content="",
    )
    assert len(matches) == 1
    assert matches[0].content == "return"
