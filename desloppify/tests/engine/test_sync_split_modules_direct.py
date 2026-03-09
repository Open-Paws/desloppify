"""Direct tests for split engine plan/scoring/lifecycle helper modules."""

from __future__ import annotations

from types import SimpleNamespace

import desloppify.engine._plan._sync_context as sync_context_mod
import desloppify.engine._plan.epic_triage_dismiss as triage_dismiss_mod
import desloppify.engine._plan.reconcile_review_import as reconcile_import_mod
import desloppify.engine._plan.schema.helpers as schema_helpers_mod
import desloppify.engine._plan.sync_auto_prune as sync_auto_prune_mod
import desloppify.engine._plan.sync_workflow as sync_workflow_mod
import desloppify.engine._scoring.state_integration_subjective as scoring_subjective_mod
import desloppify.engine._work_queue.lifecycle as lifecycle_mod


def test_sync_context_helpers_cover_policy_and_fallback_paths() -> None:
    policy = SimpleNamespace(has_objective_backlog=True)
    assert sync_context_mod.has_objective_backlog({}, policy) is True

    state = {
        "issues": {
            "id1": {"status": "open", "detector": "unused", "suppressed": False},
            "id2": {"status": "fixed", "detector": "unused", "suppressed": False},
        }
    }
    assert sync_context_mod.has_objective_backlog(state, policy=None) is True
    assert sync_context_mod.is_mid_cycle({"plan_start_scores": {"strict": 75.0}}) is True
    assert sync_context_mod.is_mid_cycle({"plan_start_scores": {"reset": True}}) is False


def test_epic_triage_dismiss_moves_issues_to_skipped() -> None:
    triage = SimpleNamespace(
        dismissed_issues=[SimpleNamespace(issue_id="id1", reason="false_positive")],
        epics=[{"dismissed": ["id2"]}],
    )
    order = ["id1", "id2", "id3"]
    skipped: dict = {}

    dismissed_ids, dismiss_count = triage_dismiss_mod.dismiss_triage_issues(
        triage=triage,
        order=order,
        skipped=skipped,
        now="2026-03-09T00:00:00+00:00",
        version=7,
        scan_count=11,
    )
    assert dismiss_count == 2
    assert dismissed_ids == ["id1", "id2"]
    assert order == ["id3"]
    assert skipped["id1"]["kind"] == "triaged_out"


def test_reconcile_review_import_sync_result(monkeypatch) -> None:
    plan = {"queue_order": ["id1"]}
    state = {"issues": {}}

    monkeypatch.setattr(reconcile_import_mod, "compute_new_issue_ids", lambda _p, _s: {"id2", "id3"})
    monkeypatch.setattr(
        reconcile_import_mod,
        "sync_triage_needed",
        lambda _p, _s, policy=None: SimpleNamespace(injected=True),
    )

    result = reconcile_import_mod.sync_plan_after_review_import(plan, state, policy=None)
    assert result is not None
    assert result.new_ids == {"id2", "id3"}
    assert result.added_to_queue == ["id2", "id3"]
    assert result.triage_injected is True
    assert plan["queue_order"] == ["id1", "id2", "id3"]


def test_schema_migration_helpers_cover_legacy_cleanup() -> None:
    assert (
        schema_helpers_mod._has_synthesis_artifacts(
            queue_order=["synthesis::a"],
            skipped={},
            clusters={},
            meta={},
        )
        is True
    )

    plan = {"old": 1, "keep": 2}
    assert schema_helpers_mod._drop_legacy_plan_keys(plan, ("old", "missing")) is True
    assert plan == {"keep": 2}

    meta = {"synthesis_stages": {}, "x": 1}
    assert schema_helpers_mod._cleanup_synthesis_meta(meta) is True
    assert "synthesis_stages" not in meta

    cluster = {"action_steps": ["short", "Sentence one. Additional detail here."]}
    changed = schema_helpers_mod._migrate_action_steps_to_v8(cluster)
    assert changed is True
    assert isinstance(cluster["action_steps"][0], dict)


def test_sync_auto_prune_removes_stale_auto_clusters_and_cleans_overrides() -> None:
    plan = {
        "overrides": {"id1": {"cluster": "auto-a", "updated_at": ""}},
        "active_cluster": "auto-a",
    }
    issues = {"id1": {"status": "fixed"}}
    clusters = {
        "auto-a": {
            "auto": True,
            "cluster_key": "stale",
            "issue_ids": ["id1"],
        },
        "manual": {"auto": False, "issue_ids": []},
    }

    changes = sync_auto_prune_mod.prune_stale_clusters(
        plan,
        issues,
        clusters,
        active_auto_keys=set(),
        now="2026-03-09T00:00:00+00:00",
    )
    assert changes == 1
    assert "auto-a" not in clusters
    assert plan["overrides"]["id1"]["cluster"] is None
    assert plan["active_cluster"] is None


def test_sync_workflow_helpers_inject_expected_items(monkeypatch) -> None:
    plan = {"queue_order": []}
    state = {"issues": {"id1": {"status": "open", "detector": "unused"}}}
    policy = SimpleNamespace(unscored_ids=set(), has_objective_backlog=True)

    r1 = sync_workflow_mod.sync_score_checkpoint_needed(plan, state, policy=policy)
    assert r1.injected == ["workflow::score-checkpoint"]

    plan = {"queue_order": []}
    r2 = sync_workflow_mod.sync_create_plan_needed(plan, state, policy=policy)
    assert r2.injected == ["workflow::create-plan"]

    plan = {"queue_order": []}
    r3 = sync_workflow_mod.sync_import_scores_needed(plan, state, assessment_mode="issues_only")
    assert r3.injected == ["workflow::import-scores"]

    plan = {"queue_order": []}
    r4 = sync_workflow_mod.sync_communicate_score_needed(
        plan,
        state,
        policy=SimpleNamespace(unscored_ids={"subjective::x"}, has_objective_backlog=True),
        scores_just_imported=True,
    )
    assert r4.injected == ["workflow::communicate-score"]

    monkeypatch.setattr(sync_workflow_mod.stale_policy_mod, "current_unscored_ids", lambda *_a, **_k: {"s"})
    assert sync_workflow_mod._no_unscored(state, policy=None) is False


def test_sync_workflow_injection_removes_stale_skip_entries() -> None:
    plan = {
        "queue_order": [],
        "skipped": {
            "workflow::create-plan": {
                "issue_id": "workflow::create-plan",
                "kind": "temporary",
                "skipped_at_scan": 0,
            }
        },
    }
    state = {"issues": {"id1": {"status": "open", "detector": "unused"}}}
    policy = SimpleNamespace(unscored_ids=set(), has_objective_backlog=True)

    result = sync_workflow_mod.sync_create_plan_needed(plan, state, policy=policy)

    assert result.injected == ["workflow::create-plan"]
    assert "workflow::create-plan" in plan["queue_order"]
    assert "workflow::create-plan" not in plan["skipped"]


def test_subjective_integrity_helpers_apply_penalty_threshold(monkeypatch) -> None:
    monkeypatch.setattr(scoring_subjective_mod, "matches_target_score", lambda score, target: score >= target)

    assessments = {
        "naming_quality": {"score": 95},
        "design_coherence": {"score": 96},
        "error_consistency": {"score": 60},
    }
    adjusted, meta = scoring_subjective_mod._apply_subjective_integrity_policy(
        assessments,
        target=95,
    )
    assert meta["status"] == "penalized"
    assert set(meta["reset_dimensions"]) == {"design_coherence", "naming_quality"}
    assert adjusted["naming_quality"]["score"] == 0.0

    assert scoring_subjective_mod._coerce_subjective_score({"score": "101"}) == 100.0
    assert scoring_subjective_mod._normalize_integrity_target(120.0) == 100.0
    assert scoring_subjective_mod._normalize_integrity_target(None) is None


def test_lifecycle_filter_respects_initial_reviews_triage_and_endgame_rules() -> None:
    initial_items = [
        {"kind": "subjective_dimension", "id": "subjective::naming", "initial_review": True},
        {"kind": "issue", "id": "unused::a", "detector": "unused"},
    ]
    filtered_initial = lifecycle_mod.apply_lifecycle_filter(initial_items)
    assert filtered_initial == [initial_items[0]]

    triage_and_objective = [
        {"kind": "workflow_stage", "id": "triage::observe"},
        {"kind": "issue", "id": "unused::a", "detector": "unused"},
        {"kind": "subjective_dimension", "id": "subjective::naming", "initial_review": False},
    ]
    filtered_mid = lifecycle_mod.apply_lifecycle_filter(triage_and_objective)
    assert all(not str(item.get("id", "")).startswith("triage::") for item in filtered_mid)
    assert all(item.get("kind") != "subjective_dimension" for item in filtered_mid)

    endgame_items = [
        {"kind": "workflow_stage", "id": "triage::observe"},
        {"kind": "workflow_action", "id": "workflow::create-plan"},
    ]
    filtered_endgame = lifecycle_mod.apply_lifecycle_filter(endgame_items)
    assert filtered_endgame == endgame_items


def test_lifecycle_filter_treats_clusters_as_objective() -> None:
    """Clusters containing objective issues should prevent triage from forcing."""
    items = [
        {"kind": "workflow_stage", "id": "triage::observe"},
        {"kind": "cluster", "id": "auto/complexity_reduction", "detector": "complexity"},
    ]
    filtered = lifecycle_mod.apply_lifecycle_filter(items)
    # Cluster is objective work — triage should be hidden, cluster shown
    assert any(item["kind"] == "cluster" for item in filtered)
    assert all(not str(item.get("id", "")).startswith("triage::") for item in filtered)


def test_lifecycle_filter_forces_triage_when_only_subjective_clusters() -> None:
    """When only subjective clusters remain, triage should still be forced."""
    items = [
        {"kind": "workflow_stage", "id": "triage::observe"},
        {"kind": "cluster", "id": "auto/subjective_review", "detector": "subjective_assessment"},
    ]
    filtered = lifecycle_mod.apply_lifecycle_filter(items)
    # Subjective cluster is not objective — triage should be forced
    assert any(str(item.get("id", "")).startswith("triage::") for item in filtered)
