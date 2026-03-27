from __future__ import annotations

from desloppify.base.subjective_dimensions import DISPLAY_NAMES
from desloppify.engine._plan.operations.lifecycle import purge_ids
from desloppify.engine._plan.refresh_lifecycle import (
    LIFECYCLE_PHASE_REVIEW_INITIAL,
    LIFECYCLE_PHASE_WORKFLOW_POSTFLIGHT,
    current_lifecycle_phase,
    mark_postflight_scan_completed,
)
from desloppify.engine._plan.schema import empty_plan
from desloppify.engine._plan.sync import reconcile_plan
from desloppify.engine._work_queue.snapshot import build_queue_snapshot


def _placeholder_state() -> dict:
    display = DISPLAY_NAMES["naming_quality"]
    return {
        "issues": {},
        "work_items": {},
        "dimension_scores": {
            display: {
                "score": 0,
                "strict": 0,
                "failing": 0,
                "checks": 0,
                "detectors": {
                    "subjective_assessment": {
                        "placeholder": True,
                        "dimension_key": "naming_quality",
                    }
                },
            }
        },
        "subjective_assessments": {
            "naming_quality": {
                "score": 0,
                "placeholder": True,
            }
        },
        "assessment_import_audit": [],
    }


def _mark_review_complete(state: dict) -> None:
    display = DISPLAY_NAMES["naming_quality"]
    state["dimension_scores"][display] = {
        "score": 88.0,
        "strict": 88.0,
        "failing": 0,
        "checks": 1,
        "detectors": {
            "subjective_assessment": {
                "placeholder": False,
                "dimension_key": "naming_quality",
            }
        },
    }
    state["subjective_assessments"]["naming_quality"] = {
        "score": 88.0,
        "placeholder": False,
        "assessed_at": "2026-03-13T12:00:00+00:00",
    }
    state["issues"]["unused::src/app.ts::x"] = {
        "id": "unused::src/app.ts::x",
        "detector": "unused",
        "status": "open",
        "file": "src/app.ts",
        "tier": 1,
        "confidence": "high",
        "summary": "unused import",
        "detail": {},
    }
    state["work_items"] = state["issues"]


def test_postflight_progresses_review_then_workflow() -> None:
    state = _placeholder_state()
    plan = empty_plan()

    reconcile_plan(plan, state, target_strict=95.0)
    initial_snapshot = build_queue_snapshot(state, plan=plan)

    assert current_lifecycle_phase(plan) == "plan"
    assert initial_snapshot.phase == LIFECYCLE_PHASE_REVIEW_INITIAL
    assert [item["id"] for item in initial_snapshot.execution_items] == [
        "subjective::naming_quality"
    ]

    _mark_review_complete(state)
    purge_ids(plan, ["subjective::naming_quality"])
    mark_postflight_scan_completed(plan, scan_count=1)
    reconcile_plan(plan, state, target_strict=95.0)
    workflow_snapshot = build_queue_snapshot(state, plan=plan)

    assert current_lifecycle_phase(plan) == "plan"
    assert workflow_snapshot.phase == LIFECYCLE_PHASE_WORKFLOW_POSTFLIGHT
    assert not any(fid.startswith("subjective::") for fid in plan["queue_order"])
    assert all(item["id"].startswith("workflow::") for item in workflow_snapshot.execution_items)
