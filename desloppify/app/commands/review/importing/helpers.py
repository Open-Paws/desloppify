"""Import/reporting helpers for holistic review command flows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from desloppify.intelligence.review.feedback_contract import (
    ASSESSMENT_FEEDBACK_THRESHOLD,
    LOW_SCORE_ISSUE_THRESHOLD,
)
from desloppify.intelligence.review.importing.contracts_models import (
    AssessmentImportPolicyModel,
)
from desloppify.intelligence.review.importing.contracts_types import (
    ReviewImportPayload,
)

from .output import (
    print_assessment_mode_banner,
    print_assessments_summary,
    print_import_load_errors,
    print_open_review_summary,
    print_review_import_scores_and_integrity,
    print_skipped_validation_details,
)
from .parse import (
    ImportParseOptions,
    ImportPayloadLoadError as ParseImportPayloadLoadError,
    _validate_assessment_feedback,
    _validate_holistic_issues_schema,
    load_import_issues_data as parse_load_import_issues_data,
    resolve_override_context,
)
from .policy import (
    ASSESSMENT_POLICY_KEY,
    ATTESTED_EXTERNAL_ATTEST_EXAMPLE,
    apply_assessment_import_policy,
    assessment_mode_label,
    assessment_policy_from_payload,
    assessment_policy_model_from_payload,
)


class ImportPayloadLoadError(ValueError):
    """Raised when review import payload parsing/validation fails."""

    def __init__(self, errors: list[str]) -> None:
        cleaned = [str(error).strip() for error in errors if str(error).strip()]
        self.errors = cleaned
        message = "; ".join(cleaned) if cleaned else "import payload validation failed"
        super().__init__(message)


@dataclass(frozen=True)
class ImportLoadConfig:
    """Config bundle for import payload parsing/validation options."""

    lang_name: str | None = None
    allow_partial: bool = False
    trusted_assessment_source: bool = False
    trusted_assessment_label: str | None = None
    attested_external: bool = False
    manual_override: bool = False
    manual_attest: str | None = None


def _normalize_optional_mapping(
    payload: dict[str, Any],
    key: str,
    *,
    errors: list[str],
) -> dict[str, Any]:
    """Normalize an optional payload mapping field."""
    value = payload.get(key)
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    errors.append(f"{key} must be an object when provided")
    return {}


def _normalize_reviewed_files_field(
    payload: dict[str, Any],
    *,
    errors: list[str],
) -> list[str]:
    """Normalize the optional reviewed_files list."""
    reviewed_files = payload.get("reviewed_files")
    if reviewed_files is None:
        return []
    if not isinstance(reviewed_files, list):
        errors.append("reviewed_files must be an array when provided")
        return []
    return [
        str(item).strip()
        for item in reviewed_files
        if isinstance(item, str) and str(item).strip()
    ]


def _normalize_assessment_policy(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the normalized assessment policy mapping for the payload."""
    policy = payload.get(ASSESSMENT_POLICY_KEY)
    if isinstance(policy, dict):
        return policy
    return AssessmentImportPolicyModel().to_dict()


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

    normalized_reviewed_files = _normalize_reviewed_files_field(
        payload,
        errors=errors,
    )
    review_scope = _normalize_optional_mapping(
        payload,
        "review_scope",
        errors=errors,
    )
    provenance = _normalize_optional_mapping(
        payload,
        "provenance",
        errors=errors,
    )
    dimension_notes = _normalize_optional_mapping(
        payload,
        "dimension_notes",
        errors=errors,
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
            ASSESSMENT_POLICY_KEY: _normalize_assessment_policy(payload),
        },
        [],
    )


def _validate_import_mode_flags(
    *,
    options: ImportLoadConfig,
    override_enabled: bool,
) -> list[str]:
    """Return mutually-exclusive flag errors for durable score imports."""
    if options.attested_external and override_enabled:
        return ["--attested-external cannot be combined with --manual-override"]
    if options.attested_external and options.allow_partial:
        return [
            "--attested-external cannot be combined with --allow-partial; "
            "attested score imports require fully valid issues payloads"
        ]
    if override_enabled and options.allow_partial:
        return [
            "--manual-override cannot be combined with --allow-partial; "
            "manual score imports require fully valid issues payloads"
        ]
    return []


def _validate_assessment_feedback_requirements(
    *,
    issues_data: ReviewImportPayload,
    override_enabled: bool,
    override_attest: str | None,
) -> list[str]:
    """Return missing assessment feedback/issue errors for score imports."""
    missing_feedback, missing_low_score_issues = _validate_assessment_feedback(
        issues_data
    )
    if override_enabled:
        if (missing_feedback or missing_low_score_issues) and not (
            isinstance(override_attest, str) and override_attest.strip()
        ):
            return ["--manual-override requires --attest"]
        return []
    if missing_low_score_issues:
        return [
            f"assessments below {LOW_SCORE_ISSUE_THRESHOLD:.1f} must include at "
            "least one issue for that same dimension with a concrete suggestion. "
            f"Missing: {', '.join(missing_low_score_issues)}"
        ]
    if missing_feedback:
        return [
            f"assessments below {ASSESSMENT_FEEDBACK_THRESHOLD:.1f} must include explicit feedback "
            "(issue with same dimension and non-empty suggestion, or "
            "dimension_notes evidence for that dimension). "
            f"Missing: {', '.join(missing_feedback)}"
        ]
    return []


def _format_schema_validation_errors(schema_errors: list[str]) -> list[str]:
    """Format capped holistic schema validation errors for CLI display."""
    visible_errors = schema_errors[:10]
    remaining = len(schema_errors) - len(visible_errors)
    errors = [
        "issues schema validation failed for holistic import. "
        "Fix payload or rerun with --allow-partial to continue."
    ]
    errors.extend(visible_errors)
    if remaining > 0:
        errors.append(f"... {remaining} additional schema error(s) omitted")
    return errors


def _load_import_payload_file(import_file: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Read and minimally validate the raw import payload from disk."""
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
    return issues_data, []


def _normalize_loaded_import_payload(
    issues_data: dict[str, Any],
) -> tuple[ReviewImportPayload | None, list[str]]:
    """Normalize the loaded import payload to the canonical object shape."""
    normalized_issues_data, shape_errors = _normalize_import_payload_shape(
        issues_data
    )
    if shape_errors:
        return None, shape_errors
    if normalized_issues_data is None:
        raise ValueError(
            "normalized import payload missing after successful shape validation"
        )
    return normalized_issues_data, []


def _resolve_import_override_context(
    options: ImportLoadConfig,
) -> tuple[bool, str | None, list[str]]:
    """Resolve override mode and validate mutually exclusive import flags."""
    override_enabled, override_attest = resolve_override_context(
        manual_override=options.manual_override,
        manual_attest=options.manual_attest,
    )
    flag_errors = _validate_import_mode_flags(
        options=options,
        override_enabled=override_enabled,
    )
    return override_enabled, override_attest, flag_errors


def _apply_import_policy(
    normalized_issues_data: ReviewImportPayload,
    *,
    import_file: str,
    options: ImportLoadConfig,
    override_enabled: bool,
    override_attest: str | None,
) -> tuple[ReviewImportPayload | None, list[str]]:
    """Apply assessment-import policy to a normalized payload."""
    issues_data, policy_errors = apply_assessment_import_policy(
        normalized_issues_data,
        import_file=import_file,
        attested_external=options.attested_external,
        attested_attest=override_attest,
        manual_override=override_enabled,
        manual_attest=override_attest,
        trusted_assessment_source=options.trusted_assessment_source,
        trusted_assessment_label=options.trusted_assessment_label,
    )
    if policy_errors:
        return None, policy_errors
    if issues_data is None:
        raise ValueError(
            "assessment import policy returned no payload without reporting errors"
        )
    return issues_data, []


def _validate_import_payload_content(
    issues_data: ReviewImportPayload,
    *,
    options: ImportLoadConfig,
    override_enabled: bool,
    override_attest: str | None,
) -> list[str]:
    """Validate review-feedback and holistic-schema requirements."""
    feedback_errors = _validate_assessment_feedback_requirements(
        issues_data=issues_data,
        override_enabled=override_enabled,
        override_attest=override_attest,
    )
    if feedback_errors:
        return feedback_errors

    schema_errors = _validate_holistic_issues_schema(
        issues_data,
        lang_name=options.lang_name,
    )
    if schema_errors and not options.allow_partial:
        return _format_schema_validation_errors(schema_errors)
    return []


def _parse_and_validate_import(
    import_file: str,
    *,
    config: ImportLoadConfig,
) -> tuple[ReviewImportPayload | None, list[str]]:
    """Load, parse, and validate a review import file.

    This helper performs filesystem I/O by reading ``import_file`` before
    normalizing and validating the payload.

    Returns ``(data, errors)`` where *data* is the normalized payload on
    success, or ``None`` when errors prevent import.
    """
    options = config
    issues_data, load_errors = _load_import_payload_file(import_file)
    if load_errors:
        return None, load_errors
    if issues_data is None:
        raise ValueError("import payload missing after successful file load")

    normalized_issues_data, shape_errors = _normalize_loaded_import_payload(
        issues_data
    )
    if shape_errors:
        return None, shape_errors
    if normalized_issues_data is None:
        raise ValueError("normalized import payload missing after successful normalization")

    override_enabled, override_attest, flag_errors = _resolve_import_override_context(
        options
    )
    if flag_errors:
        return None, flag_errors

    issues_data, policy_errors = _apply_import_policy(
        normalized_issues_data,
        import_file=import_file,
        options=options,
        override_enabled=override_enabled,
        override_attest=override_attest,
    )
    if policy_errors:
        return None, policy_errors
    if issues_data is None:
        raise ValueError("assessment import payload missing after successful policy application")

    content_errors = _validate_import_payload_content(
        issues_data,
        options=options,
        override_enabled=override_enabled,
        override_attest=override_attest,
    )
    if content_errors:
        return None, content_errors

    return issues_data, []


def load_import_issues_data(
    import_file: str,
    *,
    config: ImportLoadConfig,
) -> ReviewImportPayload:
    """Load and normalize review import payload via the canonical parse pipeline."""
    parse_options = ImportParseOptions(
        lang_name=config.lang_name,
        allow_partial=config.allow_partial,
        trusted_assessment_source=config.trusted_assessment_source,
        trusted_assessment_label=config.trusted_assessment_label,
        attested_external=config.attested_external,
        manual_override=config.manual_override,
        manual_attest=config.manual_attest,
    )
    try:
        return parse_load_import_issues_data(
            import_file,
            options=parse_options,
        )
    except ParseImportPayloadLoadError as exc:
        raise ImportPayloadLoadError(exc.errors) from exc


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

    _print_assessment_policy_notice_for_mode(
        policy_model,
        mode=mode,
        reason=reason,
        import_file=import_file,
        colorize_fn=colorize_fn,
    )


def _print_assessment_policy_notice_for_mode(
    policy_model: AssessmentImportPolicyModel,
    *,
    mode: str,
    reason: str,
    import_file: str,
    colorize_fn,
) -> None:
    """Render the assessment policy notice for one normalized mode."""
    count = int(policy_model.assessment_count or 0)
    if mode == "trusted":
        _print_trusted_assessment_notice(
            policy_model=policy_model,
            colorize_fn=colorize_fn,
        )
        return
    if mode == "trusted_internal":
        _print_trusted_internal_notice(
            count=count,
            reason=reason,
            colorize_fn=colorize_fn,
        )
        return
    if mode == "manual_override":
        _print_manual_override_notice(
            count=count,
            reason=reason,
            colorize_fn=colorize_fn,
        )
        return
    if mode == "attested_external":
        _print_attested_external_notice(
            count=count,
            reason=reason,
            colorize_fn=colorize_fn,
        )
        return
    if mode == "issues_only":
        _print_issues_only_notice(
            count=count,
            reason=reason,
            import_file=import_file,
            colorize_fn=colorize_fn,
        )


def _print_trusted_assessment_notice(
    *,
    policy_model: AssessmentImportPolicyModel,
    colorize_fn,
) -> None:
    packet_path = policy_model.provenance.packet_path.strip() or None
    detail = f" · blind packet {packet_path}" if packet_path else ""
    print(
        colorize_fn(
            f"  Assessment provenance: trusted blind batch artifact{detail}.",
            "dim",
        )
    )


def _print_trusted_internal_notice(*, count: int, reason: str, colorize_fn) -> None:
    suffix = f" ({reason})" if reason else ""
    print(
        colorize_fn(
            f"  Assessment updates applied: {count} dimension(s){suffix}.",
            "dim",
        )
    )


def _print_manual_override_notice(*, count: int, reason: str, colorize_fn) -> None:
    print(
        colorize_fn(
            f"  WARNING: applying {count} assessment update(s) via manual override from untrusted provenance.",
            "yellow",
        )
    )
    if reason:
        print(colorize_fn(f"  Reason: {reason}", "dim"))


def _print_attested_external_notice(*, count: int, reason: str, colorize_fn) -> None:
    print(
        colorize_fn(
            f"  Assessment updates applied via attested external blind review: {count} dimension(s).",
            "dim",
        )
    )
    if reason:
        print(colorize_fn(f"  Reason: {reason}", "dim"))


def _print_issues_only_notice(
    *,
    count: int,
    reason: str,
    import_file: str,
    colorize_fn,
) -> None:
    print(
        colorize_fn(
            "  WARNING: untrusted assessment source detected. "
            f"Imported issues only; skipped {count} assessment score update(s).",
            "yellow",
        )
    )
    if reason:
        print(colorize_fn(f"  Reason: {reason}", "dim"))
    for message in (
        "  Assessment scores in state were left unchanged.",
        "  Happy path: use `desloppify review --run-batches --parallel --scan-after-import`.",
        "  If you intentionally want manual assessment import, rerun with "
        f"`desloppify review --import {import_file} --manual-override --attest \"<why this is justified>\"`.",
        "  Claude cloud path for durable scores: "
        f"`desloppify review --import {import_file} --attested-external "
        f"--attest \"{ATTESTED_EXTERNAL_ATTEST_EXAMPLE}\"`",
    ):
        print(colorize_fn(message, "dim"))


__all__ = [
    "ImportLoadConfig",
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
