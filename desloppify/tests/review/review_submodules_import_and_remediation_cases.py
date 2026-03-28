"""Direct tests for review importing, cache updates, and remediation generation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from desloppify.intelligence.review._prepare.remediation_engine import (
    render_empty_remediation_plan as _empty_plan,
)
from desloppify.intelligence.review.importing.holistic import (
    import_holistic_issues,
    update_holistic_review_cache,
)
from desloppify.intelligence.review.importing.per_file import (
    import_review_issues,
    update_review_cache,
)
from desloppify.intelligence.review.remediation import generate_remediation_plan
from desloppify.state import empty_state as build_empty_state
from desloppify.state import make_issue


@pytest.fixture
def empty_state():
    return build_empty_state()


def _as_review_payload(data):
    return data if isinstance(data, dict) else {"issues": data}


class TestImportReviewIssues:
    def test_valid_issue(self, empty_state):
        data = [
            {
                "file": "src/foo.ts",
                "dimension": "naming_quality",
                "identifier": "bad_names",
                "summary": "Poor variable names",
                "confidence": "medium",
            }
        ]
        diff = import_review_issues(_as_review_payload(data), empty_state, "typescript")
        assert diff.get("skipped", 0) == 0
        # Issue should be in state
        assert any(
            f.get("detector") == "review"
            for f in empty_state.get("work_items", {}).values()
        )

    def test_skips_missing_fields(self, empty_state):
        data = [{"file": "src/foo.ts"}]  # Missing dimension, identifier, etc.
        diff = import_review_issues(_as_review_payload(data), empty_state, "typescript")
        assert diff.get("skipped", 0) == 1

    def test_skips_invalid_dimension(self, empty_state):
        data = [
            {
                "file": "src/foo.ts",
                "dimension": "nonexistent_dimension",
                "identifier": "x",
                "summary": "x",
                "confidence": "high",
            }
        ]
        diff = import_review_issues(_as_review_payload(data), empty_state, "typescript")
        assert diff.get("skipped", 0) == 1

    def test_normalizes_invalid_confidence(self, empty_state):
        data = [
            {
                "file": "src/foo.ts",
                "dimension": "naming_quality",
                "identifier": "x",
                "summary": "test",
                "confidence": "INVALID",
            }
        ]
        _ = import_review_issues(_as_review_payload(data), empty_state, "typescript")
        issues = list(empty_state.get("work_items", {}).values())
        review_issues = [f for f in issues if f.get("detector") == "review"]
        assert len(review_issues) == 1
        assert review_issues[0]["confidence"] == "low"

    def test_import_with_reviewed_files_and_no_issues_updates_cache(
        self, empty_state, tmp_path
    ):
        src = tmp_path / "src"
        src.mkdir()
        fpath = src / "reviewed.ts"
        fpath.write_text("export const reviewed = true;\n")

        diff = import_review_issues(
            {"issues": [], "reviewed_files": ["src/reviewed.ts"]},
            empty_state,
            "typescript",
            project_root=tmp_path,
        )

        assert diff.get("new", 0) == 0
        cache = empty_state.get("review_cache", {}).get("files", {})
        assert "src/reviewed.ts" in cache
        assert cache["src/reviewed.ts"]["issue_count"] == 0

    def test_auto_resolves_missing_issues(self, empty_state):
        # Pre-existing review issue for src/foo.ts
        old = make_issue(
            detector="review",
            file="src/foo.ts",
            name="naming_quality::old::abc12345",
            tier=3,
            confidence="medium",
            summary="old issue",
            detail={"dimension": "naming_quality"},
        )
        old["lang"] = "typescript"
        empty_state["work_items"][old["id"]] = old
        # Import new issues for same file, but different issue
        data = [
            {
                "file": "src/foo.ts",
                "dimension": "naming_quality",
                "identifier": "new_issue",
                "summary": "New issue",
                "confidence": "high",
            }
        ]
        _ = import_review_issues(_as_review_payload(data), empty_state, "typescript")
        # Old issue should be marked fixed by the explicit import.
        assert empty_state["work_items"][old["id"]]["status"] == "fixed"


class TestImportHolisticIssues:
    def test_valid_holistic(self, empty_state):
        data = [
            {
                "dimension": "cross_module_architecture",
                "identifier": "god_module",
                "summary": "Too many responsibilities",
                "confidence": "high",
                "related_files": ["src/big.ts"],
                "evidence": ["src/big.ts mixes persistence, orchestration, and UI concerns"],
                "suggestion": "Split by domain",
            }
        ]
        import_holistic_issues(_as_review_payload(data), empty_state, "typescript")
        issues = list(empty_state.get("work_items", {}).values())
        holistic = [f for f in issues if f.get("detail", {}).get("holistic")]
        assert len(holistic) == 1

    def test_skips_invalid(self, empty_state):
        data = [{"summary": "missing dimension"}]
        diff = import_holistic_issues(_as_review_payload(data), empty_state, "typescript")
        assert diff.get("skipped", 0) == 1


class TestUpdateReviewCache:
    def test_updates_cache(self, empty_state):
        with patch.object(Path, "exists", return_value=False):
            update_review_cache(
                empty_state,
                [{"file": "src/a.ts"}],
                project_root=Path("/fake"),
                utc_now_fn=lambda: "2026-01-01T00:00:00+00:00",
            )
        cache = empty_state.get("review_cache", {}).get("files", {})
        assert "src/a.ts" in cache
        assert cache["src/a.ts"]["reviewed_at"] == "2026-01-01T00:00:00+00:00"


class TestUpdateHolisticReviewCache:
    def test_updates_holistic_cache(self, empty_state):
        update_holistic_review_cache(
            empty_state,
            [],
            utc_now_fn=lambda: "2026-02-01",
        )
        rc = empty_state.get("review_cache", {})
        assert "holistic" in rc
        assert rc["holistic"]["reviewed_at"] == "2026-02-01"

    def test_uses_codebase_metrics_total_files_when_present(self, empty_state):
        empty_state["codebase_metrics"] = {"python": {"total_files": 267}}
        update_holistic_review_cache(
            empty_state,
            [],
            lang_name="python",
            utc_now_fn=lambda: "2026-02-01",
        )

        rc = empty_state.get("review_cache", {})
        assert rc["holistic"]["file_count_at_review"] == 267

    def test_review_scope_total_files_overrides_metric_fallback(self, empty_state):
        empty_state["codebase_metrics"] = {"python": {"total_files": 267}}
        update_holistic_review_cache(
            empty_state,
            [],
            lang_name="python",
            review_scope={
                "total_files": 999,
                "reviewed_files_count": 42,
                "full_sweep_included": True,
            },
            utc_now_fn=lambda: "2026-02-01",
        )

        rc = empty_state.get("review_cache", {})
        assert rc["holistic"]["file_count_at_review"] == 999
        assert rc["holistic"]["reviewed_files_count"] == 42
        assert rc["holistic"]["full_sweep_included"] is True


# ── remediation.py tests ─────────────────────────────────────────


class TestEmptyPlan:
    def test_contains_score(self, empty_state):
        empty_state["objective_score"] = 88.5
        result = _empty_plan(empty_state, "typescript")
        assert "88.5" in result
        assert "No open holistic issues" in result


class TestGenerateRemediationPlan:
    def test_empty_issues(self, empty_state):
        result = generate_remediation_plan(empty_state, "typescript")
        assert "No open holistic issues" in result

    def test_with_issues(self, empty_state):
        f = make_issue(
            detector="review",
            file="",
            name="holistic::cross_module_architecture::god::abc12345",
            tier=3,
            confidence="high",
            summary="God module detected",
            detail={
                "holistic": True,
                "dimension": "cross_module_architecture",
                "related_files": ["src/big.ts"],
                "evidence": ["Too many exports"],
                "suggestion": "Split the module",
                "reasoning": "Reduces coupling",
            },
        )
        empty_state["work_items"][f["id"]] = f
        empty_state["objective_score"] = 85.0
        empty_state["strict_score"] = 84.0
        empty_state["potentials"] = {"typescript": {"review": 50}}
        result = generate_remediation_plan(empty_state, "typescript")
        assert "God module detected" in result
        assert "Priority 1" in result
        assert "Evidence" in result
        assert "Suggested fix" in result

    def test_writes_to_file(self, empty_state, tmp_path):
        out = tmp_path / "plan.md"
        with patch("desloppify.intelligence.review._prepare.remediation_engine.safe_write_text") as mock_write:
            generate_remediation_plan(empty_state, "python", output_path=out)
            mock_write.assert_called_once()
