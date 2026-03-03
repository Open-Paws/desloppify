"""Merge and dedupe logic for holistic review batch outputs."""

from __future__ import annotations

from typing import Any

from .batch_core import (
    _accumulate_batch_scores,
    _accumulate_batch_quality,
    _compute_abstraction_components,
    _compute_merged_assessments,
    _issue_identity_key,
    _issue_pressure_by_dimension,
    assessment_weight,
)
from desloppify.intelligence.review.feedback_contract import (
    REVIEW_QUALITY_HIGH_SCORE_MISSING_ISSUES_KEY,
)
from desloppify.intelligence.review.issue_merge import (
    merge_list_fields,
    normalize_word_set,
    pick_longer_text,
    track_merged_from,
)


def _merge_issue_payload(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    merge_list_fields(existing, incoming, ("related_files", "evidence"))
    pick_longer_text(existing, incoming, "summary")
    pick_longer_text(existing, incoming, "suggestion")
    track_merged_from(existing, str(incoming.get("identifier", "")).strip())


def _should_merge_issues(existing: dict[str, Any], incoming: dict[str, Any]) -> bool:
    existing_summary = normalize_word_set(str(existing.get("summary", "")))
    incoming_summary = normalize_word_set(str(incoming.get("summary", "")))
    summary_similarity_signal = False
    if existing_summary and incoming_summary:
        overlap = len(existing_summary & incoming_summary)
        union = len(existing_summary | incoming_summary)
        summary_similarity_signal = bool(union and overlap / union >= 0.45)

    existing_files = set(existing.get("related_files", []))
    incoming_files = set(incoming.get("related_files", []))
    file_overlap_signal = bool(existing_files and incoming_files and (existing_files & incoming_files))

    existing_identifier = str(existing.get("identifier", "")).strip()
    incoming_identifier = str(incoming.get("identifier", "")).strip()
    identifier_signal = bool(
        existing_identifier and incoming_identifier and existing_identifier == incoming_identifier
    )

    corroborating_signals = (
        int(summary_similarity_signal)
        + int(file_overlap_signal)
        + int(identifier_signal)
    )
    if identifier_signal and (summary_similarity_signal or file_overlap_signal):
        return True
    return corroborating_signals >= 2


def _append_batch_issues(
    result: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    for issue in result.get("issues", []):
        if isinstance(issue, dict):
            issues.append(issue)


def _merge_issue_group(group: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge one dedupe-key group using transitive connected components."""
    if len(group) <= 1:
        return list(group)

    visited: set[int] = set()
    components: list[list[int]] = []

    for start in range(len(group)):
        if start in visited:
            continue
        stack = [start]
        component: list[int] = []
        visited.add(start)
        while stack:
            node = stack.pop()
            component.append(node)
            source = group[node]
            for probe in range(len(group)):
                if probe in visited:
                    continue
                target = group[probe]
                if _should_merge_issues(source, target) or _should_merge_issues(
                    target, source
                ):
                    visited.add(probe)
                    stack.append(probe)
        components.append(sorted(component))

    merged_components: list[dict[str, Any]] = []
    for indexes in sorted(components, key=lambda ids: ids[0]):
        base = group[indexes[0]]
        for idx in indexes[1:]:
            _merge_issue_payload(base, group[idx])
        merged_components.append(base)
    return merged_components


def _merge_issues_transitively(
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        grouped.setdefault(_issue_identity_key(issue), []).append(issue)

    merged: list[dict[str, Any]] = []
    for group in grouped.values():
        merged.extend(_merge_issue_group(group))
    return merged


def merge_batch_results(
    batch_results: list[dict[str, Any]],
    *,
    abstraction_sub_axes: tuple[str, ...],
    abstraction_component_names: dict[str, str],
) -> dict[str, object]:
    """Deterministically merge assessments/issues across batch outputs."""
    score_buckets: dict[str, list[tuple[float, float]]] = {}
    score_raw_by_dim: dict[str, list[float]] = {}
    all_issues: list[dict[str, Any]] = []
    merged_dimension_notes: dict[str, dict[str, Any]] = {}
    coverage_values: list[float] = []
    evidence_density_values: list[float] = []
    high_score_missing_issue_note_total = 0.0
    abstraction_axis_scores: dict[str, list[tuple[float, float]]] = {
        axis: [] for axis in abstraction_sub_axes
    }

    for result in batch_results:
        _accumulate_batch_scores(
            result,
            score_buckets=score_buckets,
            score_raw_by_dim=score_raw_by_dim,
            merged_dimension_notes=merged_dimension_notes,
            abstraction_axis_scores=abstraction_axis_scores,
            abstraction_sub_axes=abstraction_sub_axes,
        )
        _append_batch_issues(result, all_issues)
        high_score_missing_issue_note_total += _accumulate_batch_quality(
            result,
            coverage_values=coverage_values,
            evidence_density_values=evidence_density_values,
        )

    merged_issues = _merge_issues_transitively(all_issues)
    issue_pressure_by_dim, issue_count_by_dim = _issue_pressure_by_dimension(
        merged_issues,
        dimension_notes=merged_dimension_notes,
    )

    merged_assessments = _compute_merged_assessments(
        score_buckets, score_raw_by_dim, issue_pressure_by_dim, issue_count_by_dim
    )

    merged_assessment_payload: dict[str, float | dict[str, object]] = {
        key: value for key, value in merged_assessments.items()
    }
    component_scores = _compute_abstraction_components(
        merged_assessments,
        abstraction_axis_scores,
        abstraction_sub_axes=abstraction_sub_axes,
        abstraction_component_names=abstraction_component_names,
    )
    if component_scores is not None:
        merged_assessment_payload["abstraction_fitness"] = {
            "score": merged_assessments["abstraction_fitness"],
            "components": list(component_scores),
            "component_scores": component_scores,
        }

    return {
        "assessments": merged_assessment_payload,
        "dimension_notes": merged_dimension_notes,
        "issues": merged_issues,
        "review_quality": {
            "batch_count": len(batch_results),
            "dimension_coverage": round(
                sum(coverage_values) / max(len(coverage_values), 1),
                3,
            ),
            "evidence_density": round(
                sum(evidence_density_values) / max(len(evidence_density_values), 1),
                3,
            ),
            REVIEW_QUALITY_HIGH_SCORE_MISSING_ISSUES_KEY: int(
                high_score_missing_issue_note_total
            ),
            "issue_pressure": round(sum(issue_pressure_by_dim.values()), 3),
            "dimensions_with_issues": len(issue_count_by_dim),
        },
    }


__all__ = ["assessment_weight", "merge_batch_results"]
