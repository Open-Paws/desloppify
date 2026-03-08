"""Direct tests for review batch core helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from desloppify.app.commands.review.batch.core_normalize import normalize_batch_result
from desloppify.app.commands.review.batch.merge import merge_batch_results
from desloppify.app.commands.review.batch.prompt_template import render_batch_prompt
from desloppify.app.commands.review.batch.scoring import (
    DimensionMergeScorer,
    ScoreInputs,
)
from desloppify.intelligence.review.feedback_contract import (
    LOW_SCORE_ISSUE_THRESHOLD,
    max_batch_issues_for_dimension_count,
)

_ABSTRACTION_SUB_AXES = (
    "abstraction_leverage",
    "indirection_cost",
    "interface_honesty",
)
_ABSTRACTION_COMPONENT_NAMES = {
    "abstraction_leverage": "Abstraction leverage",
    "indirection_cost": "Indirection cost",
    "interface_honesty": "Interface honesty",
}


def _merge(batch_results: list[dict]) -> dict[str, object]:
    return merge_batch_results(
        batch_results,
        abstraction_sub_axes=_ABSTRACTION_SUB_AXES,
        abstraction_component_names=_ABSTRACTION_COMPONENT_NAMES,
    )


def test_merge_penalizes_high_scores_when_severe_issues_exist():
    merged = _merge(
        [
            {
                "assessments": {"high_level_elegance": 92.0},
                "dimension_notes": {
                    "high_level_elegance": {
                        "evidence": ["layering is inconsistent around shared core"],
                        "impact_scope": "codebase",
                        "fix_scope": "architectural_change",
                        "confidence": "high",
                        "issues_preventing_higher_score": "major refactor required",
                    }
                },
                "issues": [
                    {
                        "dimension": "high_level_elegance",
                        "identifier": "core_boundary_drift",
                        "summary": "boundary drift across critical modules",
                        "confidence": "high",
                        "impact_scope": "codebase",
                        "fix_scope": "architectural_change",
                    }
                ],
                "quality": {},
            }
        ]
    )
    assert merged["assessments"]["high_level_elegance"] == 75.7
    quality = merged.get("review_quality", {})
    assert quality["issue_pressure"] == 4.08
    assert quality["dimensions_with_issues"] == 1


def test_merge_keeps_scores_without_issues():
    merged = _merge(
        [
            {
                "assessments": {"mid_level_elegance": 88.0},
                "dimension_notes": {
                    "mid_level_elegance": {
                        "evidence": ["handoff seams are mostly coherent"],
                        "impact_scope": "module",
                        "fix_scope": "single_edit",
                        "confidence": "medium",
                        "issues_preventing_higher_score": "minor seam churn remains",
                    }
                },
                "issues": [],
                "quality": {},
            }
        ]
    )
    assert merged["assessments"]["mid_level_elegance"] == 88.0


def test_batch_prompt_requires_score_and_issue_consistency():
    prompt = render_batch_prompt(
        repo_root=Path("/repo"),
        packet_path=Path("/repo/.desloppify/review_packets/p.json"),
        batch_index=0,
        batch={
            "name": "high_level_elegance",
            "dimensions": ["high_level_elegance"],
            "why": "test",
            "files_to_read": ["core.py", "scan.py"],
        },
    )
    assert "Seed files (start here):" in prompt
    assert "Start from the seed files" in prompt
    assert "blind packet's `system_prompt`" in prompt
    assert "Evaluate ONLY listed files and ONLY listed dimensions" not in prompt


def test_dimension_merge_scorer_penalizes_higher_pressure():
    scorer = DimensionMergeScorer()
    low = scorer.score_dimension(
        ScoreInputs(
            weighted_mean=92.0,
            floor=90.0,
            issue_pressure=1.0,
            issue_count=1,
        )
    )
    high = scorer.score_dimension(
        ScoreInputs(
            weighted_mean=92.0,
            floor=90.0,
            issue_pressure=4.08,
            issue_count=1,
        )
    )
    assert low.final_score > high.final_score


def test_dimension_merge_scorer_penalizes_additional_issues():
    scorer = DimensionMergeScorer()
    one_issue = scorer.score_dimension(
        ScoreInputs(
            weighted_mean=92.0,
            floor=90.0,
            issue_pressure=2.0,
            issue_count=1,
        )
    )
    three_issues = scorer.score_dimension(
        ScoreInputs(
            weighted_mean=92.0,
            floor=90.0,
            issue_pressure=2.0,
            issue_count=3,
        )
    )
    assert one_issue.final_score > three_issues.final_score


def test_merge_batch_results_merges_same_identifier_issues():
    merged = _merge(
        [
            {
                "assessments": {"logic_clarity": 70.0},
                "dimension_notes": {
                    "logic_clarity": {
                        "evidence": ["predicate mismatch in task filtering"],
                        "impact_scope": "module",
                        "fix_scope": "single_edit",
                        "confidence": "medium",
                        "issues_preventing_higher_score": "",
                    }
                },
                "issues": [
                    {
                        "dimension": "logic_clarity",
                        "identifier": "processing_filter_predicate_mismatch",
                        "summary": "Mismatch in processing predicates",
                        "related_files": ["src/a.ts", "src/b.ts"],
                        "evidence": ["branch A uses OR"],
                        "suggestion": "align predicates",
                        "confidence": "high",
                        "impact_scope": "module",
                        "fix_scope": "single_edit",
                    }
                ],
                "quality": {},
            },
            {
                "assessments": {"logic_clarity": 65.0},
                "dimension_notes": {
                    "logic_clarity": {
                        "evidence": ["task filtering diverges"],
                        "impact_scope": "module",
                        "fix_scope": "single_edit",
                        "confidence": "medium",
                        "issues_preventing_higher_score": "",
                    }
                },
                "issues": [
                    {
                        "dimension": "logic_clarity",
                        "identifier": "processing_filter_predicate_mismatch",
                        "summary": "Processing predicate mismatch across hooks",
                        "related_files": ["src/b.ts", "src/c.ts"],
                        "evidence": ["branch B uses AND"],
                        "suggestion": "create shared predicate helper",
                        "confidence": "high",
                        "impact_scope": "module",
                        "fix_scope": "single_edit",
                    }
                ],
                "quality": {},
            },
        ]
    )
    issues = merged["issues"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue["identifier"] == "processing_filter_predicate_mismatch"
    assert issue["summary"] == "Processing predicate mismatch across hooks"
    assert set(issue["related_files"]) == {"src/a.ts", "src/b.ts", "src/c.ts"}
    assert set(issue["evidence"]) == {"branch A uses OR", "branch B uses AND"}


def test_normalize_batch_result_rejects_low_score_without_same_dimension_issue():
    with pytest.raises(ValueError) as exc:
        normalize_batch_result(
            payload={
                "assessments": {"logic_clarity": LOW_SCORE_ISSUE_THRESHOLD - 10.0},
                "dimension_notes": {
                    "logic_clarity": {
                        "evidence": ["branching logic diverges across handlers"],
                        "impact_scope": "module",
                        "fix_scope": "single_edit",
                        "confidence": "high",
                        "issues_preventing_higher_score": "",
                    }
                },
                "issues": [],
            },
            allowed_dims={"logic_clarity"},
            max_batch_issues=max_batch_issues_for_dimension_count(1),
            abstraction_sub_axes=_ABSTRACTION_SUB_AXES,
        )
    assert "low-score dimensions must include at least one explicit issue" in str(exc.value)


def test_normalize_batch_result_accepts_low_score_with_same_dimension_issue():
    assessments, issues, _notes, _judgment, _quality = normalize_batch_result(
        payload={
            "assessments": {"logic_clarity": LOW_SCORE_ISSUE_THRESHOLD - 10.0},
            "dimension_notes": {
                "logic_clarity": {
                    "evidence": ["branching logic diverges across handlers"],
                    "impact_scope": "module",
                    "fix_scope": "single_edit",
                    "confidence": "high",
                    "issues_preventing_higher_score": "",
                }
            },
            "issues": [
                {
                    "dimension": "logic_clarity",
                    "identifier": "divergent_predicates",
                    "summary": "Predicate branches diverge in equivalent handlers",
                    "related_files": ["src/a.ts", "src/b.ts"],
                    "evidence": ["handler A uses OR, handler B uses AND"],
                    "suggestion": "extract a shared predicate helper and reuse it",
                    "confidence": "high",
                    "impact_scope": "module",
                    "fix_scope": "single_edit",
                }
            ],
        },
        allowed_dims={"logic_clarity"},
        max_batch_issues=max_batch_issues_for_dimension_count(1),
        abstraction_sub_axes=_ABSTRACTION_SUB_AXES,
    )
    assert assessments["logic_clarity"] == LOW_SCORE_ISSUE_THRESHOLD - 10.0
    assert len(issues) == 1


def test_normalize_batch_result_accepts_legacy_findings_alias():
    assessments, issues, _notes, _judgment, _quality = normalize_batch_result(
        payload={
            "assessments": {"logic_clarity": 80.0},
            "dimension_notes": {
                "logic_clarity": {
                    "evidence": ["legacy alias path"],
                    "impact_scope": "module",
                    "fix_scope": "single_edit",
                    "confidence": "medium",
                    "issues_preventing_higher_score": "",
                }
            },
            "findings": [
                {
                    "dimension": "logic_clarity",
                    "identifier": "legacy_findings_alias",
                    "summary": "Legacy findings key still normalizes",
                    "related_files": ["src/a.ts"],
                    "evidence": ["payload used findings key"],
                    "suggestion": "continue importing via issues key",
                    "confidence": "medium",
                    "impact_scope": "module",
                    "fix_scope": "single_edit",
                }
            ],
        },
        allowed_dims={"logic_clarity"},
        max_batch_issues=max_batch_issues_for_dimension_count(1),
        abstraction_sub_axes=_ABSTRACTION_SUB_AXES,
    )
    assert assessments["logic_clarity"] == 80.0
    assert len(issues) == 1
    assert issues[0]["identifier"] == "legacy_findings_alias"


def test_normalize_batch_result_accepts_legacy_unreported_risk_key():
    _assessments, _issues, notes, _judgment, _quality = normalize_batch_result(
        payload={
            "assessments": {"logic_clarity": 90.0},
            "dimension_notes": {
                "logic_clarity": {
                    "evidence": ["legacy payload compatibility path"],
                    "impact_scope": "module",
                    "fix_scope": "single_edit",
                    "confidence": "medium",
                    "unreported_risk": "legacy note still provided",
                }
            },
            "issues": [
                {
                    "dimension": "logic_clarity",
                    "identifier": "legacy_note_path",
                    "summary": "Legacy note field still accepted",
                    "related_files": ["src/a.ts", "src/b.ts"],
                    "evidence": ["legacy payload uses unreported_risk"],
                    "suggestion": "continue normalizing onto the new field",
                    "confidence": "medium",
                    "impact_scope": "module",
                    "fix_scope": "single_edit",
                }
            ],
        },
        allowed_dims={"logic_clarity"},
        max_batch_issues=max_batch_issues_for_dimension_count(1),
        abstraction_sub_axes=_ABSTRACTION_SUB_AXES,
    )
    assert (
        notes["logic_clarity"]["issues_preventing_higher_score"]
        == "legacy note still provided"
    )
