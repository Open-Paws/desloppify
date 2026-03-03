"""Shared fixtures/helpers for split review test modules."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from desloppify.intelligence.review import (
    prepare_review as _prepare_review_impl,
)
from desloppify.intelligence.review import (
    select_files_for_review as _select_files_for_review_impl,
)
from desloppify.intelligence.review.prepare import ReviewPrepareOptions
from desloppify.intelligence.review.selection import ReviewSelectionOptions
from desloppify.state import empty_state as build_empty_state


@pytest.fixture
def empty_state():
    return build_empty_state()


@pytest.fixture
def state_with_issues():
    state = build_empty_state()
    state["issues"] = {
        "unused::src/foo.ts::bar": {
            "id": "unused::src/foo.ts::bar",
            "detector": "unused",
            "file": "src/foo.ts",
            "tier": 1,
            "confidence": "high",
            "summary": "Unused import: bar",
            "detail": {},
            "status": "open",
            "note": None,
            "first_seen": "2026-01-01T00:00:00+00:00",
            "last_seen": "2026-01-01T00:00:00+00:00",
            "resolved_at": None,
            "reopen_count": 0,
            "lang": "typescript",
        },
        "smells::src/utils.ts::eval_exec": {
            "id": "smells::src/utils.ts::eval_exec",
            "detector": "smells",
            "file": "src/utils.ts",
            "tier": 2,
            "confidence": "medium",
            "summary": "eval usage",
            "detail": {},
            "status": "open",
            "note": None,
            "first_seen": "2026-01-01T00:00:00+00:00",
            "last_seen": "2026-01-01T00:00:00+00:00",
            "resolved_at": None,
            "reopen_count": 0,
            "lang": "typescript",
        },
    }
    return state


@pytest.fixture
def mock_lang():
    """Create a mock LangConfig with minimal interface."""
    lang = MagicMock()
    lang.name = "typescript"
    lang.file_finder = MagicMock(
        return_value=["src/foo.ts", "src/bar.ts", "src/utils.ts"]
    )
    lang.zone_map = None
    lang.dep_graph = None
    lang.zone_rules = []
    lang.build_dep_graph = None
    return lang


@pytest.fixture
def mock_lang_with_zones(mock_lang):
    """Mock lang with zone map."""
    zone_map = MagicMock()

    def get_zone(filepath):
        z = MagicMock()
        fname = filepath.split("/")[-1] if "/" in filepath else filepath
        if (
            "__tests__" in filepath
            or fname.endswith(".test.ts")
            or fname.startswith("test_")
        ):
            z.value = "test"
        elif "generated" in fname:
            z.value = "generated"
        else:
            z.value = "production"
        return z

    zone_map.get = get_zone
    zone_map.counts.return_value = {"production": 3, "test": 1}
    mock_lang.zone_map = zone_map
    return mock_lang


@pytest.fixture
def sample_issues_data():
    """Sample agent-produced review issues."""
    return [
        {
            "file": "src/foo.ts",
            "dimension": "naming_quality",
            "identifier": "processData",
            "summary": "processData is vague — rename to reconcileInvoice",
            "evidence_lines": [15, 32],
            "evidence": ["function processData() handles invoice reconciliation"],
            "suggestion": "Rename processData to reconcileInvoice",
            "reasoning": "Callers expect invoice handling, not generic processing",
            "confidence": "high",
        },
        {
            "file": "src/bar.ts",
            "dimension": "comment_quality",
            "identifier": "handleSubmit",
            "summary": "Stale comment references removed validation step",
            "evidence_lines": [42],
            "evidence": ["Comment says 'validate first' but validation was removed"],
            "suggestion": "Remove stale comment on line 42",
            "reasoning": "Comment misleads maintainers about current behavior",
            "confidence": "medium",
        },
        {
            "file": "src/foo.ts",
            "dimension": "error_consistency",
            "identifier": "fetchUser",
            "summary": "fetchUser returns null on error while siblings throw",
            "evidence_lines": [80],
            "evidence": ["fetchUser returns null, fetchOrder throws on error"],
            "suggestion": "Align to throw pattern used by fetchOrder and fetchItems",
            "reasoning": "Mixed error conventions in the same module",
            "confidence": "low",
        },
    ]


def _as_review_payload(data):
    return data if isinstance(data, dict) else {"issues": data}


def select_files_for_review(lang, path, state, **kwargs):
    return _select_files_for_review_impl(
        lang, path, state, options=ReviewSelectionOptions(**kwargs)
    )


def prepare_review(path, lang, state, **kwargs):
    return _prepare_review_impl(path, lang, state, options=ReviewPrepareOptions(**kwargs))
