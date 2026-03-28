"""Direct coverage tests for work-queue ranking output helpers."""

from __future__ import annotations

import desloppify.engine._work_queue.ranking_output as output_mod


def test_subjective_score_value_uses_detail_strict_score_for_dimension_items() -> None:
    value = output_mod.subjective_score_value(
        {
            "kind": "subjective_dimension",
            "subjective_score": 88,
            "detail": {"strict_score": "72.5"},
        }
    )

    assert value == 72.5


def test_subjective_score_value_falls_back_to_default_for_bad_values() -> None:
    assert output_mod.subjective_score_value({"subjective_score": "bad"}) == 100.0
    assert output_mod.subjective_score_value({"subjective_score": None}) == 100.0


def test_item_explain_for_workflow_stage_and_cluster(monkeypatch) -> None:
    monkeypatch.setattr(output_mod, "workflow_stage_name", lambda _item: "observe")

    stage = output_mod.item_explain(
        {
            "kind": "workflow_stage",
            "is_blocked": True,
            "blocked_by": ["workflow::x"],
        }
    )
    assert stage["kind"] == "workflow_stage"
    assert stage["stage"] == "observe"
    assert stage["is_blocked"] is True

    cluster = output_mod.item_explain(
        {
            "kind": "cluster",
            "estimated_impact": 1.2,
            "action_type": "refactor",
            "member_count": 4,
        }
    )
    assert cluster["kind"] == "cluster"
    assert cluster["member_count"] == 4
    assert cluster["ranking_factors"] == ["action_type asc", "member_count desc", "id asc"]


def test_item_explain_for_issue_variants_includes_expected_fields() -> None:
    review = output_mod.item_explain(
        {
            "kind": "issue",
            "confidence": "high",
            "is_review": True,
            "review_weight": 3.4,
            "estimated_impact": 7.8,
            "detail": {"count": 5},
            "id": "review::abc",
        }
    )
    assert review["kind"] == "issue"
    assert review["review_weight"] == 3.4
    assert "review_weight desc" in review["ranking_factors"]

    subjective = output_mod.item_explain(
        {
            "kind": "issue",
            "is_subjective": True,
            "estimated_impact": 9.1,
            "subjective_score": 42,
            "id": "subjective::naming",
        }
    )
    assert subjective["kind"] == "issue"
    assert subjective["subjective_score"] == 42.0
    assert "subjective_score asc" in subjective["ranking_factors"]
    assert subjective["policy"].startswith("Sorted by dimension impact")


def test_group_queue_items_groups_by_requested_key() -> None:
    items = [
        {
            "id": "a",
            "file": "src/a.ts",
            "detector": "smells",
            "plan_cluster": {"name": "cluster/a"},
        },
        {
            "id": "b",
            "file": "src/b.ts",
            "detector": "deps",
            "plan_cluster": None,
        },
    ]

    by_file = output_mod.group_queue_items(items, "file")
    by_detector = output_mod.group_queue_items(items, "detector")
    by_cluster = output_mod.group_queue_items(items, "cluster")
    default = output_mod.group_queue_items(items, "anything")

    assert sorted(by_file) == ["src/a.ts", "src/b.ts"]
    assert sorted(by_detector) == ["deps", "smells"]
    assert sorted(by_cluster) == ["(unclustered)", "cluster/a"]
    assert list(default.keys()) == ["items"]
