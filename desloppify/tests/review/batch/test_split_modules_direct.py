"""Direct coverage tests for review/issue split modules."""

from __future__ import annotations

import pytest

from desloppify.base.output.issues import issue_weight, render_issue_detail
from desloppify.intelligence.review._prepare.remediation_engine import (
    render_empty_remediation_plan,
)
from desloppify.intelligence.review.importing.assessments import store_assessments
from desloppify.intelligence.review.importing.holistic import (
    parse_holistic_import_payload,
)
from desloppify.intelligence.review.importing.payload import (
    extract_reviewed_files,
    parse_review_import_payload,
)
from desloppify.intelligence.review.importing.per_file import (
    parse_per_file_import_payload,
)


def test_import_split_extract_helpers_require_object_payloads():
    with pytest.raises(ValueError):
        parse_per_file_import_payload([{"summary": "x"}])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="issues\\[0\\]"):
        parse_per_file_import_payload({"issues": ["x"]})  # type: ignore[list-item]

    issues2, assessments2, reviewed_files = parse_holistic_import_payload(
        {
            "issues": [{"summary": "y"}],
            "assessments": {"naming_quality": 88},
            "reviewed_files": ["a.py"],
        }
    )
    assert issues2 == [{"summary": "y"}]
    assert assessments2 == {"naming_quality": 88}
    assert reviewed_files == ["a.py"]

    with pytest.raises(ValueError, match="issues\\[0\\]"):
        parse_holistic_import_payload({"issues": ["bad"]})  # type: ignore[list-item]


def test_import_shared_extract_reviewed_files_deduplicates():
    reviewed = extract_reviewed_files({"reviewed_files": ["a.py", "", "a.py", "b.py"]})
    assert reviewed == ["a.py", "b.py"]


def test_import_shared_parse_payload_requires_canonical_issues_key():
    with pytest.raises(ValueError, match="must contain 'issues'"):
        parse_review_import_payload(
            {"findings": [{"summary": "legacy payload"}]},
            mode_name="Holistic",
        )


def test_store_assessments_keeps_holistic_precedence():
    state = {
        "subjective_assessments": {
            "naming_quality": {
                "score": 90,
                "source": "holistic",
                "assessed_at": "2026-01-01",
            }
        }
    }
    store_assessments(state, {"naming_quality": 50}, source="per_file")
    assert state["subjective_assessments"]["naming_quality"]["score"] == 90


def test_store_assessments_handles_raw_int_in_existing_state():
    """Regression test for #465: raw int in state should not crash store_assessments."""
    state = {
        "subjective_assessments": {
            "type_safety": 55,  # corrupted/old-format: raw int instead of dict
        }
    }
    # Should not raise AttributeError on the raw int
    store_assessments(state, {"type_safety": 70}, source="per_file")
    # The raw int should be overwritten with a proper dict
    result = state["subjective_assessments"]["type_safety"]
    assert isinstance(result, dict)
    assert result["score"] == 70
    assert result["source"] == "per_file"


def test_store_assessments_raw_int_overwritten_by_holistic():
    """Raw int in state should not block holistic source from overwriting."""
    state = {
        "subjective_assessments": {
            "type_safety": 55,  # corrupted raw int
        }
    }
    store_assessments(state, {"type_safety": 80}, source="holistic")
    result = state["subjective_assessments"]["type_safety"]
    assert isinstance(result, dict)
    assert result["score"] == 80
    assert result["source"] == "holistic"


def test_remediation_empty_plan_renders_scores_block():
    state = {
        "overall_score": 95.1,
        "objective_score": 96.2,
        "strict_score": 95.1,
        "version": 1,
        "created": "2026-01-01T00:00:00+00:00",
    }
    content = render_empty_remediation_plan(state, "python")
    assert "Holistic Review: Remediation Plan" in content
    assert (
        "desloppify --lang python review --prepare --path <src>" in content
    )


def test_issues_render_builds_markdown_payload():
    issue = {
        "id": "review::src/foo.py::logic_clarity::abc12345",
        "summary": "Simplify conditional chain",
        "confidence": "medium",
        "detail": {
            "dimension": "logic_clarity",
            "evidence": ["deeply nested conditionals"],
            "suggestion": "Extract guard clauses",
            "reasoning": "Improves readability",
            "evidence_lines": ["src/foo.py:10"],
        },
        "file": "src/foo.py",
    }
    weight, impact, _ = issue_weight(issue)
    assert weight > 0
    assert impact > 0

    rendered = render_issue_detail(issue, "python")
    assert "Suggested Fix" in rendered
    assert "desloppify plan resolve" in rendered
