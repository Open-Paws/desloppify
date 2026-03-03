"""Typed contracts and schema helpers for review import payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NotRequired, Required, TypedDict

REVIEW_ISSUE_REQUIRED_FIELDS = (
    "dimension",
    "identifier",
    "summary",
    "confidence",
    "suggestion",
    "related_files",
    "evidence",
)
VALID_REVIEW_CONFIDENCE = frozenset({"high", "medium", "low"})


class ReviewIssuePayload(TypedDict, total=False):
    """Single issue entry in review import payloads."""

    file: str
    dimension: str
    identifier: str
    summary: str
    confidence: str
    suggestion: str
    evidence: list[str]
    related_files: list[str]
    reasoning: str
    evidence_lines: list[int]
    concern_verdict: str
    concern_fingerprint: str
    concern_type: str
    concern_file: str


def _normalized_non_empty_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if text else None


def _normalized_non_empty_text_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    cleaned = [
        str(item).strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]
    return cleaned if cleaned else None


def validate_review_issue_payload(
    issue: object,
    *,
    label: str,
    allowed_dimensions: set[str] | None = None,
    allow_dismissed: bool = True,
) -> tuple[ReviewIssuePayload | None, list[str]]:
    """Validate and normalize one review issue payload entry."""
    if not isinstance(issue, dict):
        return None, [f"{label} must be an object"]

    dismissed = issue.get("concern_verdict") == "dismissed"
    if dismissed and not allow_dismissed:
        return None, [f"{label}.concern_verdict='dismissed' is not allowed here"]

    if dismissed:
        fingerprint = _normalized_non_empty_text(issue.get("concern_fingerprint"))
        if fingerprint is None:
            return (
                None,
                [
                    f"{label}.concern_fingerprint is required when concern_verdict='dismissed'"
                ],
            )
        normalized: ReviewIssuePayload = {
            "concern_verdict": "dismissed",
            "concern_fingerprint": fingerprint,
        }
        concern_type = _normalized_non_empty_text(issue.get("concern_type"))
        if concern_type is not None:
            normalized["concern_type"] = concern_type
        concern_file = _normalized_non_empty_text(issue.get("concern_file"))
        if concern_file is not None:
            normalized["concern_file"] = concern_file
        reasoning = _normalized_non_empty_text(issue.get("reasoning"))
        if reasoning is not None:
            normalized["reasoning"] = reasoning
        return normalized, []

    errors: list[str] = []
    missing = [field for field in REVIEW_ISSUE_REQUIRED_FIELDS if field not in issue]
    if missing:
        errors.append(f"{label} missing required fields: {', '.join(missing)}")
        return None, errors

    dimension = _normalized_non_empty_text(issue.get("dimension"))
    if dimension is None:
        errors.append(f"{label}.dimension must be a non-empty string")
    elif allowed_dimensions is not None and dimension not in allowed_dimensions:
        errors.append(f"{label}.dimension '{dimension}' is not allowed")

    identifier = _normalized_non_empty_text(issue.get("identifier"))
    if identifier is None:
        errors.append(f"{label}.identifier must be a non-empty string")

    summary = _normalized_non_empty_text(issue.get("summary"))
    if summary is None:
        errors.append(f"{label}.summary must be a non-empty string")

    suggestion = _normalized_non_empty_text(issue.get("suggestion"))
    if suggestion is None:
        errors.append(f"{label}.suggestion must be a non-empty string")

    confidence = _normalized_non_empty_text(issue.get("confidence"))
    confidence_text = confidence.lower() if confidence is not None else ""
    if confidence_text not in VALID_REVIEW_CONFIDENCE:
        errors.append(f"{label}.confidence must be one of: high, medium, low")

    related_files = _normalized_non_empty_text_list(issue.get("related_files"))
    if related_files is None:
        errors.append(
            f"{label}.related_files must contain at least one file path string"
        )

    evidence = _normalized_non_empty_text_list(issue.get("evidence"))
    if evidence is None:
        errors.append(
            f"{label}.evidence must contain at least one concrete evidence string"
        )

    if errors:
        return None, errors

    normalized_payload: ReviewIssuePayload = {
        "dimension": dimension or "",
        "identifier": identifier or "",
        "summary": summary or "",
        "confidence": confidence_text,
        "suggestion": suggestion or "",
        "related_files": related_files or [],
        "evidence": evidence or [],
    }
    reasoning = _normalized_non_empty_text(issue.get("reasoning"))
    if reasoning is not None:
        normalized_payload["reasoning"] = reasoning
    concern_type = _normalized_non_empty_text(issue.get("concern_type"))
    if concern_type is not None:
        normalized_payload["concern_type"] = concern_type
    concern_file = _normalized_non_empty_text(issue.get("concern_file"))
    if concern_file is not None:
        normalized_payload["concern_file"] = concern_file
    file_path = _normalized_non_empty_text(issue.get("file"))
    if file_path is not None:
        normalized_payload["file"] = file_path
    evidence_lines = issue.get("evidence_lines")
    if isinstance(evidence_lines, list):
        normalized_lines = [line for line in evidence_lines if isinstance(line, int)]
        if normalized_lines:
            normalized_payload["evidence_lines"] = normalized_lines
    return normalized_payload, []


class ReviewScopePayload(TypedDict, total=False):
    """Optional import-scope metadata shipped with review payloads."""

    imported_dimensions: list[str]
    full_sweep_included: bool


class ReviewProvenancePayload(TypedDict, total=False):
    """Optional provenance block for imported review artifacts."""

    kind: str
    blind: bool
    runner: str
    packet_sha256: str
    packet_path: str


class ReviewImportPayload(TypedDict, total=False):
    """Top-level review import payload shared by per-file and holistic importers."""

    issues: Required[list[ReviewIssuePayload]]
    assessments: Required[dict[str, Any]]
    reviewed_files: Required[list[str]]
    review_scope: Required[ReviewScopePayload]
    provenance: Required[ReviewProvenancePayload]
    dimension_notes: Required[dict[str, Any]]
    _assessment_policy: Required[AssessmentImportPolicy]


class AssessmentProvenanceStatus(TypedDict, total=False):
    """Normalized provenance trust-check result for assessment imports."""

    trusted: Required[bool]
    reason: Required[str]
    import_file: Required[str]
    runner: str
    packet_path: str
    packet_sha256: str


class AssessmentImportPolicy(TypedDict, total=False):
    """Assessment import policy selected during payload validation."""

    assessments_present: Required[bool]
    assessment_count: Required[int]
    trusted: Required[bool]
    mode: Required[str]
    reason: Required[str]
    provenance: Required[AssessmentProvenanceStatus]
    attest: NotRequired[str]


@dataclass(frozen=True)
class AssessmentProvenanceModel:
    """Typed provenance status model for assessment import trust checks."""

    trusted: bool = False
    reason: str = ""
    import_file: str = ""
    runner: str = ""
    packet_path: str = ""
    packet_sha256: str = ""

    @classmethod
    def from_mapping(
        cls, payload: AssessmentProvenanceStatus | dict[str, Any] | None
    ) -> AssessmentProvenanceModel:
        data = payload if isinstance(payload, dict) else {}
        return cls(
            trusted=bool(data.get("trusted", False)),
            reason=str(data.get("reason", "") or ""),
            import_file=str(data.get("import_file", "") or ""),
            runner=str(data.get("runner", "") or ""),
            packet_path=str(data.get("packet_path", "") or ""),
            packet_sha256=str(data.get("packet_sha256", "") or ""),
        )

    def to_dict(self) -> AssessmentProvenanceStatus:
        payload: AssessmentProvenanceStatus = {
            "trusted": self.trusted,
            "reason": self.reason,
            "import_file": self.import_file,
        }
        if self.runner:
            payload["runner"] = self.runner
        if self.packet_path:
            payload["packet_path"] = self.packet_path
        if self.packet_sha256:
            payload["packet_sha256"] = self.packet_sha256
        return payload


@dataclass(frozen=True)
class AssessmentImportPolicyModel:
    """Typed assessment import policy model used by review import flows."""

    assessments_present: bool = False
    assessment_count: int = 0
    trusted: bool = False
    mode: str = "none"
    reason: str = ""
    provenance: AssessmentProvenanceModel = field(
        default_factory=AssessmentProvenanceModel
    )
    attest: str | None = None

    @classmethod
    def from_mapping(
        cls, payload: AssessmentImportPolicy | dict[str, Any] | None
    ) -> AssessmentImportPolicyModel:
        data = payload if isinstance(payload, dict) else {}
        attest = data.get("attest")
        return cls(
            assessments_present=bool(data.get("assessments_present", False)),
            assessment_count=int(data.get("assessment_count", 0) or 0),
            trusted=bool(data.get("trusted", False)),
            mode=str(data.get("mode", "none") or "none"),
            reason=str(data.get("reason", "") or ""),
            provenance=AssessmentProvenanceModel.from_mapping(data.get("provenance")),
            attest=(str(attest).strip() if isinstance(attest, str) and attest.strip() else None),
        )

    def to_dict(self) -> AssessmentImportPolicy:
        payload: AssessmentImportPolicy = {
            "assessments_present": bool(self.assessments_present),
            "assessment_count": int(self.assessment_count),
            "trusted": bool(self.trusted),
            "mode": self.mode,
            "reason": self.reason,
            "provenance": self.provenance.to_dict(),
        }
        if self.attest:
            payload["attest"] = self.attest
        return payload


__all__ = [
    "AssessmentImportPolicyModel",
    "AssessmentProvenanceModel",
    "AssessmentImportPolicy",
    "AssessmentProvenanceStatus",
    "REVIEW_ISSUE_REQUIRED_FIELDS",
    "VALID_REVIEW_CONFIDENCE",
    "ReviewIssuePayload",
    "ReviewImportPayload",
    "ReviewProvenancePayload",
    "ReviewScopePayload",
    "validate_review_issue_payload",
]
