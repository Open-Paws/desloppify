"""Focused tests for plan schema migration helpers."""

from __future__ import annotations

import desloppify.engine._plan.schema.migrations as migrations


def test_ensure_container_types_sets_defaults_and_renames_keys() -> None:
    plan = {
        "queue_order": "bad",
        "deferred": None,
        "skipped": [],
        "clusters": [],
        "epic_triage_meta": {"finding_snapshot_hash": "abc"},
        "uncommitted_findings": ["x"],
    }

    migrations.ensure_container_types(plan)

    assert isinstance(plan["queue_order"], list)
    assert isinstance(plan["deferred"], list)
    assert isinstance(plan["skipped"], dict)
    assert isinstance(plan["clusters"], dict)
    assert plan["epic_triage_meta"]["issue_snapshot_hash"] == "abc"
    assert "finding_snapshot_hash" not in plan["epic_triage_meta"]
    assert plan["uncommitted_issues"] == ["x"]
    assert plan["commit_tracking_branch"] is None


def test_migrate_synthesis_to_triage_renames_ids_meta_and_cluster_fields() -> None:
    plan = {
        "queue_order": ["synthesis::a", "other"],
        "skipped": {
            "synthesis::b": {"issue_id": "synthesis::b", "kind": "synthesized_out"}
        },
        "epic_synthesis_meta": {
            "synthesis_stages": {"observe": {}},
            "synthesized_ids": ["id1"],
        },
        "clusters": {
            "c": {"synthesis_version": 4},
        },
    }

    migrations.migrate_synthesis_to_triage(plan)

    assert plan["queue_order"][0] == "triage::a"
    assert "triage::b" in plan["skipped"]
    assert plan["skipped"]["triage::b"]["kind"] == "triaged_out"
    assert "epic_synthesis_meta" not in plan
    assert plan["epic_triage_meta"]["triage_stages"] == {"observe": {}}
    assert plan["epic_triage_meta"]["triaged_ids"] == ["id1"]
    assert plan["clusters"]["c"]["triage_version"] == 4


def test_upgrade_plan_to_v7_runs_legacy_cleanup() -> None:
    plan = {
        "version": 5,
        "queue_order": ["synthesis::legacy"],
        "deferred": ["issue-1"],
        "skipped": {},
        "clusters": {"c": {"synthesis_version": 1}},
        "epics": {},
        "epic_synthesis_meta": {"synthesized_ids": ["x"]},
        "pending_plan_gate": True,
        "uncommitted_findings": ["x"],
    }
    changed = migrations.upgrade_plan_to_v7(plan)

    assert changed is True
    assert plan["version"] == migrations.V7_SCHEMA_VERSION
    assert "epics" not in plan
    assert "epic_synthesis_meta" not in plan
    assert "pending_plan_gate" not in plan
    assert "uncommitted_findings" not in plan
    assert "deferred" in plan and plan["deferred"] == []
