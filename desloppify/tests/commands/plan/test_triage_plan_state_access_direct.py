"""Direct tests for triage plan-state access helpers."""

from __future__ import annotations

from typing import get_type_hints

import desloppify.app.commands.plan.triage.plan_state_access as plan_state_access_mod
from desloppify.app.commands.plan.triage.plan_state_access import (
    ensure_cluster_map,
    ensure_execution_log,
    ensure_queue_order,
    ensure_skipped_map,
    ensure_triage_meta,
    normalized_issue_id_list,
)
from desloppify.engine._work_queue.types import PlanClusterRef, SerializedQueueItem
from desloppify.engine.plan_state import ActionStep, Cluster


def test_plan_state_access_initializes_missing_collections() -> None:
    plan: dict[str, object] = {}

    queue_order = ensure_queue_order(plan)
    skipped = ensure_skipped_map(plan)
    clusters = ensure_cluster_map(plan)
    meta = ensure_triage_meta(plan)
    log = ensure_execution_log(plan)

    assert queue_order == []
    assert skipped == {}
    assert clusters == {}
    assert meta == {}
    assert log == []
    assert plan["queue_order"] is queue_order
    assert plan["skipped"] is skipped
    assert plan["clusters"] is clusters
    assert plan["epic_triage_meta"] is meta
    assert plan["execution_log"] is log


def test_normalized_issue_id_list_filters_non_strings() -> None:
    assert normalized_issue_id_list(["a", 123, None, "b"]) == ["a", "b"]
    assert normalized_issue_id_list("a") == []


def test_plan_state_access_reuses_existing_storage_and_filters_execution_log() -> None:
    queue_order = ["a"]
    skipped = {"issue": {"note": "keep"}}
    clusters = {"cluster": {"issue_ids": ["a"]}}
    meta = {"stage": "observe"}
    raw_log: list[object] = [{"kind": "resolve"}, "skip-me", {"kind": "note"}]
    plan = {
        "queue_order": queue_order,
        "skipped": skipped,
        "clusters": clusters,
        "epic_triage_meta": meta,
        "execution_log": raw_log,
    }

    assert plan_state_access_mod.ensure_queue_order(plan) is queue_order
    assert plan_state_access_mod.ensure_skipped_map(plan) is skipped
    assert plan_state_access_mod.ensure_cluster_map(plan) is clusters
    assert plan_state_access_mod.ensure_triage_meta(plan) is meta

    normalized_log = plan_state_access_mod.ensure_execution_log(plan)

    assert normalized_log == [{"kind": "resolve"}, {"kind": "note"}]
    assert plan["execution_log"] is normalized_log


def test_plan_state_access_exports_expected_helpers() -> None:
    assert "ensure_queue_order" in plan_state_access_mod.__all__
    assert "ensure_skipped_map" in plan_state_access_mod.__all__
    assert "ensure_cluster_map" in plan_state_access_mod.__all__
    assert "ensure_triage_meta" in plan_state_access_mod.__all__
    assert "ensure_execution_log" in plan_state_access_mod.__all__
    assert "normalized_issue_id_list" in plan_state_access_mod.__all__


def test_plan_schema_and_queue_types_cover_runtime_cluster_payloads() -> None:
    action_step_hints = get_type_hints(ActionStep)
    cluster_hints = get_type_hints(Cluster)
    plan_cluster_hints = get_type_hints(PlanClusterRef)
    serialized_queue_hints = get_type_hints(SerializedQueueItem)

    assert "effort" in action_step_hints
    assert "depends_on_clusters" in cluster_hints
    assert "action_steps" in plan_cluster_hints
    assert "action_steps" in serialized_queue_hints
