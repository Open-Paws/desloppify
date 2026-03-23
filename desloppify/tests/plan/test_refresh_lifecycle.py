from __future__ import annotations

from desloppify.engine._plan.refresh_lifecycle import (
    clear_postflight_scan_completion,
    current_lifecycle_phase,
    mark_postflight_scan_completed,
    postflight_scan_pending,
)
from desloppify.engine._plan.schema import empty_plan


def test_postflight_scan_pending_until_completed() -> None:
    plan = empty_plan()

    assert postflight_scan_pending(plan) is True

    changed = mark_postflight_scan_completed(plan, scan_count=7)

    assert changed is True
    assert postflight_scan_pending(plan) is False
    assert plan["refresh_state"]["postflight_scan_completed_at_scan_count"] == 7


def test_clearing_completion_ignores_synthetic_ids() -> None:
    plan = empty_plan()
    mark_postflight_scan_completed(plan, scan_count=3)

    changed = clear_postflight_scan_completion(
        plan,
        issue_ids=["workflow::run-scan", "triage::observe", "subjective::naming_quality"],
    )

    assert changed is False
    assert postflight_scan_pending(plan) is False


def test_clearing_completion_for_real_issue_requires_new_scan() -> None:
    plan = empty_plan()
    mark_postflight_scan_completed(plan, scan_count=5)

    changed = clear_postflight_scan_completion(
        plan,
        issue_ids=["unused::src/app.ts::thing"],
        state={
            "issues": {
                "unused::src/app.ts::thing": {
                    "id": "unused::src/app.ts::thing",
                    "detector": "unused",
                    "status": "open",
                    "file": "src/app.ts",
                    "tier": 1,
                    "confidence": "high",
                    "summary": "unused import",
                    "detail": {},
                }
            }
        },
    )

    assert changed is True
    assert postflight_scan_pending(plan) is True
    assert current_lifecycle_phase(plan) == "execute"


def test_clearing_completion_for_review_issue_keeps_current_scan_boundary() -> None:
    plan = empty_plan()
    mark_postflight_scan_completed(plan, scan_count=5)

    changed = clear_postflight_scan_completion(
        plan,
        issue_ids=["review::src/app.ts::naming"],
        state={
            "issues": {
                "review::src/app.ts::naming": {
                    "id": "review::src/app.ts::naming",
                    "detector": "review",
                    "status": "open",
                    "file": "src/app.ts",
                    "tier": 1,
                    "confidence": "high",
                    "summary": "naming issue",
                    "detail": {"dimension": "naming_quality"},
                }
            }
        },
    )

    assert changed is False
    assert postflight_scan_pending(plan) is False


def test_current_lifecycle_phase_falls_back_for_legacy_plans() -> None:
    plan = empty_plan()
    assert current_lifecycle_phase(plan) == "plan"

    mark_postflight_scan_completed(plan, scan_count=2)
    plan["plan_start_scores"] = {"strict": 75.0}
    assert current_lifecycle_phase(plan) == "execute"


def test_legacy_coarse_phase_migrated_to_plan_mode() -> None:
    plan = empty_plan()
    plan["refresh_state"] = {"lifecycle_phase": "review"}

    assert current_lifecycle_phase(plan) == "plan"
