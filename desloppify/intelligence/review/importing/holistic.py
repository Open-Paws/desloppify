"""Holistic review issue import workflow."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from desloppify.intelligence.review.dimensions import normalize_dimension_name
from desloppify.intelligence.review.dimensions.data import load_dimensions_for_lang
from desloppify.intelligence.review.importing.contracts import (
    ReviewIssuePayload,
    ReviewImportPayload,
    ReviewScopePayload,
    validate_review_issue_payload,
)
from desloppify.intelligence.review.importing.shared import (
    _lang_potentials,
    auto_resolve_review_issues,
    normalize_review_confidence,
    parse_review_import_payload,
    refresh_review_file_cache,
    review_tier,
    ReviewImportEnvelope,
    store_assessments,
)
from desloppify.intelligence.review.selection import hash_file
from desloppify.scoring import HOLISTIC_POTENTIAL
from desloppify.state import MergeScanOptions, make_issue, merge_scan, utc_now

# Backward-compatible test patch hook (runtime root now resolves lazily).
PROJECT_ROOT: Path | None = None


def parse_holistic_import_payload(
    data: ReviewImportPayload | dict[str, Any],
) -> tuple[list[ReviewIssuePayload], dict[str, Any] | None, list[str]]:
    """Parse strict holistic import payload object."""
    payload = parse_review_import_payload(data, mode_name="Holistic")
    return payload.issues, payload.assessments, payload.reviewed_files


def update_reviewed_file_cache(
    state: dict[str, Any],
    reviewed_files: list[str],
    *,
    project_root: Path | str | None = None,
    utc_now_fn=utc_now,
) -> None:
    """Refresh per-file review cache entries from holistic payload metadata."""
    refresh_review_file_cache(
        state,
        reviewed_files=reviewed_files,
        issues_by_file=None,
        project_root=project_root,
        hash_file_fn=hash_file,
        utc_now_fn=utc_now_fn,
    )


_POSITIVE_PREFIXES = (
    "good ",
    "well ",
    "strong ",
    "clean ",
    "excellent ",
    "nice ",
    "solid ",
)


def _validate_and_build_issues(
    issues_list: list[ReviewIssuePayload],
    holistic_prompts: dict[str, Any],
    lang_name: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate raw holistic issues and build state-ready issue dicts.

    Returns (review_issues, skipped, dismissed_concerns).
    """
    review_issues: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    dismissed_concerns: list[dict[str, Any]] = []
    allowed_dimensions = {
        dim for dim in holistic_prompts if isinstance(dim, str) and dim.strip()
    }

    for idx, raw_issue in enumerate(issues_list):
        issue, issue_errors = validate_review_issue_payload(
            raw_issue,
            label=f"issues[{idx}]",
            allowed_dimensions=allowed_dimensions,
            allow_dismissed=True,
        )
        if issue_errors:
            skipped.append(
                {
                    "index": idx,
                    "missing": issue_errors,
                    "identifier": (
                        raw_issue.get("identifier", "<none>")
                        if isinstance(raw_issue, dict)
                        else "<none>"
                    ),
                }
            )
            continue
        assert issue is not None

        # Handle dismissed concern verdicts (no dimension/summary required).
        if issue.get("concern_verdict") == "dismissed":
            fp = issue.get("concern_fingerprint", "")
            if fp:
                dismissed_concerns.append(
                    {
                        "fingerprint": fp,
                        "concern_type": issue.get("concern_type", ""),
                        "concern_file": issue.get("concern_file", ""),
                        "reasoning": issue.get("reasoning", ""),
                    }
                )
            continue

        # Safety net: skip positive observations that slipped past the prompt.
        summary_text = str(issue.get("summary", ""))
        if summary_text.lower().startswith(_POSITIVE_PREFIXES):
            skipped.append(
                {
                    "index": idx,
                    "missing": ["positive observation (not a defect)"],
                    "identifier": issue.get("identifier", "<none>"),
                }
            )
            continue

        dimension = issue["dimension"]

        # Confirmed concern verdicts become "concerns" detector issues.
        is_confirmed_concern = issue.get("concern_verdict") == "confirmed"
        detector = "concerns" if is_confirmed_concern else "review"

        content_hash = hashlib.sha256(summary_text.encode()).hexdigest()[:8]
        detail: dict[str, Any] = {
            "holistic": True,
            "dimension": dimension,
            "related_files": issue["related_files"],
            "evidence": issue["evidence"],
            "suggestion": issue.get("suggestion", ""),
            "reasoning": issue.get("reasoning", ""),
        }
        if is_confirmed_concern:
            detail["concern_type"] = issue.get("concern_type", "")
            detail["concern_verdict"] = "confirmed"

        prefix = "concern" if is_confirmed_concern else "holistic"
        file = issue.get("concern_file", "") if is_confirmed_concern else ""
        confidence = normalize_review_confidence(issue.get("confidence", "low"))
        imported = make_issue(
            detector=detector,
            file=file,
            name=f"{prefix}::{dimension}::{issue['identifier']}::{content_hash}",
            tier=review_tier(confidence, holistic=True),
            confidence=confidence,
            summary=summary_text,
            detail=detail,
        )
        imported["lang"] = lang_name
        review_issues.append(imported)

    return review_issues, skipped, dismissed_concerns


def _collect_imported_dimensions(
    *,
    issues_list: list[ReviewIssuePayload],
    review_issues: list[dict[str, Any]],
    assessments: dict[str, Any] | None,
    review_scope: ReviewScopePayload | dict[str, Any] | None,
    valid_dimensions: set[str],
) -> set[str]:
    """Return normalized dimensions this import explicitly covered."""
    imported_dimensions: set[str] = set()

    if isinstance(review_scope, dict):
        scope_dims = review_scope.get("imported_dimensions")
        if isinstance(scope_dims, list):
            for raw_dim in scope_dims:
                normalized = normalize_dimension_name(str(raw_dim))
                if normalized in valid_dimensions:
                    imported_dimensions.add(normalized)

    for issue in issues_list:
        if not isinstance(issue, dict):
            continue
        normalized = normalize_dimension_name(str(issue.get("dimension", "")))
        if normalized in valid_dimensions:
            imported_dimensions.add(normalized)

    for issue in review_issues:
        detail = issue.get("detail")
        if not isinstance(detail, dict):
            continue
        normalized = normalize_dimension_name(str(detail.get("dimension", "")))
        if normalized in valid_dimensions:
            imported_dimensions.add(normalized)

    for raw_dim in (assessments or {}):
        normalized = normalize_dimension_name(str(raw_dim))
        if normalized in valid_dimensions:
            imported_dimensions.add(normalized)

    return imported_dimensions


def _auto_resolve_stale_holistic(
    state: dict[str, Any],
    new_ids: set[str],
    diff: dict[str, Any],
    utc_now_fn,
    *,
    imported_dimensions: set[str] | None = None,
    full_sweep_included: bool | None = None,
) -> None:
    """Auto-resolve open holistic issues not present in the latest import."""
    scope_dimensions = {
        normalize_dimension_name(dim)
        for dim in (imported_dimensions or set())
        if isinstance(dim, str) and dim.strip()
    }
    scoped_reimport = full_sweep_included is False
    # Partial re-import with unknown dimension scope: do not auto-resolve.
    if scoped_reimport and not scope_dimensions:
        return

    def _should_resolve(issue: dict[str, Any]) -> bool:
        if issue.get("detector") not in ("review", "concerns"):
            return False
        detail = issue.get("detail")
        if not isinstance(detail, dict) or not detail.get("holistic"):
            return False
        if not scoped_reimport:
            return True
        dimension = normalize_dimension_name(str(detail.get("dimension", "")))
        return dimension in scope_dimensions

    auto_resolve_review_issues(
        state,
        new_ids=new_ids,
        diff=diff,
        note="not reported in latest holistic re-import",
        should_resolve=_should_resolve,
        utc_now_fn=utc_now_fn,
    )


def import_holistic_issues(
    issues_data: ReviewImportPayload,
    state: dict[str, Any],
    lang_name: str,
    *,
    project_root: Path | str | None = None,
    utc_now_fn=utc_now,
) -> dict[str, Any]:
    """Import holistic (codebase-wide) issues into state."""
    payload: ReviewImportEnvelope = parse_review_import_payload(
        issues_data,
        mode_name="Holistic",
    )
    issues_list = payload.issues
    assessments = payload.assessments
    reviewed_files = payload.reviewed_files
    review_scope = issues_data.get("review_scope", {})
    if not isinstance(review_scope, dict):
        review_scope = {}
    review_scope.setdefault("full_sweep_included", None)
    scope_full_sweep = review_scope.get("full_sweep_included")
    if not isinstance(scope_full_sweep, bool):
        scope_full_sweep = None
    if assessments:
        store_assessments(
            state,
            assessments,
            source="holistic",
            utc_now_fn=utc_now_fn,
        )

    _, holistic_prompts, _ = load_dimensions_for_lang(lang_name)
    valid_dimensions = {
        normalize_dimension_name(dim)
        for dim in holistic_prompts
        if isinstance(dim, str)
    }
    review_issues, skipped, dismissed_concerns = _validate_and_build_issues(
        issues_list, holistic_prompts, lang_name
    )
    imported_dimensions = _collect_imported_dimensions(
        issues_list=issues_list,
        review_issues=review_issues,
        assessments=assessments if isinstance(assessments, dict) else None,
        review_scope=review_scope,
        valid_dimensions=valid_dimensions,
    )

    # Store dismissed concern verdicts for suppression in future concern generation.
    if dismissed_concerns:
        from desloppify.engine.concerns import generate_concerns

        store = state.setdefault("concern_dismissals", {})
        now = utc_now_fn()
        # Compute current concerns to get source_issue_ids for each fingerprint.
        current_concerns = generate_concerns(state, lang_name=lang_name)
        concern_sources = {
            c.fingerprint: list(c.source_issues) for c in current_concerns
        }
        for dc in dismissed_concerns:
            fp = dc["fingerprint"]
            store[fp] = {
                "dismissed_at": now,
                "reasoning": dc.get("reasoning", ""),
                "concern_type": dc.get("concern_type", ""),
                "concern_file": dc.get("concern_file", ""),
                "source_issue_ids": concern_sources.get(fp, []),
            }

    potentials = _lang_potentials(state, lang_name)
    existing_review = potentials.get("review", 0)
    potentials["review"] = max(existing_review, HOLISTIC_POTENTIAL)

    concern_count = sum(1 for f in review_issues if f.get("detector") == "concerns")
    if concern_count:
        potentials["concerns"] = max(potentials.get("concerns", 0), concern_count)

    merge_potentials_dict: dict[str, int] = {"review": potentials.get("review", 0)}
    if potentials.get("concerns", 0) > 0:
        merge_potentials_dict["concerns"] = potentials["concerns"]

    diff = merge_scan(
        state,
        review_issues,
        options=MergeScanOptions(
            lang=lang_name,
            potentials=merge_potentials_dict,
            merge_potentials=True,
        ),
    )

    new_ids = {issue["id"] for issue in review_issues}
    _auto_resolve_stale_holistic(
        state,
        new_ids,
        diff,
        utc_now_fn,
        imported_dimensions=imported_dimensions,
        full_sweep_included=scope_full_sweep,
    )

    if skipped:
        diff["skipped"] = len(skipped)
        diff["skipped_details"] = skipped

    update_reviewed_file_cache(
        state,
        reviewed_files,
        project_root=project_root,
        utc_now_fn=utc_now_fn,
    )
    resolve_reviewed_file_coverage_issues(
        state,
        diff,
        reviewed_files,
        utc_now_fn=utc_now_fn,
    )
    update_holistic_review_cache(
        state,
        issues_list,
        lang_name=lang_name,
        review_scope=review_scope,
        utc_now_fn=utc_now_fn,
    )
    resolve_holistic_coverage_issues(state, diff, utc_now_fn=utc_now_fn)

    # Clean up dismissals whose source issues were all resolved — runs after
    # all issue mutations (merge_scan, auto_resolve, coverage resolve) so it
    # sees the final state.
    from desloppify.engine.concerns import cleanup_stale_dismissals

    cleanup_stale_dismissals(state)

    return diff


def _resolve_total_files(state: dict[str, Any], lang_name: str | None) -> int:
    """Best-effort total file count from codebase_metrics or review cache."""
    review_cache = state.get("review_cache", {})
    fallback = len(review_cache.get("files", {}))

    codebase_metrics = state.get("codebase_metrics", {})
    if not isinstance(codebase_metrics, dict):
        return fallback

    # Try language-specific metrics first, then global.
    sources = []
    if lang_name:
        lang_metrics = codebase_metrics.get(lang_name)
        if isinstance(lang_metrics, dict):
            sources.append(lang_metrics)
    sources.append(codebase_metrics)

    for source in sources:
        metric_total = source.get("total_files")
        if isinstance(metric_total, int) and metric_total > 0:
            return metric_total

    return fallback


def update_holistic_review_cache(
    state: dict[str, Any],
    issues_data: list[dict],
    *,
    lang_name: str | None = None,
    review_scope: dict[str, Any] | None = None,
    utc_now_fn=utc_now,
) -> None:
    """Store holistic review metadata in review_cache."""
    review_cache = state.setdefault("review_cache", {})
    now = utc_now_fn()
    _, holistic_prompts, _ = load_dimensions_for_lang(lang_name or "")

    valid = [
        issue
        for issue in issues_data
        if all(
            key in issue
            for key in ("dimension", "identifier", "summary", "confidence")
        )
        and issue["dimension"] in holistic_prompts
    ]

    resolved_total_files: int
    total_override = (
        review_scope.get("total_files")
        if isinstance(review_scope, dict)
        else None
    )
    if (
        isinstance(total_override, int)
        and not isinstance(total_override, bool)
        and total_override > 0
    ):
        resolved_total_files = total_override
    else:
        resolved_total_files = _resolve_total_files(state, lang_name)

    holistic_entry: dict[str, Any] = {
        "reviewed_at": now,
        "file_count_at_review": resolved_total_files,
        "issue_count": len(valid),
    }
    if isinstance(review_scope, dict):
        reviewed_files_count = review_scope.get("reviewed_files_count")
        if (
            isinstance(reviewed_files_count, int)
            and not isinstance(reviewed_files_count, bool)
            and reviewed_files_count >= 0
        ):
            holistic_entry["reviewed_files_count"] = reviewed_files_count
        full_sweep_included = review_scope.get("full_sweep_included")
        if isinstance(full_sweep_included, bool):
            holistic_entry["full_sweep_included"] = full_sweep_included

    review_cache["holistic"] = holistic_entry


def resolve_holistic_coverage_issues(
    state: dict[str, Any],
    diff: dict[str, Any],
    *,
    utc_now_fn=utc_now,
) -> None:
    """Resolve stale holistic coverage entries after successful holistic import."""
    now = utc_now_fn()
    for issue in state.get("issues", {}).values():
        if issue.get("status") != "open":
            continue
        if issue.get("detector") != "subjective_review":
            continue

        issue_id = issue.get("id", "")
        if (
            "::holistic_unreviewed" not in issue_id
            and "::holistic_stale" not in issue_id
        ):
            continue

        issue["status"] = "auto_resolved"
        issue["resolved_at"] = now
        issue["note"] = "resolved by holistic review import"
        issue["resolution_attestation"] = {
            "kind": "agent_import",
            "text": "Holistic review refreshed; coverage marker superseded",
            "attested_at": now,
            "scan_verified": False,
        }
        diff["auto_resolved"] += 1


def resolve_reviewed_file_coverage_issues(
    state: dict[str, Any],
    diff: dict[str, Any],
    reviewed_files: list[str],
    *,
    utc_now_fn=utc_now,
) -> None:
    """Resolve per-file subjective coverage markers for freshly reviewed files."""
    if not reviewed_files:
        return

    reviewed_set = {path for path in reviewed_files if isinstance(path, str) and path}
    if not reviewed_set:
        return

    now = utc_now_fn()
    for issue in state.get("issues", {}).values():
        if issue.get("status") != "open":
            continue
        if issue.get("detector") != "subjective_review":
            continue

        issue_id = issue.get("id", "")
        if "::holistic_unreviewed" in issue_id or "::holistic_stale" in issue_id:
            continue

        issue_file = issue.get("file", "")
        if issue_file not in reviewed_set:
            continue

        issue["status"] = "auto_resolved"
        issue["resolved_at"] = now
        issue["note"] = "resolved by reviewed_files cache refresh"
        issue["resolution_attestation"] = {
            "kind": "agent_import",
            "text": "Per-file review cache refreshed for this file",
            "attested_at": now,
            "scan_verified": False,
        }
        diff["auto_resolved"] += 1
