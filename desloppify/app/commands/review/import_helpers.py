"""Import/reporting helpers for holistic review command flows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .import_output import (
    print_assessment_mode_banner,
    print_assessments_summary,
    print_import_load_errors,
    print_open_review_summary,
    print_review_import_scores_and_integrity,
    print_skipped_validation_details,
)
from .import_parse import (
    _validate_assessment_feedback,
    _validate_holistic_issues_schema,
    resolve_override_context,
)
from .import_policy import (
    ASSESSMENT_POLICY_KEY,
    ATTESTED_EXTERNAL_ATTEST_EXAMPLE,
    apply_assessment_import_policy,
    assessment_mode_label,
    assessment_policy_from_payload,
    assessment_policy_model_from_payload,
)
from desloppify.intelligence.review.importing.contracts import (
    AssessmentImportPolicyModel,
    ReviewImportPayload,
)
from desloppify.intelligence.review.feedback_contract import (
    ASSESSMENT_FEEDBACK_THRESHOLD,
    LOW_SCORE_ISSUE_THRESHOLD,
)


class ImportPayloadLoadError(ValueError):
    """Raised when review import payload parsing/validation fails."""

    def __init__(self, errors: list[str]) -> None:
        cleaned = [str(error).strip() for error in errors if str(error).strip()]
        self.errors = cleaned
        message = "; ".join(cleaned) if cleaned else "import payload validation failed"
        super().__init__(message)


def _normalize_import_payload_shape(
    payload: dict[str, Any],
) -> tuple[ReviewImportPayload | None, list[str]]:
    """Normalize payload into required-key contract with strict type checks."""
    errors: list[str] = []
    issues = payload.get("issues")
    if not isinstance(issues, list):
        errors.append("issues must be a JSON array")
        issues = []

    assessments = payload.get("assessments")
    if assessments is None:
        assessments = {}
    elif not isinstance(assessments, dict):
        errors.append("assessments must be an object when provided")
        assessments = {}

    reviewed_files = payload.get("reviewed_files")
    normalized_reviewed_files: list[str] = []
    if reviewed_files is None:
        normalized_reviewed_files = []
    elif isinstance(reviewed_files, list):
        normalized_reviewed_files = [
            str(item).strip()
            for item in reviewed_files
            if isinstance(item, str) and str(item).strip()
        ]
    else:
        errors.append("reviewed_files must be an array when provided")

    review_scope = payload.get("review_scope")
    if review_scope is None:
        review_scope = {}
    elif not isinstance(review_scope, dict):
        errors.append("review_scope must be an object when provided")
        review_scope = {}

    provenance = payload.get("provenance")
    if provenance is None:
        provenance = {}
    elif not isinstance(provenance, dict):
        errors.append("provenance must be an object when provided")
        provenance = {}

    dimension_notes = payload.get("dimension_notes")
    if dimension_notes is None:
        dimension_notes = {}
    elif not isinstance(dimension_notes, dict):
        errors.append("dimension_notes must be an object when provided")
        dimension_notes = {}

    policy = payload.get(ASSESSMENT_POLICY_KEY)
    normalized_policy = (
        policy if isinstance(policy, dict) else AssessmentImportPolicyModel().to_dict()
    )
    if errors:
        return None, errors
    return (
        {
            "issues": issues,
            "assessments": assessments,
            "reviewed_files": normalized_reviewed_files,
            "review_scope": review_scope,
            "provenance": provenance,
            "dimension_notes": dimension_notes,
            ASSESSMENT_POLICY_KEY: normalized_policy,
        },
        [],
    )


def _parse_and_validate_import(
    import_file: str,
    *,
    lang_name: str | None = None,
    allow_partial: bool = False,
    trusted_assessment_source: bool = False,
    trusted_assessment_label: str | None = None,
    attested_external: bool = False,
    manual_override: bool = False,
    manual_attest: str | None = None,
    assessment_override: bool = False,
    assessment_note: str | None = None,
) -> tuple[ReviewImportPayload | None, list[str]]:
    """Parse and validate a review import file (pure function).

    Returns ``(data, errors)`` where *data* is the normalized payload on
    success, or ``None`` when errors prevent import.
    """
    issues_path = Path(import_file)
    if not issues_path.exists():
        return None, [f"file not found: {import_file}"]
    try:
        issues_data = json.loads(issues_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return None, [f"error reading issues: {exc}"]

    if isinstance(issues_data, list):
        issues_data = {"issues": issues_data}

    if not isinstance(issues_data, dict):
        return None, ["issues file must contain a JSON array or object"]

    if "issues" not in issues_data:
        return None, ["issues object must contain a 'issues' key"]
    normalized_issues_data, shape_errors = _normalize_import_payload_shape(
        issues_data
    )
    if shape_errors:
        return None, shape_errors
    assert normalized_issues_data is not None

    override_enabled, override_attest = resolve_override_context(
        manual_override=manual_override,
        manual_attest=manual_attest,
        assessment_override=assessment_override,
        assessment_note=assessment_note,
    )
    if attested_external and override_enabled:
        return None, [
            "--attested-external cannot be combined with --manual-override"
        ]
    if attested_external and allow_partial:
        return None, [
            "--attested-external cannot be combined with --allow-partial; "
            "attested score imports require fully valid issues payloads"
        ]
    if override_enabled and allow_partial:
        return None, [
            "--manual-override cannot be combined with --allow-partial; "
            "manual score imports require fully valid issues payloads"
        ]
    issues_data, policy_errors = apply_assessment_import_policy(
        normalized_issues_data,
        import_file=import_file,
        attested_external=attested_external,
        attested_attest=override_attest,
        manual_override=override_enabled,
        manual_attest=override_attest,
        trusted_assessment_source=trusted_assessment_source,
        trusted_assessment_label=trusted_assessment_label,
    )
    if policy_errors:
        return None, policy_errors
    assert issues_data is not None

    missing_feedback, missing_low_score_issues = _validate_assessment_feedback(
        issues_data
    )
    if missing_low_score_issues:
        if override_enabled:
            if not isinstance(override_attest, str) or not override_attest.strip():
                return None, ["--manual-override requires --attest"]
            return issues_data, []
        return None, [
            f"assessments below {LOW_SCORE_ISSUE_THRESHOLD:.1f} must include at "
            "least one issue for that same dimension with a concrete suggestion. "
            f"Missing: {', '.join(missing_low_score_issues)}"
        ]

    if missing_feedback:
        if override_enabled:
            if not isinstance(override_attest, str) or not override_attest.strip():
                return None, ["--manual-override requires --attest"]
            return issues_data, []
        return None, [
            f"assessments below {ASSESSMENT_FEEDBACK_THRESHOLD:.1f} must include explicit feedback "
            "(issue with same dimension and non-empty suggestion, or "
            "dimension_notes evidence for that dimension). "
            f"Missing: {', '.join(missing_feedback)}"
        ]

    schema_errors = _validate_holistic_issues_schema(
        issues_data,
        lang_name=lang_name,
    )
    if schema_errors and not allow_partial:
        visible_errors = schema_errors[:10]
        remaining = len(schema_errors) - len(visible_errors)
        errors = [
            "issues schema validation failed for holistic import. "
            "Fix payload or rerun with --allow-partial to continue."
        ]
        errors.extend(visible_errors)
        if remaining > 0:
            errors.append(f"... {remaining} additional schema error(s) omitted")
        return None, errors

    return issues_data, []


def load_import_issues_data(
    import_file: str,
    *,
    colorize_fn=None,
    lang_name: str | None = None,
    allow_partial: bool = False,
    trusted_assessment_source: bool = False,
    trusted_assessment_label: str | None = None,
    attested_external: bool = False,
    manual_override: bool = False,
    manual_attest: str | None = None,
    assessment_override: bool = False,
    assessment_note: str | None = None,
) -> ReviewImportPayload:
    """Load and normalize review import payload to object format.

    Raises ``ImportPayloadLoadError`` when validation fails.
    """
    data, errors = _parse_and_validate_import(
        import_file,
        lang_name=lang_name,
        allow_partial=allow_partial,
        trusted_assessment_source=trusted_assessment_source,
        trusted_assessment_label=trusted_assessment_label,
        attested_external=attested_external,
        manual_override=manual_override,
        manual_attest=manual_attest,
        assessment_override=assessment_override,
        assessment_note=assessment_note,
    )
    if errors:
        raise ImportPayloadLoadError(errors)
    assert data is not None  # guaranteed when errors is empty
    return data


def print_assessment_policy_notice(
    policy,
    *,
    import_file: str,
    colorize_fn,
) -> None:
    """Render trust/override status for assessment-bearing imports."""
    policy_model = AssessmentImportPolicyModel.from_mapping(policy)
    if not policy_model.assessments_present:
        return
    mode = policy_model.mode.strip().lower()
    reason = policy_model.reason.strip()

    if mode == "trusted":
        packet_path = policy_model.provenance.packet_path.strip() or None
        detail = f" · blind packet {packet_path}" if packet_path else ""
        print(
            colorize_fn(
                f"  Assessment provenance: trusted blind batch artifact{detail}.",
                "dim",
            )
        )
        return

    if mode == "trusted_internal":
        count = int(policy_model.assessment_count or 0)
        reason_text = policy_model.reason.strip()
        suffix = f" ({reason_text})" if reason_text else ""
        print(
            colorize_fn(
                f"  Assessment updates applied: {count} dimension(s){suffix}.",
                "dim",
            )
        )
        return

    if mode == "manual_override":
        count = int(policy_model.assessment_count or 0)
        print(
            colorize_fn(
                f"  WARNING: applying {count} assessment update(s) via manual override from untrusted provenance.",
                "yellow",
            )
        )
        if reason:
            print(colorize_fn(f"  Reason: {reason}", "dim"))
        return

    if mode == "attested_external":
        count = int(policy_model.assessment_count or 0)
        print(
            colorize_fn(
                f"  Assessment updates applied via attested external blind review: {count} dimension(s).",
                "dim",
            )
        )
        if reason:
            print(colorize_fn(f"  Reason: {reason}", "dim"))
        return

    if mode == "issues_only":
        count = int(policy_model.assessment_count or 0)
        print(
            colorize_fn(
                "  WARNING: untrusted assessment source detected. "
                f"Imported issues only; skipped {count} assessment score update(s).",
                "yellow",
            )
        )
        if reason:
            print(colorize_fn(f"  Reason: {reason}", "dim"))
        print(
            colorize_fn(
                "  Assessment scores in state were left unchanged.",
                "dim",
            )
        )
        print(
            colorize_fn(
                "  Happy path: use `desloppify review --run-batches --parallel --scan-after-import`.",
                "dim",
            )
        )
        print(
            colorize_fn(
                "  If you intentionally want manual assessment import, rerun with "
                f"`desloppify review --import {import_file} --manual-override --attest \"<why this is justified>\"`.",
                "dim",
            )
        )
        print(
            colorize_fn(
                "  Claude cloud path for durable scores: "
                f"`desloppify review --import {import_file} --attested-external "
                f"--attest \"{ATTESTED_EXTERNAL_ATTEST_EXAMPLE}\"`",
                "dim",
            )
        )


__all__ = [
    "ImportPayloadLoadError",
    "assessment_mode_label",
    "assessment_policy_model_from_payload",
    "assessment_policy_from_payload",
    "load_import_issues_data",
    "print_assessment_mode_banner",
    "print_import_load_errors",
    "print_assessment_policy_notice",
    "print_assessments_summary",
    "print_open_review_summary",
    "print_review_import_scores_and_integrity",
    "print_skipped_validation_details",
    "resolve_override_context",
]
