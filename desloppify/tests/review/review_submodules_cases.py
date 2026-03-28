"""Direct tests for review/ submodules — selection, prepare, import_issues, remediation.

These tests import directly from the submodule files (not the __init__.py facade)
so the test_coverage detector recognizes them as directly tested.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from desloppify.intelligence.review.importing.assessments import store_assessments
from desloppify.intelligence.review.importing.payload import extract_reviewed_files
from desloppify.intelligence.review.importing.per_file import (
    parse_per_file_import_payload,
)
from desloppify.intelligence.review.prepare import (
    HolisticReviewPrepareOptions,
    ReviewPrepareOptions,
    _build_file_requests,
    _build_investigation_batches,
    _rel_list,
)
from desloppify.intelligence.review.prepare import (
    prepare_holistic_review as _prepare_holistic_review_impl,
)
from desloppify.intelligence.review.prepare import (
    prepare_review as _prepare_review_impl,
)
from desloppify.intelligence.review.selection import (
    LOW_VALUE_NAMES,
    ReviewSelectionOptions,
    _compute_review_priority,
    count_fresh,
    count_stale,
    get_file_issues,
    hash_file,
    is_low_value_file,
)
from desloppify.intelligence.review.selection import (
    select_files_for_review as _select_files_for_review_impl,
)
from desloppify.state import empty_state as build_empty_state

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def empty_state():
    return build_empty_state()


@pytest.fixture
def mock_lang():
    lang = MagicMock()
    lang.name = "typescript"
    lang.zone_map = None
    lang.dep_graph = None
    lang.file_finder = MagicMock(return_value=[])
    return lang


def _call_select_files_for_review(lang, path, state, **kwargs):
    return _select_files_for_review_impl(
        lang, path, state, options=ReviewSelectionOptions(**kwargs)
    )


def _call_prepare_review(path, lang, state, **kwargs):
    return _prepare_review_impl(path, lang, state, options=ReviewPrepareOptions(**kwargs))


def _call_prepare_holistic_review(path, lang, state, **kwargs):
    return _prepare_holistic_review_impl(
        path,
        lang,
        state,
        options=HolisticReviewPrepareOptions(**kwargs),
    )


# ── selection.py tests ───────────────────────────────────────────


class TestHashFile:
    def test_hash_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        h = hash_file(str(f))
        assert len(h) == 16
        expected = hashlib.sha256(b"hello").hexdigest()[:16]
        assert h == expected

    def test_hash_missing_file(self):
        assert hash_file("/nonexistent/file.txt") == ""


class TestCountFreshStale:
    def test_count_fresh_empty(self, empty_state):
        assert count_fresh(empty_state, 30) == 0

    def test_count_fresh_with_recent(self, empty_state):
        now = datetime.now(UTC).isoformat()
        empty_state["review_cache"] = {"files": {"src/a.ts": {"reviewed_at": now}}}
        assert count_fresh(empty_state, 30) == 1

    def test_count_fresh_with_old(self, empty_state):
        old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        empty_state["review_cache"] = {"files": {"src/a.ts": {"reviewed_at": old}}}
        assert count_fresh(empty_state, 30) == 0

    def test_count_stale(self, empty_state):
        old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        now = datetime.now(UTC).isoformat()
        empty_state["review_cache"] = {
            "files": {
                "src/a.ts": {"reviewed_at": old},
                "src/b.ts": {"reviewed_at": now},
            }
        }
        assert count_stale(empty_state, 30) == 1


class TestGetFileIssues:
    def test_empty_state(self, empty_state):
        assert get_file_issues(empty_state, "src/foo.ts") == []

    def test_finds_matching(self, empty_state):
        empty_state["work_items"] = {
            "f1": {
                "detector": "smells",
                "file": "src/foo.ts",
                "summary": "bad smell",
                "status": "open",
                "id": "f1",
            },
            "f2": {
                "detector": "smells",
                "file": "src/bar.ts",
                "summary": "other",
                "status": "open",
                "id": "f2",
            },
        }
        with patch("desloppify.intelligence.review.selection.rel", side_effect=lambda x: x):
            results = get_file_issues(empty_state, "src/foo.ts")
        assert len(results) == 1
        assert results[0]["summary"] == "bad smell"


class TestComputeReviewPriority:
    def test_tiny_file_filtered(self, mock_lang, empty_state):
        with (
            patch("desloppify.intelligence.review.selection.rel", return_value="tiny.ts"),
            patch("desloppify.intelligence.review.selection.read_file_text", return_value="x\n" * 5),
        ):
            assert _compute_review_priority("tiny.ts", mock_lang, empty_state) == -1

    def test_normal_file_gets_score(self, mock_lang, empty_state):
        content = "line\n" * 100
        with (
            patch("desloppify.intelligence.review.selection.rel", return_value="src/app.ts"),
            patch("desloppify.intelligence.review.selection.read_file_text", return_value=content),
        ):
            score = _compute_review_priority("src/app.ts", mock_lang, empty_state)
            assert score >= 0

    def test_low_value_penalty(self, mock_lang, empty_state):
        content = "line\n" * 100
        with (
            patch("desloppify.intelligence.review.selection.rel") as mock_rel,
            patch("desloppify.intelligence.review.selection.read_file_text", return_value=content),
        ):
            mock_rel.return_value = "src/types.ts"
            low_score = _compute_review_priority("src/types.ts", mock_lang, empty_state)
            mock_rel.return_value = "src/app.ts"
            normal_score = _compute_review_priority(
                "src/app.ts", mock_lang, empty_state
            )
            assert low_score < normal_score


class TestSelectFilesForReview:
    def test_empty_files(self, mock_lang, empty_state):
        result = _call_select_files_for_review(mock_lang, Path("."), empty_state, files=[])
        assert result == []

    def test_skips_cached_fresh(self, mock_lang, empty_state):
        now = datetime.now(UTC).isoformat()
        content_hash = hashlib.sha256(b"hello").hexdigest()[:16]
        empty_state["review_cache"] = {
            "files": {
                "src/a.ts": {
                    "content_hash": content_hash,
                    "reviewed_at": now,
                }
            }
        }
        with (
            patch("desloppify.intelligence.review.selection.rel", return_value="src/a.ts"),
            patch("desloppify.intelligence.review.selection.hash_file", return_value=content_hash),
            patch(
                "desloppify.intelligence.review.selection._compute_review_priority", return_value=10
            ),
        ):
            result = _call_select_files_for_review(
                mock_lang,
                Path("."),
                empty_state,
                files=["src/a.ts"],
                force_refresh=False,
            )
        assert result == []


class TestLowValueNames:
    def test_types_file(self):
        assert LOW_VALUE_NAMES.search("src/types.ts")

    def test_dts_file(self):
        assert is_low_value_file("src/foo.d.ts", "typescript")

    def test_normal_file(self):
        assert not LOW_VALUE_NAMES.search("src/app.ts")


# ── prepare.py tests ────────────────────────────────────────────


class TestRelList:
    def test_set_input(self):
        with patch("desloppify.intelligence.review.prepare.rel", side_effect=lambda x: x):
            result = _rel_list({"b", "a", "c"})
            assert result == sorted(result)
            assert len(result) == 3

    def test_list_truncation(self):
        with patch("desloppify.intelligence.review.prepare.rel", side_effect=lambda x: x):
            result = _rel_list(list(range(20)))
            assert len(result) == 10


class TestBuildFileRequests:
    def test_basic(self, mock_lang, empty_state):
        with (
            patch(
                "desloppify.intelligence.review.prepare.read_file_text", return_value="line1\nline2"
            ),
            patch("desloppify.intelligence.review.prepare.rel", return_value="src/a.ts"),
            patch("desloppify.intelligence.review.prepare.abs_path", side_effect=lambda x: x),
        ):
            result = _build_file_requests(["src/a.ts"], mock_lang, empty_state)
        assert len(result) == 1
        assert result[0]["file"] == "src/a.ts"
        assert result[0]["loc"] == 2

    def test_skips_unreadable(self, mock_lang, empty_state):
        with (
            patch("desloppify.intelligence.review.prepare.read_file_text", return_value=None),
            patch("desloppify.intelligence.review.prepare.abs_path", side_effect=lambda x: x),
        ):
            result = _build_file_requests(["missing.ts"], mock_lang, empty_state)
        assert result == []


class TestBuildInvestigationBatches:
    def test_empty_context(self, mock_lang):
        result = _build_investigation_batches({}, mock_lang)
        # One batch per dimension, even with empty context
        assert len(result) >= 1
        for batch in result:
            assert "name" in batch
            assert "dimensions" in batch

    def test_batches_with_data(self, mock_lang):
        ctx = {
            "architecture": {"god_modules": [{"file": "src/big.ts"}]},
            "coupling": {"module_level_io": []},
            "conventions": {},
            "abstractions": {},
            "dependencies": {},
            "testing": {},
            "api_surface": {},
        }
        result = _build_investigation_batches(ctx, mock_lang)
        assert len(result) >= 1
        names = [b["name"] for b in result]
        assert "cross_module_architecture" in names
        arch_batch = next(b for b in result if b["name"] == "cross_module_architecture")
        assert "files_to_read" not in arch_batch
        assert arch_batch["dimensions"] == ["cross_module_architecture"]


class TestPrepareReview:
    def test_returns_expected_keys(self, mock_lang, empty_state):
        with (
            patch("desloppify.intelligence.review.prepare.build_review_context") as mock_ctx,
            patch("desloppify.intelligence.review.prepare.select_files_for_review", return_value=[]),
            patch("desloppify.intelligence.review.prepare._build_file_requests", return_value=[]),
            patch("desloppify.intelligence.review.prepare.serialize_context", return_value={}),
            patch("desloppify.intelligence.review.prepare.count_fresh", return_value=0),
            patch("desloppify.intelligence.review.prepare.count_stale", return_value=0),
        ):
            mock_ctx.return_value = MagicMock()
            result = _call_prepare_review(Path("."), mock_lang, empty_state, files=[])
        assert "command" in result
        assert result["command"] == "review"
        assert "dimensions" in result
        assert "files" in result
        assert "cache_status" in result


class TestPrepareHolisticReview:
    def test_returns_expected_keys(self, mock_lang, empty_state):
        with (
            patch("desloppify.intelligence.review.prepare.build_review_context") as mock_review_ctx,
            patch("desloppify.intelligence.review.prepare.build_holistic_context", return_value={}),
            patch("desloppify.intelligence.review.prepare.serialize_context", return_value={}),
            patch(
                "desloppify.intelligence.review.prepare._build_investigation_batches",
                return_value=[],
            ) as mock_build_batches,
        ):
            mock_review_ctx.return_value = MagicMock()
            result = _call_prepare_holistic_review(
                Path("."), mock_lang, empty_state, files=[]
            )
        assert result["command"] == "review"
        assert result["mode"] == "holistic"
        assert "investigation_batches" in result
        assert "workflow" in result
        assert mock_build_batches.call_args.kwargs["repo_root"] == Path(".")


# ── import_issues.py tests ──────────────────────────────────────


class TestExtractIssuesAndAssessments:
    def test_list_format_rejected(self):
        with pytest.raises(ValueError):
            parse_per_file_import_payload([{"file": "a.ts", "summary": "x"}])  # type: ignore[arg-type]

    def test_dict_format(self):
        data = {
            "issues": [{"file": "a.ts"}],
            "assessments": {"naming": 80},
        }
        issues, assessments = parse_per_file_import_payload(data)
        assert len(issues) == 1
        assert assessments == {"naming": 80}

    def test_invalid_type_rejected(self):
        with pytest.raises(ValueError):
            parse_per_file_import_payload("bad")  # type: ignore[arg-type]

    def test_non_object_issue_item_rejected(self):
        with pytest.raises(ValueError, match="issues\\[0\\]"):
            parse_per_file_import_payload(
                {
                    "issues": ["bad-item"],  # type: ignore[list-item]
                }
            )


class TestExtractReviewedFiles:
    def test_non_dict_payload(self):
        assert extract_reviewed_files([]) == []

    def test_valid_reviewed_files_dedupes_and_filters(self):
        payload = {
            "issues": [],
            "reviewed_files": ["src/a.ts", "src/a.ts", " ", 42, "src/b.ts"],
        }
        assert extract_reviewed_files(payload) == ["src/a.ts", "src/b.ts"]


class TestStoreAssessments:
    def test_stores_basic(self, empty_state):
        store_assessments(empty_state, {"naming_quality": 80}, "per_file")
        assert empty_state["subjective_assessments"]["naming_quality"]["score"] == 80
        assert empty_state["subjective_assessments"]["naming_quality"]["source"] == "per_file"

    def test_holistic_overwrites_per_file(self, empty_state):
        store_assessments(empty_state, {"naming_quality": 60}, "per_file")
        store_assessments(empty_state, {"naming_quality": 90}, "holistic")
        assert empty_state["subjective_assessments"]["naming_quality"]["score"] == 90

    def test_per_file_no_overwrite_holistic(self, empty_state):
        store_assessments(empty_state, {"naming_quality": 90}, "holistic")
        store_assessments(empty_state, {"naming_quality": 60}, "per_file")
        assert empty_state["subjective_assessments"]["naming_quality"]["score"] == 90

    def test_clamps_score(self, empty_state):
        store_assessments(empty_state, {"naming_quality": 200}, "per_file")
        assert empty_state["subjective_assessments"]["naming_quality"]["score"] == 100
        store_assessments(empty_state, {"naming_quality": -50}, "holistic")
        assert empty_state["subjective_assessments"]["naming_quality"]["score"] == 0

    def test_dict_value_format(self, empty_state):
        store_assessments(
            empty_state,
            {"naming_quality": {"score": 75, "extra": "data"}},
            "per_file",
        )
        assert empty_state["subjective_assessments"]["naming_quality"]["score"] == 75

    def test_preserves_component_breakdown_metadata(self, empty_state):
        store_assessments(
            empty_state,
            {
                "abstraction_fitness": {
                    "score": 71,
                    "components": ["Abstraction Leverage", "Indirection Cost"],
                    "component_scores": {
                        "Abstraction Leverage": 74,
                        "Indirection Cost": 68,
                    },
                }
            },
            "holistic",
        )
        stored = empty_state["subjective_assessments"]["abstraction_fitness"]
        assert stored["score"] == 71
        assert stored["components"] == ["Abstraction Leverage", "Indirection Cost"]
        assert stored["component_scores"]["Abstraction Leverage"] == 74.0
        assert stored["component_scores"]["Indirection Cost"] == 68.0

