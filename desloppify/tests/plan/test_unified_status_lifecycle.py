"""Integration tests for unified issue lifecycle status.

Exercises every rendering surface with mixed statuses (open, deferred, triaged_out,
fixed, wontfix, false_positive) to verify the full data flow.
"""
from __future__ import annotations

from desloppify.base.enums import (
    _CANONICAL_ISSUE_STATUSES,
    _RESOLVED_STATUSES,
    Status,
    canonical_issue_status,
    issue_status_tokens,
)
from desloppify.engine._plan.operations.skip import (
    backlog_items,
    skip_items,
    unskip_items,
)
from desloppify.engine._plan.scan_issue_reconcile import reconcile_plan_after_scan
from desloppify.engine._plan.schema import empty_plan
from desloppify.engine._plan.skip_policy import (
    skip_kind_needs_state_reopen,
    skip_kind_state_status,
)
from desloppify.engine._plan.triage.apply import apply_triage_to_plan
from desloppify.engine._plan.triage.prompt import (
    DismissedIssue,
    TriageResult,
)
from desloppify.engine._scoring.policy.core import FAILURE_STATUSES_BY_MODE
from desloppify.engine.planning.render_sections import summary_lines

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue(
    fid: str,
    *,
    status: str = "open",
    detector: str = "review",
    tier: int = 3,
) -> dict:
    return {
        "id": fid,
        "status": status,
        "detector": detector,
        "file": "test.py",
        "tier": tier,
        "confidence": "high",
        "summary": f"Issue {fid}",
    }


def _state_with_mixed_issues() -> dict:
    """Create a realistic state with issues at every lifecycle stage."""
    return {
        "issues": {
            "open_1": _issue("open_1", status="open"),
            "open_2": _issue("open_2", status="open"),
            "deferred_1": _issue("deferred_1", status="deferred"),
            "deferred_2": _issue("deferred_2", status="deferred"),
            "triaged_out_1": _issue("triaged_out_1", status="triaged_out"),
            "fixed_1": _issue("fixed_1", status="fixed"),
            "fixed_2": _issue("fixed_2", status="fixed"),
            "wontfix_1": _issue("wontfix_1", status="wontfix"),
            "fp_1": _issue("fp_1", status="false_positive"),
        },
        "scan_count": 10,
        "stats": {
            "total": 9,
            "open": 2,
            "deferred": 2,
            "triaged_out": 1,
            "fixed": 2,
            "wontfix": 1,
            "false_positive": 1,
            "auto_resolved": 0,
        },
    }


def _plan_with_skipped() -> dict:
    plan = empty_plan()
    plan["queue_order"] = ["open_1", "open_2"]
    plan["skipped"] = {
        "deferred_1": {
            "issue_id": "deferred_1",
            "kind": "temporary",
            "reason": "waiting on refactor",
        },
        "deferred_2": {
            "issue_id": "deferred_2",
            "kind": "temporary",
            "reason": "low priority",
        },
        "triaged_out_1": {
            "issue_id": "triaged_out_1",
            "kind": "triaged_out",
            "reason": "dismissed by triage",
        },
        "wontfix_1": {
            "issue_id": "wontfix_1",
            "kind": "permanent",
            "note": "acceptable risk",
        },
    }
    return plan


# ---------------------------------------------------------------------------
# A1: Enum membership
# ---------------------------------------------------------------------------

class TestEnumMembership:
    def test_deferred_in_canonical(self):
        assert "deferred" in _CANONICAL_ISSUE_STATUSES
        assert "triaged_out" in _CANONICAL_ISSUE_STATUSES

    def test_deferred_not_in_resolved(self):
        assert "deferred" not in _RESOLVED_STATUSES
        assert "triaged_out" not in _RESOLVED_STATUSES

    def test_canonical_normalizes_deferred(self):
        assert canonical_issue_status("deferred") == Status.DEFERRED
        assert canonical_issue_status("triaged_out") == Status.TRIAGED_OUT

    def test_issue_status_tokens_includes_new(self):
        tokens = issue_status_tokens()
        assert "deferred" in tokens
        assert "triaged_out" in tokens

    def test_issue_status_tokens_with_all(self):
        tokens = issue_status_tokens(include_all=True)
        assert "all" in tokens
        assert "deferred" in tokens


# ---------------------------------------------------------------------------
# A2: Scoring policy
# ---------------------------------------------------------------------------

class TestScoringPolicy:
    def test_all_modes_include_deferred(self):
        for mode, statuses in FAILURE_STATUSES_BY_MODE.items():
            assert "deferred" in statuses, f"deferred missing from {mode}"
            assert "triaged_out" in statuses, f"triaged_out missing from {mode}"


# ---------------------------------------------------------------------------
# A3: Skip ↔ status mapping
# ---------------------------------------------------------------------------

class TestSkipStatusMapping:
    def test_temporary_maps_to_deferred(self):
        assert skip_kind_state_status("temporary") == "deferred"

    def test_triaged_out_maps_to_triaged_out(self):
        assert skip_kind_state_status("triaged_out") == "triaged_out"

    def test_all_kinds_need_state_reopen(self):
        for kind in ("temporary", "permanent", "false_positive", "triaged_out"):
            assert skip_kind_needs_state_reopen(kind), f"{kind} should need reopen"


# ---------------------------------------------------------------------------
# A4: Backlog reopens deferred issues
# ---------------------------------------------------------------------------

class TestBacklogReopensDeferred:
    def test_backlog_removes_from_plan(self):
        plan = _plan_with_skipped()
        removed = backlog_items(plan, ["deferred_1"])
        assert "deferred_1" in removed
        assert "deferred_1" not in plan["skipped"]

    # The actual state reopen happens in cmd_plan_backlog (app layer),
    # which is tested via the full command flow.


# ---------------------------------------------------------------------------
# A5: Triage dismiss sets state status
# ---------------------------------------------------------------------------

class TestTriageDismissSetsState:
    def test_triage_apply_sets_triaged_out_in_state(self):
        plan = empty_plan()
        plan["queue_order"] = ["a", "b", "c"]
        state = {
            "issues": {
                "a": _issue("a"),
                "b": _issue("b"),
                "c": _issue("c"),
            },
            "scan_count": 5,
        }
        triage = TriageResult(
            strategy_summary="test strategy",
            epics=[{
                "name": "epic_test",
                "thesis": "test cluster",
                "direction": "fix it",
                "issue_ids": ["a"],
                "dependency_order": 1,
                "dismissed": [],
            }],
            dismissed_issues=[
                DismissedIssue(issue_id="b", reason="not relevant"),
            ],
        )
        result = apply_triage_to_plan(plan, state, triage, trigger="test")
        assert result.issues_dismissed == 1
        # State status should be updated
        assert state["work_items"]["b"]["status"] == "triaged_out"
        # Non-dismissed issue should stay open
        assert state["work_items"]["a"]["status"] == "open"


# ---------------------------------------------------------------------------
# A6: Deferred issues NOT reopened on scan reappearance
# ---------------------------------------------------------------------------

class TestDeferredNotReopenedOnScan:
    def test_upsert_preserves_deferred(self):
        from desloppify.engine._state.merge_issues import upsert_issues

        existing = {
            "d1": {**_issue("d1", status="deferred"), "last_seen": "old"},
        }
        current = [
            {**_issue("d1"), "status": "open"},  # scan sees it again
        ]
        upsert_issues(existing, current, [], "now", lang="python")
        # Deferred issues should NOT be reopened
        assert existing["d1"]["status"] == "deferred"


# ---------------------------------------------------------------------------
# A7: Status icons
# ---------------------------------------------------------------------------

class TestStatusIcons:
    def test_render_deferred_icon(self):
        from desloppify.base.enums import canonical_issue_status

        # Verify canonical_issue_status handles the new values
        assert canonical_issue_status("deferred") == "deferred"
        assert canonical_issue_status("triaged_out") == "triaged_out"


# ---------------------------------------------------------------------------
# A8: Plan header and summary include deferred counts
# ---------------------------------------------------------------------------

class TestPlanReportingSurfaces:
    def test_summary_lines_counts_deferred(self):
        stats = {
            "open": 5,
            "fixed": 3,
            "wontfix": 1,
            "auto_resolved": 1,
            "deferred": 2,
            "triaged_out": 1,
        }
        lines = summary_lines(stats)
        text = "\n".join(lines)
        assert "5 open" in text
        # Total = 5+3+1+1+2+1 = 13
        assert "13 total" in text
        # Addressed = 13 - 5(open) - 3(deferred) = 5
        assert "3 deferred" in text

    def test_summary_lines_no_deferred_note_when_zero(self):
        stats = {"open": 3, "fixed": 2, "wontfix": 0, "auto_resolved": 0}
        lines = summary_lines(stats)
        text = "\n".join(lines)
        assert "deferred" not in text


# ---------------------------------------------------------------------------
# A9: Data migration via reconcile
# ---------------------------------------------------------------------------

class TestReconcileDataMigration:
    def test_reconcile_syncs_open_skipped_to_deferred(self):
        plan = empty_plan()
        plan["queue_order"] = []
        plan["skipped"] = {
            "a": {"issue_id": "a", "kind": "temporary", "reason": "later"},
            "b": {"issue_id": "b", "kind": "triaged_out", "reason": "dismissed"},
        }
        state = {
            "issues": {
                "a": _issue("a", status="open"),  # should become deferred
                "b": _issue("b", status="open"),  # should become triaged_out
                "c": _issue("c", status="open"),  # not in skipped, stays open
            },
            "scan_count": 5,
        }
        reconcile_plan_after_scan(plan, state)
        assert state["work_items"]["a"]["status"] == "deferred"
        assert state["work_items"]["b"]["status"] == "triaged_out"
        assert state["work_items"]["c"]["status"] == "open"

    def test_reconcile_does_not_re_sync_already_correct(self):
        plan = empty_plan()
        plan["skipped"] = {
            "a": {"issue_id": "a", "kind": "temporary"},
        }
        state = {
            "issues": {
                "a": _issue("a", status="deferred"),  # already correct
            },
            "scan_count": 5,
        }
        reconcile_plan_after_scan(plan, state)
        assert state["work_items"]["a"]["status"] == "deferred"

    def test_reconcile_resurfaces_and_reopens(self):
        plan = empty_plan()
        plan["skipped"] = {
            "a": {
                "issue_id": "a",
                "kind": "temporary",
                "review_after": 2,
                "skipped_at_scan": 3,
            },
        }
        state = {
            "issues": {
                "a": _issue("a", status="deferred"),
            },
            "scan_count": 5,  # 3+2=5, should resurface
        }
        result = reconcile_plan_after_scan(plan, state)
        assert "a" in result.resurfaced
        # State should be reopened from deferred back to open
        assert state["work_items"]["a"]["status"] == "open"


# ---------------------------------------------------------------------------
# B2: Historical focus grouping
# ---------------------------------------------------------------------------

class TestHistoricalFocusGrouping:
    def test_groups_by_status(self):
        from desloppify.app.commands.review.prompt_sections import (
            render_historical_focus,
        )

        batch = {
            "historical_issue_focus": {
                "selected_count": 6,
                "issues": [
                    {"status": "open", "summary": "open issue 1"},
                    {"status": "deferred", "summary": "deferred issue 1"},
                    {"status": "triaged_out", "summary": "triaged out issue 1"},
                    {"status": "fixed", "summary": "fixed issue 1"},
                    {"status": "wontfix", "summary": "wontfix issue 1"},
                    {"status": "open", "summary": "open issue 2"},
                ],
            },
        }
        text = render_historical_focus(batch)
        assert "Still open (2):" in text
        assert "Deferred (1):" in text
        assert "Triaged out (1):" in text
        assert "Resolved (2):" in text
        assert "desloppify show review --no-budget" in text
        assert "desloppify show review --status deferred" in text

    def test_empty_when_no_history(self):
        from desloppify.app.commands.review.prompt_sections import (
            render_historical_focus,
        )

        assert render_historical_focus({}) == ""
        assert render_historical_focus({"historical_issue_focus": {"selected_count": 0}}) == ""


# ---------------------------------------------------------------------------
# B3: Dimension deferral context
# ---------------------------------------------------------------------------

class TestDimensionDeferralContext:
    def test_renders_deferral_cycles(self):
        from desloppify.app.commands.review.prompt_sections import (
            render_dimension_deferral_context,
        )

        batch = {
            "subjective_defer_meta": {
                "naming_quality": {"deferred_cycles": 3},
            },
        }
        text = render_dimension_deferral_context(batch)
        assert "naming_quality" in text
        assert "3 scan cycle(s)" in text
        assert "stale" in text

    def test_empty_when_no_meta(self):
        from desloppify.app.commands.review.prompt_sections import (
            render_dimension_deferral_context,
        )

        assert render_dimension_deferral_context({}) == ""
        assert render_dimension_deferral_context({"subjective_defer_meta": {}}) == ""


# ---------------------------------------------------------------------------
# Unskip roundtrip: temporary skip → deferred → unskip → open
# ---------------------------------------------------------------------------

class TestFullLifecycleRoundtrip:
    def test_skip_unskip_roundtrip_with_state(self):
        """Full lifecycle: skip temporary → state deferred → unskip → need reopen."""
        plan = empty_plan()
        plan["queue_order"] = ["a", "b"]

        # Skip a as temporary
        skip_items(plan, ["a"], kind="temporary", reason="waiting")
        assert "a" in plan["skipped"]
        assert plan["skipped"]["a"]["kind"] == "temporary"

        # skip_kind_state_status tells the caller to set state to "deferred"
        assert skip_kind_state_status("temporary") == "deferred"

        # Unskip
        count, need_reopen, protected = unskip_items(plan, ["a"])
        assert count == 1
        assert "a" in need_reopen  # caller must reopen state from deferred→open
        assert "a" in plan["queue_order"]

    def test_triage_dismiss_unskip_roundtrip(self):
        """Triage dismiss → triaged_out → unskip → reopen."""
        plan = empty_plan()
        plan["queue_order"] = ["x"]
        state = {"issues": {"x": _issue("x")}, "scan_count": 1}

        triage = TriageResult(
            strategy_summary="test",
            epics=[],
            dismissed_issues=[DismissedIssue(issue_id="x", reason="not needed")],
        )
        apply_triage_to_plan(plan, state, triage, trigger="test")
        assert state["work_items"]["x"]["status"] == "triaged_out"
        assert "x" in plan["skipped"]

        # Unskip
        count, need_reopen, _ = unskip_items(plan, ["x"])
        assert count == 1
        assert "x" in need_reopen
