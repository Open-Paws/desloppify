"""Tests for canonical triage snapshot and progress derivation."""

from __future__ import annotations

from desloppify.engine.plan_triage import (
    active_triage_issue_ids,
    build_triage_snapshot,
    compute_triage_progress,
    triage_coverage,
    undispositioned_triage_issue_ids,
)


def _review_state(*issue_ids: str) -> dict:
    return {
        "issues": {
            issue_id: {
                "status": "open",
                "detector": "review",
                "summary": issue_id,
                "detail": {"dimension": "naming"},
            }
            for issue_id in issue_ids
        }
    }


def test_build_triage_snapshot_empty_plan_is_inactive() -> None:
    snapshot = build_triage_snapshot({"queue_order": [], "epic_triage_meta": {}}, {"issues": {}})

    assert snapshot.cycle_active is False
    assert snapshot.is_triage_stale is False
    assert snapshot.new_since_triage_ids == frozenset()
    assert snapshot.undispositioned_ids == frozenset()


def test_build_triage_snapshot_excludes_frozen_active_ids_from_new_since_triage() -> None:
    plan = {
        "queue_order": ["triage::observe"],
        "epic_triage_meta": {
            "triaged_ids": ["review::old"],
            "active_triage_issue_ids": ["review::frozen"],
            "triage_stages": {"observe": {"report": "done"}},
        },
    }
    state = _review_state("review::old", "review::frozen", "review::new")

    snapshot = build_triage_snapshot(plan, state)

    assert snapshot.new_since_triage_ids == frozenset({"review::new"})
    assert snapshot.is_triage_stale is True


def test_build_triage_snapshot_tracks_undispositioned_and_coverage_consistently() -> None:
    plan = {
        "queue_order": ["triage::organize"],
        "clusters": {
            "cluster-a": {
                "issue_ids": ["review::r1"],
                "action_steps": [{"title": "Fix", "issue_refs": ["review::r1"]}],
            }
        },
        "skipped": {"review::r2": {"kind": "temporary"}},
        "epic_triage_meta": {
            "active_triage_issue_ids": ["review::r1", "review::r2", "review::r3"],
            "triage_stages": {
                "observe": {"report": "obs", "confirmed_at": "2026-03-12T10:00:00Z"},
                "reflect": {"report": "ref", "confirmed_at": "2026-03-12T10:05:00Z"},
            },
        },
    }
    state = _review_state("review::r1", "review::r2", "review::r3")

    snapshot = build_triage_snapshot(plan, state)
    organized, total, _clusters = triage_coverage(plan, open_review_ids=set(snapshot.frozen_issue_ids))

    assert snapshot.undispositioned_ids == frozenset({"review::r3"})
    assert snapshot.organized_count == organized
    assert snapshot.total_in_scope == total
    assert snapshot.frozen_issue_ids == frozenset(active_triage_issue_ids(plan, state))
    assert snapshot.undispositioned_ids == frozenset(undispositioned_triage_issue_ids(plan, state))


def test_compute_triage_progress_blocks_enrich_until_organize_confirmed() -> None:
    progress = compute_triage_progress(
        {
            "observe": {"report": "obs", "confirmed_at": "2026-03-12T10:00:00Z"},
            "reflect": {"report": "ref", "confirmed_at": "2026-03-12T10:05:00Z"},
            "organize": {"report": "org"},
        }
    )

    assert progress.current_stage is None
    assert progress.next_command == "desloppify plan triage --confirm organize"
    assert "blocked until Defer contradictions, cluster, & prioritize is confirmed" in str(
        progress.blocked_reason
    )
