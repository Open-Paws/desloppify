"""Tests for the subjective code review system (review.py, commands/review/cmd.py)."""

from __future__ import annotations

from desloppify.engine._scoring.policy.core import (
    DIMENSIONS,
    FILE_BASED_DETECTORS,
)
from desloppify.engine._scoring.results.core import compute_dimension_scores
from desloppify.intelligence.review import (
    import_holistic_issues,
    import_review_issues,
)
from desloppify.state import MergeScanOptions, merge_scan
from desloppify.state import empty_state as build_empty_state
from desloppify.tests.review.shared_review_fixtures import _as_review_payload


class TestImportReviewIssues:
    def test_import_valid_issues(self, empty_state, sample_issues_data):
        diff = import_review_issues(_as_review_payload(sample_issues_data), empty_state, "typescript")
        assert diff["new"] == 3
        # Check issues were added to state
        issues = empty_state["work_items"]
        assert len(issues) == 3
        # Check issue IDs follow the pattern
        ids = list(issues.keys())
        assert any("naming_quality" in fid for fid in ids)
        assert any("comment_quality" in fid for fid in ids)
        assert any("error_consistency" in fid for fid in ids)

    def test_import_skips_malformed_issues(self, empty_state):
        data = [
            {"file": "foo.ts"},  # Missing required fields
            {"dimension": "naming_quality"},  # Missing file
            {  # Valid
                "file": "src/foo.ts",
                "dimension": "naming_quality",
                "identifier": "foo",
                "summary": "test",
                "confidence": "low",
            },
        ]
        diff = import_review_issues(_as_review_payload(data), empty_state, "typescript")
        assert diff["new"] == 1

    def test_import_validates_confidence(self, empty_state):
        data = [
            {
                "file": "src/foo.ts",
                "dimension": "naming_quality",
                "identifier": "foo",
                "summary": "test",
                "confidence": "very_high",  # Invalid
            }
        ]
        import_review_issues(_as_review_payload(data), empty_state, "typescript")
        issue = list(empty_state["work_items"].values())[0]
        assert issue["confidence"] == "low"

    def test_import_validates_dimension(self, empty_state):
        data = [
            {
                "file": "src/foo.ts",
                "dimension": "invalid_dimension",
                "identifier": "foo",
                "summary": "test",
                "confidence": "high",
            }
        ]
        diff = import_review_issues(_as_review_payload(data), empty_state, "typescript")
        assert diff["new"] == 0

    def test_import_updates_review_cache(
        self, empty_state, sample_issues_data, tmp_path
    ):
        # Create actual files so hashing works
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "foo.ts").write_text("content")
        (tmp_path / "src" / "bar.ts").write_text("content")
        import_review_issues(
            _as_review_payload(sample_issues_data),
            empty_state,
            "typescript",
            project_root=tmp_path,
        )
        cache = empty_state.get("review_cache", {}).get("files", {})
        assert len(cache) >= 1  # At least one file cached

    def test_import_merges_with_state(self, state_with_issues, sample_issues_data):
        diff = import_review_issues(_as_review_payload(sample_issues_data), state_with_issues, "typescript"
        )
        # Original issues should still be there
        assert "unused::src/foo.ts::bar" in state_with_issues["issues"]
        assert diff["new"] == 3

    def test_import_preserves_existing_mechanical_potentials(
        self, empty_state, sample_issues_data
    ):
        empty_state["potentials"] = {"typescript": {"unused": 10, "smells": 25}}
        import_review_issues(_as_review_payload(sample_issues_data), empty_state, "typescript")

        pots = empty_state["potentials"]["typescript"]
        assert pots["unused"] == 10
        assert pots["smells"] == 25
        assert pots.get("review", 0) > 0

    def test_import_preserves_wontfix_issues(self, empty_state, sample_issues_data):
        # First import
        import_review_issues(_as_review_payload(sample_issues_data), empty_state, "typescript")
        # Mark one as wontfix
        for f in empty_state["work_items"].values():
            if "naming_quality" in f["id"]:
                f["status"] = "wontfix"
                f["note"] = "intentionally generic"
                break
        # Second import with same issues
        import_review_issues(_as_review_payload(sample_issues_data), empty_state, "typescript")
        # Wontfix should NOT be auto-resolved (it's still in current issues)
        assert any(f["status"] == "wontfix" for f in empty_state["work_items"].values())
        # The issue still exists
        assert any(
            "naming_quality" in f["id"] for f in empty_state["work_items"].values()
        )

    def test_import_sets_lang(self, empty_state, sample_issues_data):
        import_review_issues(_as_review_payload(sample_issues_data), empty_state, "python")
        for f in empty_state["work_items"].values():
            assert f["lang"] == "python"

    def test_import_sets_tier_3(self, empty_state, sample_issues_data):
        import_review_issues(_as_review_payload(sample_issues_data), empty_state, "typescript")
        for f in empty_state["work_items"].values():
            assert f["tier"] == 3

    def test_import_stores_detail(self, empty_state, sample_issues_data):
        import_review_issues(_as_review_payload(sample_issues_data), empty_state, "typescript")
        for f in empty_state["work_items"].values():
            assert "dimension" in f["detail"]
            assert "suggestion" in f["detail"]

    def test_id_collision_different_summaries(self, empty_state):
        """Two issues for same file/dimension/identifier but different summaries
        must both appear in state (#56)."""
        data = [
            {
                "file": "src/foo.ts",
                "dimension": "naming_quality",
                "identifier": "processData",
                "summary": "processData is vague — rename to reconcileInvoice",
                "evidence_lines": [15],
                "confidence": "high",
            },
            {
                "file": "src/foo.ts",
                "dimension": "naming_quality",
                "identifier": "processData",
                "summary": "processData doesn't indicate the return type",
                "evidence_lines": [15],
                "confidence": "medium",
            },
        ]
        diff = import_review_issues(_as_review_payload(data), empty_state, "typescript")
        # Same file + dimension + identifier = same issue ID, even with different summaries.
        # The second entry overwrites the first (last-writer wins during import).
        assert diff["new"] == 1
        assert len(empty_state["work_items"]) == 1

    def test_id_stable_for_same_summary(self, empty_state):
        """Same summary should produce the same issue ID (stable identifier)."""
        data = [
            {
                "file": "src/foo.ts",
                "dimension": "naming_quality",
                "identifier": "processData",
                "summary": "processData is vague",
                "confidence": "high",
            }
        ]
        import_review_issues(_as_review_payload(data), empty_state, "typescript")
        ids_first = set(empty_state["work_items"].keys())

        # Import again — should match same IDs (no new issues)
        diff = import_review_issues(_as_review_payload(data), empty_state, "typescript")
        assert diff["new"] == 0
        assert set(empty_state["work_items"].keys()) == ids_first


# ── Scoring integration tests ─────────────────────────────────────


class TestScoringIntegration:
    def test_review_issues_appear_in_scoring(self, empty_state, sample_issues_data):
        import_review_issues(_as_review_payload(sample_issues_data), empty_state, "typescript")

        # Assessment scores drive dimension scores directly.
        # Review issues are tracked but don't affect the score.
        assessments = {
            "naming_quality": {"score": 75},
            "comment_quality": {"score": 85},
        }
        potentials = {"review": 2}
        dim_scores = compute_dimension_scores(
            empty_state["work_items"], potentials, subjective_assessments=assessments
        )
        assert "Naming quality" in dim_scores
        assert dim_scores["Naming quality"]["score"] == 75.0
        det = dim_scores["Naming quality"]["detectors"]["subjective_assessment"]
        assert det["assessment_score"] == 75.0

    def test_review_issues_not_auto_resolved_by_scan(
        self, empty_state, sample_issues_data
    ):
        # Import review issues
        import_review_issues(_as_review_payload(sample_issues_data), empty_state, "typescript")
        review_ids = {
            f["id"]
            for f in empty_state["work_items"].values()
            if f["detector"] == "review"
        }

        # Simulate a normal scan with no review detector in potentials
        merge_scan(
            empty_state,
            [],
            options=MergeScanOptions(
                lang="typescript",
                potentials={"unused": 10, "smells": 50},
            ),
        )

        # Review issues should still be open (not auto-resolved)
        for fid in review_ids:
            if fid in empty_state["work_items"]:
                assert empty_state["work_items"][fid]["status"] == "open"

    def test_review_in_file_based_detectors(self):
        assert "review" in FILE_BASED_DETECTORS

    def test_test_health_dimension_exists(self):
        dim_names = [d.name for d in DIMENSIONS]
        assert "Test health" in dim_names
        rc = [d for d in DIMENSIONS if d.name == "Test health"][0]
        assert rc.tier == 4
        # subjective_review is now a non-objective detector, not in Test health
        assert "subjective_review" not in rc.detectors
        assert "test_coverage" in rc.detectors


# ── Assessment import tests ────────────────────────────────────────


class TestAssessmentImport:
    def test_import_new_format_with_assessments(self):
        state = build_empty_state()
        data = {
            "assessments": {"naming_quality": 75, "comment_quality": 85},
            "issues": [
                {
                    "file": "src/foo.ts",
                    "dimension": "naming_quality",
                    "identifier": "x",
                    "summary": "bad name",
                    "confidence": "high",
                },
            ],
        }
        diff = import_review_issues(_as_review_payload(data), state, "typescript")
        assert diff["new"] == 1
        assert len(state["work_items"]) == 1
        assessments = state["subjective_assessments"]
        assert "naming_quality" in assessments
        assert assessments["naming_quality"]["score"] == 75
        assert "comment_quality" in assessments
        assert assessments["comment_quality"]["score"] == 85

    def test_import_legacy_format_still_works(self):
        state = build_empty_state()
        data = [
            {
                "file": "src/foo.ts",
                "dimension": "naming_quality",
                "identifier": "x",
                "summary": "bad name",
                "confidence": "high",
            },
        ]
        diff = import_review_issues(_as_review_payload(data), state, "typescript")
        assert diff["new"] == 1
        # Legacy format: no assessments stored
        assert state.get("subjective_assessments", {}) == {}

    def test_holistic_assessment_overwrites_per_file(self):
        state = build_empty_state()
        # Import per-file assessments first
        per_file_data = {
            "assessments": {"abstraction_fitness": 60},
            "issues": [],
        }
        import_review_issues(_as_review_payload(per_file_data), state, "typescript")
        assert state["subjective_assessments"]["abstraction_fitness"]["score"] == 60

        # Import holistic assessments for the same dimension with a different score
        holistic_data = {
            "assessments": {"abstraction_fitness": 40},
            "issues": [],
        }
        import_holistic_issues(_as_review_payload(holistic_data), state, "typescript")
        # Holistic wins
        assert state["subjective_assessments"]["abstraction_fitness"]["score"] == 40
        assert (
            state["subjective_assessments"]["abstraction_fitness"]["source"]
            == "holistic"
        )

    def test_per_file_does_not_overwrite_holistic(self):
        state = build_empty_state()
        # Import holistic first
        holistic_data = {
            "assessments": {"abstraction_fitness": 40},
            "issues": [],
        }
        import_holistic_issues(_as_review_payload(holistic_data), state, "typescript")
        assert state["subjective_assessments"]["abstraction_fitness"]["score"] == 40

        # Import per-file for the same dimension
        per_file_data = {
            "assessments": {"abstraction_fitness": 80},
            "issues": [],
        }
        import_review_issues(_as_review_payload(per_file_data), state, "typescript")
        # Holistic score should be preserved
        assert state["subjective_assessments"]["abstraction_fitness"]["score"] == 40
        assert (
            state["subjective_assessments"]["abstraction_fitness"]["source"]
            == "holistic"
        )

    def test_assessment_score_clamped(self):
        state = build_empty_state()
        data = {
            "assessments": {"naming_quality": 150},
            "issues": [],
        }
        import_review_issues(_as_review_payload(data), state, "typescript")
        assert state["subjective_assessments"]["naming_quality"]["score"] == 100

    def test_assessment_negative_clamped(self):
        state = build_empty_state()
        data = {
            "assessments": {"naming_quality": -10},
            "issues": [],
        }
        import_review_issues(_as_review_payload(data), state, "typescript")
        assert state["subjective_assessments"]["naming_quality"]["score"] == 0

    def test_import_dict_without_assessments(self):
        state = build_empty_state()
        data = {
            "issues": [
                {
                    "file": "src/foo.ts",
                    "dimension": "naming_quality",
                    "identifier": "x",
                    "summary": "bad name",
                    "confidence": "high",
                },
            ],
        }
        diff = import_review_issues(_as_review_payload(data), state, "typescript")
        assert diff["new"] == 1
        # No assessments key in import data, so nothing stored
        assert state.get("subjective_assessments", {}) == {}
