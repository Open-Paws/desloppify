"""Edge-case and combined-scenario tests for epic triage apply."""

from __future__ import annotations

from desloppify.engine._plan.triage.apply import apply_triage_to_plan
from desloppify.engine._plan.triage.prompt import DismissedIssue, TriageResult
from desloppify.engine._plan.schema import empty_plan


def _state_with_review_issues(*ids: str) -> dict:
    """Build minimal state with open review issues."""
    issues = {}
    for fid in ids:
        issues[fid] = {
            "status": "open",
            "detector": "review",
            "file": "test.py",
            "summary": f"Review issue {fid}",
            "confidence": "medium",
            "tier": 2,
            "detail": {"dimension": "abstraction_fitness"},
        }
    return {"issues": issues, "scan_count": 5, "dimension_scores": {}}


def _state_empty() -> dict:
    return {"issues": {}, "scan_count": 1, "dimension_scores": {}}


def _triage_with_epics(*epics: dict) -> TriageResult:
    """Build a TriageResult with the given epics and no dismissals."""
    return TriageResult(
        strategy_summary="Test strategy",
        epics=list(epics),
    )


def _epic(
    name: str,
    issue_ids: list[str],
    dependency_order: int = 1,
    *,
    direction: str = "delete",
    dismissed: list[str] | None = None,
    agent_safe: bool = False,
    status: str = "pending",
    action_steps: list[str] | None = None,
) -> dict:
    """Build a minimal epic dict for TriageResult."""
    return {
        "name": name,
        "thesis": f"Thesis for {name}",
        "direction": direction,
        "root_cause": f"Root cause for {name}",
        "issue_ids": issue_ids,
        "dismissed": dismissed or [],
        "agent_safe": agent_safe,
        "dependency_order": dependency_order,
        "action_steps": action_steps or [],
        "status": status,
    }


class TestEdgeCases:
    def test_empty_plan(self):
        """apply_triage_to_plan works on a completely empty plan."""
        plan = empty_plan()
        state = _state_empty()
        triage = TriageResult(strategy_summary="nothing to do", epics=[])

        result = apply_triage_to_plan(plan, state, triage)

        assert result.epics_created == 0
        assert result.issues_dismissed == 0
        assert result.triage_version == 1
        assert plan["epic_triage_meta"]["version"] == 1

    def test_no_epics_no_dismissals(self):
        plan = empty_plan()
        plan["queue_order"] = ["a", "b"]
        state = _state_with_review_issues("a", "b")
        triage = TriageResult(strategy_summary="clean", epics=[])

        result = apply_triage_to_plan(plan, state, triage)

        assert result.epics_created == 0
        assert result.issues_dismissed == 0
        assert plan["queue_order"] == ["a", "b"]

    def test_empty_state_no_issues(self):
        plan = empty_plan()
        state = _state_empty()
        triage = _triage_with_epics(
            _epic("empty-epic", [], dependency_order=1),
        )

        result = apply_triage_to_plan(plan, state, triage)

        assert result.epics_created == 1
        assert plan["clusters"]["epic/empty-epic"]["issue_ids"] == []

    def test_minimal_plan_dict(self):
        """A bare dict (not from empty_plan) should be filled by ensure_plan_defaults."""
        plan: dict = {"version": 7, "created": "x", "updated": "x"}
        state = _state_with_review_issues("r1")
        triage = _triage_with_epics(_epic("minimal", ["r1"]))

        result = apply_triage_to_plan(plan, state, triage)

        assert result.epics_created == 1
        assert "epic/minimal" in plan["clusters"]

    def test_idempotent_apply(self):
        """Applying the same triage twice: first creates, second updates."""
        plan = empty_plan()
        state = _state_with_review_issues("r1")
        triage = _triage_with_epics(_epic("idem", ["r1"]))

        r1 = apply_triage_to_plan(plan, state, triage)
        assert r1.epics_created == 1
        assert r1.epics_updated == 0

        r2 = apply_triage_to_plan(plan, state, triage)
        assert r2.epics_created == 0
        assert r2.epics_updated == 1

        # Same epic still present
        assert "epic/idem" in plan["clusters"]

    def test_epic_issue_not_in_queue_still_reordered(self):
        """Epic issues not already in queue_order still appear in reordered queue."""
        plan = empty_plan()
        plan["queue_order"] = ["other"]
        state = _state_with_review_issues("r1")
        triage = _triage_with_epics(_epic("missing", ["r1"]))

        apply_triage_to_plan(plan, state, triage)

        # r1 was not in queue but is an epic issue -- it gets added at front
        assert "r1" in plan["queue_order"]
        assert plan["queue_order"][0] == "r1"


# ---------------------------------------------------------------------------
# Combined scenarios
# ---------------------------------------------------------------------------


class TestCombinedScenarios:
    def test_create_dismiss_and_reorder(self):
        """Full scenario: create epics, dismiss issues, and reorder."""
        plan = empty_plan()
        plan["queue_order"] = ["r1", "r2", "r3", "r4", "other"]
        state = _state_with_review_issues("r1", "r2", "r3", "r4")
        triage = TriageResult(
            strategy_summary="Comprehensive plan",
            epics=[
                _epic("high-priority", ["r1"], dependency_order=1),
                _epic("low-priority", ["r3"], dependency_order=2),
            ],
            dismissed_issues=[
                DismissedIssue(issue_id="r4", reason="false positive"),
            ],
        )

        result = apply_triage_to_plan(plan, state, triage)

        assert result.epics_created == 2
        assert result.issues_dismissed == 1
        # r4 gone from queue
        assert "r4" not in plan["queue_order"]
        assert "r4" in plan["skipped"]
        # Order: epic dep 1 (r1), epic dep 2 (r3), non-epic (r2, other)
        assert plan["queue_order"] == ["r1", "r3", "r2", "other"]

    def test_update_and_dismiss_in_same_triage(self):
        """Update an existing epic and dismiss issues in a single triage pass."""
        plan = empty_plan()
        plan["clusters"]["epic/old"] = {
            "name": "epic/old",
            "thesis": "old thesis",
            "direction": "merge",
            "issue_ids": ["r1"],
            "status": "pending",
            "auto": True,
            "cluster_key": "epic::epic/old",
            "created_at": "2025-01-01",
            "updated_at": "2025-01-01",
            "triage_version": 1,
        }
        plan["queue_order"] = ["r1", "r2", "r3"]
        state = _state_with_review_issues("r1", "r2", "r3")
        triage = TriageResult(
            strategy_summary="refresh",
            epics=[_epic("old", ["r1", "r2"], dependency_order=1)],
            dismissed_issues=[
                DismissedIssue(issue_id="r3", reason="obsolete"),
            ],
        )

        result = apply_triage_to_plan(plan, state, triage)

        assert result.epics_updated == 1
        assert result.issues_dismissed == 1
        assert plan["clusters"]["epic/old"]["issue_ids"] == ["r1", "r2"]
        assert "r3" not in plan["queue_order"]
        assert "r3" in plan["skipped"]

    def test_scan_count_zero(self):
        """When scan_count is 0, skipped_at_scan should be 0."""
        plan = empty_plan()
        plan["queue_order"] = ["r1"]
        state = _state_with_review_issues("r1")
        state["scan_count"] = 0
        triage = TriageResult(
            strategy_summary="x",
            epics=[],
            dismissed_issues=[DismissedIssue(issue_id="r1", reason="test")],
        )

        apply_triage_to_plan(plan, state, triage)

        assert plan["skipped"]["r1"]["skipped_at_scan"] == 0
