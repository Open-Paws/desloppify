from __future__ import annotations

import ast
from pathlib import Path

from desloppify.engine._plan.refresh_lifecycle import (
    invalidate_postflight_scan,
    current_lifecycle_phase,
    mark_postflight_scan_completed,
    postflight_scan_pending,
)
from desloppify.engine._plan.schema import empty_plan

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_REFRESH_LIFECYCLE = _PACKAGE_ROOT / "engine" / "_plan" / "refresh_lifecycle.py"
_PIPELINE = _PACKAGE_ROOT / "engine" / "_plan" / "sync" / "pipeline.py"


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

    changed = invalidate_postflight_scan(
        plan,
        issue_ids=[
            "workflow::run-scan",
            "triage::observe",
            "subjective::naming_quality",
        ],
    )

    assert changed is False
    assert postflight_scan_pending(plan) is False


def test_clearing_completion_for_real_issue_requires_new_scan() -> None:
    plan = empty_plan()
    mark_postflight_scan_completed(plan, scan_count=5)

    changed = invalidate_postflight_scan(
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
    assert current_lifecycle_phase(plan) == "plan"


def test_clearing_completion_for_review_issue_keeps_current_scan_boundary() -> None:
    plan = empty_plan()
    mark_postflight_scan_completed(plan, scan_count=5)

    changed = invalidate_postflight_scan(
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
    assert current_lifecycle_phase(plan) == "execute"

    plan["plan_start_scores"] = {"strict": 75.0}
    assert current_lifecycle_phase(plan) == "execute"


def test_legacy_coarse_phase_migrated_to_plan_mode() -> None:
    plan = empty_plan()
    plan["refresh_state"] = {"lifecycle_phase": "review"}

    assert current_lifecycle_phase(plan) == "plan"


def test_lifecycle_phase_writes_stay_owned_by_refresh_lifecycle_module() -> None:
    direct_writers: list[str] = []
    private_setter_callers: list[str] = []

    for path in _PACKAGE_ROOT.rglob("*.py"):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "_set_lifecycle_phase":
                    private_setter_callers.append(str(path.relative_to(_PACKAGE_ROOT)))
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Subscript):
                    continue
                slice_node = target.slice
                key: str | None = None
                if isinstance(slice_node, ast.Constant) and isinstance(
                    slice_node.value, str
                ):
                    key = slice_node.value
                elif isinstance(slice_node, ast.Name):
                    key = slice_node.id
                if key in {"lifecycle_phase", "_LIFECYCLE_PHASE_KEY"}:
                    direct_writers.append(str(path.relative_to(_PACKAGE_ROOT)))

    assert private_setter_callers == [str(_PIPELINE.relative_to(_PACKAGE_ROOT))]
    assert sorted(set(direct_writers)) == [
        str(_REFRESH_LIFECYCLE.relative_to(_PACKAGE_ROOT))
    ]
