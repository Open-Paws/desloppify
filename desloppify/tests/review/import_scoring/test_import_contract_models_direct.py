"""Direct tests for typed review import contract models."""

from __future__ import annotations

from desloppify.intelligence.review.importing.contracts_types import (
    NormalizedReviewImportPayload,
    ReviewImportPayload,
)
from desloppify.intelligence.review.importing.contracts_models import (
    AssessmentImportPolicyModel,
    AssessmentProvenanceModel,
)


def test_assessment_provenance_model_round_trip():
    model = AssessmentProvenanceModel.from_mapping(
        {
            "trusted": True,
            "reason": "trusted blind subagent provenance",
            "import_file": "issues.json",
            "runner": "claude",
            "packet_path": "/tmp/review_packet_blind.json",
            "packet_sha256": "a" * 64,
        }
    )
    dumped = model.to_dict()
    assert dumped["trusted"] is True
    assert dumped["runner"] == "claude"
    assert dumped["packet_path"] == "/tmp/review_packet_blind.json"


def test_assessment_import_policy_model_round_trip():
    model = AssessmentImportPolicyModel.from_mapping(
        {
            "assessments_present": True,
            "assessment_count": 2,
            "trusted": True,
            "mode": "trusted_internal",
            "reason": "trusted internal run-batches import",
            "provenance": {
                "trusted": True,
                "reason": "trusted blind subagent provenance",
                "import_file": "issues.json",
            },
        }
    )
    dumped = model.to_dict()
    assert dumped["mode"] == "trusted_internal"
    assert dumped["assessment_count"] == 2
    assert dumped["provenance"]["trusted"] is True


def test_review_import_payload_is_raw_optional_envelope() -> None:
    """Parser validates required keys; raw payload TypedDict should not over-promise."""
    required = set(getattr(ReviewImportPayload, "__required_keys__", set()))
    optional = set(getattr(ReviewImportPayload, "__optional_keys__", set()))
    assert required == set()
    assert {
        "issues",
        "assessments",
        "reviewed_files",
        "review_scope",
        "provenance",
        "dimension_notes",
        "_assessment_policy",
    }.issubset(optional)


def test_normalized_review_import_payload_requires_fully_populated_contract() -> None:
    required = set(getattr(NormalizedReviewImportPayload, "__required_keys__", set()))
    assert required == {
        "issues",
        "assessments",
        "reviewed_files",
        "review_scope",
        "provenance",
        "dimension_notes",
        "_assessment_policy",
    }
