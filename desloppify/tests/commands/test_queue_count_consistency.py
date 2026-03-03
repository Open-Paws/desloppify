"""Tests for queue count disagreement fixes (#194, #195, #196).

Covers:
- Fix 1: auto_resolve_disappeared resolves out-of-scope issues
- Fix 2: queue counting functions pass scan_path
- Fix 3: compute_subjective_visibility respects scan_path + plan
- Fix 4a: workflow::run-scan synthetic item
- Fix 6: queue_guard passes scan_path
"""

from __future__ import annotations

from unittest.mock import patch

from desloppify.engine._state.merge_issues import auto_resolve_disappeared
from desloppify.engine._plan.subjective_policy import compute_subjective_visibility


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue(
    fid: str,
    detector: str = "unused",
    status: str = "open",
    file: str = "src/foo.ts",
    suppressed: bool = False,
) -> dict:
    f: dict = {
        "id": fid,
        "detector": detector,
        "status": status,
        "file": file,
    }
    if suppressed:
        f["suppressed"] = True
    return f


def _state_with_issues(*issues: dict) -> dict:
    return {
        "issues": {f["id"]: f for f in issues},
        "scan_count": 5,
    }


# ---------------------------------------------------------------------------
# Fix 1: auto_resolve_disappeared resolves out-of-scope issues
# ---------------------------------------------------------------------------

class TestAutoResolveOutOfScope:
    def test_out_of_scope_issues_are_resolved(self):
        """Issues outside scan_path are auto-resolved, not skipped."""
        existing = {
            "f1": {
                "id": "f1", "status": "open", "file": "supabase/fn.ts",
                "detector": "unused",
            },
            "f2": {
                "id": "f2", "status": "open", "file": "src/app.ts",
                "detector": "unused",
            },
        }
        resolved, _lang, out_of_scope, detectors = auto_resolve_disappeared(
            existing,
            current_ids=set(),
            suspect_detectors=set(),
            now="2026-01-01T00:00:00+00:00",
            lang=None,
            scan_path="src",
        )
        # f1 is out of scope and should be auto-resolved
        assert existing["f1"]["status"] == "auto_resolved"
        assert "Out of current scan scope" in existing["f1"]["note"]
        assert out_of_scope == 1
        # f2 is in scope and should also be resolved (disappeared from scan)
        assert existing["f2"]["status"] == "auto_resolved"
        assert resolved == 1  # f2 counts toward normal resolved
        assert "unused" in detectors

    def test_out_of_scope_resolution_attestation(self):
        """Out-of-scope issues get scan_verified attestation with scope note."""
        existing = {
            "f1": {
                "id": "f1", "status": "open", "file": "supabase/fn.ts",
                "detector": "smells",
            },
        }
        auto_resolve_disappeared(
            existing,
            current_ids=set(),
            suspect_detectors=set(),
            now="2026-03-01T00:00:00+00:00",
            lang=None,
            scan_path="src",
        )
        attestation = existing["f1"]["resolution_attestation"]
        assert attestation["kind"] == "scan_verified"
        assert "scan_path: src" in attestation["text"]

    def test_no_scan_path_skips_nothing(self):
        """When scan_path is None, all disappeared issues are resolved normally."""
        existing = {
            "f1": {
                "id": "f1", "status": "open", "file": "anywhere/file.ts",
                "detector": "unused",
            },
        }
        resolved, _lang, out_of_scope, _detectors = auto_resolve_disappeared(
            existing,
            current_ids=set(),
            suspect_detectors=set(),
            now="2026-01-01T00:00:00+00:00",
            lang=None,
            scan_path=None,
        )
        assert resolved == 1
        assert out_of_scope == 0

    def test_dot_scan_path_skips_nothing(self):
        """scan_path='.' means everything is in scope."""
        existing = {
            "f1": {
                "id": "f1", "status": "open", "file": "anywhere/file.ts",
                "detector": "unused",
            },
        }
        resolved, _lang, out_of_scope, _detectors = auto_resolve_disappeared(
            existing,
            current_ids=set(),
            suspect_detectors=set(),
            now="2026-01-01T00:00:00+00:00",
            lang=None,
            scan_path=".",
        )
        assert resolved == 1
        assert out_of_scope == 0

    def test_out_of_scope_adds_to_resolved_detectors(self):
        """Out-of-scope resolved issues contribute to resolved_detectors set."""
        existing = {
            "f1": {
                "id": "f1", "status": "open", "file": "other/file.ts",
                "detector": "smells",
            },
        }
        _resolved, _lang, _out_of_scope, detectors = auto_resolve_disappeared(
            existing,
            current_ids=set(),
            suspect_detectors=set(),
            now="2026-01-01T00:00:00+00:00",
            lang=None,
            scan_path="src",
        )
        assert "smells" in detectors


# ---------------------------------------------------------------------------
# Fix 2: queue counting functions pass scan_path
# ---------------------------------------------------------------------------

class TestQueueCountingScanPath:
    def test_queue_count_respects_scan_path_from_state(self):
        """build_work_queue auto-reads scan_path from state and filters issues."""
        from desloppify.engine.work_queue import QueueBuildOptions, build_work_queue

        state: dict = {
            "issues": {
                "f1": {
                    "id": "f1", "detector": "unused", "status": "open",
                    "file": "src/a.ts", "tier": 1, "confidence": "high",
                    "summary": "in scope", "detail": {},
                },
                "f2": {
                    "id": "f2", "detector": "unused", "status": "open",
                    "file": "other/b.ts", "tier": 1, "confidence": "high",
                    "summary": "out of scope", "detail": {},
                },
            },
            "scan_path": "src",
            "scan_count": 5,
        }
        # No explicit scan_path — auto-reads "src" from state
        result = build_work_queue(
            state,
            options=QueueBuildOptions(status="open", count=None),
        )
        ids = {item["id"] for item in result["items"]}
        assert "f1" in ids
        assert "f2" not in ids
        assert result["total"] == 1

    def test_queue_count_no_scan_path_returns_all(self):
        """Without scan_path in state, all issues are returned."""
        from desloppify.engine.work_queue import QueueBuildOptions, build_work_queue

        state: dict = {
            "issues": {
                "f1": {
                    "id": "f1", "detector": "unused", "status": "open",
                    "file": "src/a.ts", "tier": 1, "confidence": "high",
                    "summary": "a", "detail": {},
                },
                "f2": {
                    "id": "f2", "detector": "unused", "status": "open",
                    "file": "other/b.ts", "tier": 1, "confidence": "high",
                    "summary": "b", "detail": {},
                },
            },
            "scan_count": 5,
        }
        result = build_work_queue(
            state,
            options=QueueBuildOptions(status="open", count=None),
        )
        assert result["total"] == 2

    def test_explicit_scan_path_overrides_state(self):
        """Explicit scan_path on QueueBuildOptions overrides state value."""
        from desloppify.engine.work_queue import QueueBuildOptions, build_work_queue

        state: dict = {
            "issues": {
                "f1": {
                    "id": "f1", "detector": "unused", "status": "open",
                    "file": "src/a.ts", "tier": 1, "confidence": "high",
                    "summary": "a", "detail": {},
                },
                "f2": {
                    "id": "f2", "detector": "unused", "status": "open",
                    "file": "other/b.ts", "tier": 1, "confidence": "high",
                    "summary": "b", "detail": {},
                },
            },
            "scan_path": "src",  # state says "src"
            "scan_count": 5,
        }
        # Explicit scan_path=None disables filtering despite state having "src"
        result = build_work_queue(
            state,
            options=QueueBuildOptions(status="open", count=None, scan_path=None),
        )
        assert result["total"] == 2


# ---------------------------------------------------------------------------
# Fix 3: compute_subjective_visibility respects scan_path + plan
# ---------------------------------------------------------------------------

class TestSubjectivePolicyScanPathAndPlan:
    def test_scan_path_excludes_out_of_scope_issues(self):
        """Issues outside scan_path don't count toward objective backlog."""
        state = _state_with_issues(
            _issue("f1", "unused", file="src/app.ts"),
            _issue("f2", "unused", file="supabase/fn.ts"),
            _issue("f3", "unused", file="src/lib.ts"),
        )
        # Without scan_path: all 3 count
        policy_all = compute_subjective_visibility(state)
        assert policy_all.objective_count == 3

        # With scan_path: only 2 in src/ count
        policy_scoped = compute_subjective_visibility(state, scan_path="src")
        assert policy_scoped.objective_count == 2
        assert policy_scoped.has_objective_backlog is True

    def test_scan_path_drains_backlog_correctly(self):
        """When all in-scope issues are resolved, backlog is drained even
        if out-of-scope issues remain open."""
        state = _state_with_issues(
            _issue("f1", "unused", file="supabase/fn.ts"),
            _issue("f2", "unused", file="supabase/other.ts"),
        )
        policy = compute_subjective_visibility(state, scan_path="src")
        assert policy.objective_count == 0
        assert policy.has_objective_backlog is False

    def test_plan_skipped_issues_excluded(self):
        """Issues in plan['skipped'] don't count toward objective backlog."""
        state = _state_with_issues(
            _issue("f1", "unused", file="src/a.ts"),
            _issue("f2", "unused", file="src/b.ts"),
            _issue("f3", "unused", file="src/c.ts"),
        )
        plan = {"skipped": {"f1": {"kind": "temporary"}, "f2": {"kind": "permanent"}}}
        policy = compute_subjective_visibility(state, plan=plan)
        assert policy.objective_count == 1  # only f3

    def test_scan_path_and_plan_combined(self):
        """Both filters applied together: scope + skipped."""
        state = _state_with_issues(
            _issue("f1", "unused", file="src/a.ts"),     # in scope, not skipped → counts
            _issue("f2", "unused", file="src/b.ts"),     # in scope, skipped → excluded
            _issue("f3", "unused", file="other/c.ts"),   # out of scope → excluded
        )
        plan = {"skipped": {"f2": {"kind": "temporary"}}}
        policy = compute_subjective_visibility(state, scan_path="src", plan=plan)
        assert policy.objective_count == 1
        assert policy.has_objective_backlog is True

    def test_no_params_backward_compat(self):
        """Without new params, behavior is unchanged (all issues counted)."""
        state = _state_with_issues(
            _issue("f1", "unused", file="anywhere/a.ts"),
        )
        policy = compute_subjective_visibility(state)
        assert policy.objective_count == 1


# ---------------------------------------------------------------------------
# Fix 4a: workflow::run-scan synthetic item
# ---------------------------------------------------------------------------

class TestWorkflowRunScanItem:
    def test_run_scan_item_injected_when_queue_empty_and_plan_active(self):
        """When queue is empty and plan_start_scores exist, workflow::run-scan appears."""
        from desloppify.engine.work_queue import QueueBuildOptions, build_work_queue

        state: dict = {"issues": {}, "scan_count": 5}
        plan = {
            "plan_start_scores": {"strict": 75.0},
            "queue_order": [],
            "skipped": {},
        }
        result = build_work_queue(
            state,
            options=QueueBuildOptions(
                status="open",
                count=None,
                plan=plan,
            ),
        )
        items = result["items"]
        assert len(items) == 1
        assert items[0]["id"] == "workflow::run-scan"
        assert items[0]["kind"] == "workflow_action"
        assert "scan" in items[0]["primary_command"]

    def test_run_scan_not_injected_when_real_items_exist(self):
        """When queue has real issues, no workflow::run-scan item."""
        from desloppify.engine.work_queue import QueueBuildOptions, build_work_queue

        state: dict = {
            "issues": {
                "f1": {
                    "id": "f1", "detector": "unused", "status": "open",
                    "file": "src/a.ts", "tier": 1, "confidence": "high",
                    "summary": "test", "detail": {},
                },
            },
            "scan_count": 5,
        }
        plan = {
            "plan_start_scores": {"strict": 75.0},
            "queue_order": ["f1"],
            "skipped": {},
        }
        result = build_work_queue(
            state,
            options=QueueBuildOptions(
                status="open",
                count=None,
                plan=plan,
            ),
        )
        run_scan_items = [i for i in result["items"] if i.get("id") == "workflow::run-scan"]
        assert len(run_scan_items) == 0

    def test_run_scan_not_injected_without_plan_start_scores(self):
        """No workflow::run-scan when plan_start_scores is empty (no active cycle)."""
        from desloppify.engine.work_queue import QueueBuildOptions, build_work_queue

        state: dict = {"issues": {}, "scan_count": 5}
        plan = {
            "plan_start_scores": {},
            "queue_order": [],
            "skipped": {},
        }
        result = build_work_queue(
            state,
            options=QueueBuildOptions(
                status="open",
                count=None,
                plan=plan,
            ),
        )
        assert result["total"] == 0

    def test_run_scan_not_injected_without_plan(self):
        """No workflow::run-scan when no plan is provided."""
        from desloppify.engine.work_queue import QueueBuildOptions, build_work_queue

        state: dict = {"issues": {}, "scan_count": 5}
        result = build_work_queue(
            state,
            options=QueueBuildOptions(
                status="open",
                count=None,
                plan=None,
            ),
        )
        assert result["total"] == 0

    def test_run_scan_does_not_block_scan_preflight(self):
        """The scan preflight gate uses breakdown.actionable which excludes
        workflow items, so workflow::run-scan doesn't create a circular block."""
        from desloppify.app.commands.helpers.queue_progress import (
            plan_aware_queue_breakdown,
        )

        state: dict = {"issues": {}, "scan_count": 5}
        plan = {
            "plan_start_scores": {"strict": 75.0},
            "queue_order": [],
            "skipped": {},
        }
        breakdown = plan_aware_queue_breakdown(state, plan=plan)
        assert breakdown.queue_total == 1
        assert breakdown.workflow == 1
        assert breakdown.actionable == 0  # gate passes


# ---------------------------------------------------------------------------
# Fix 4a: render_queue_header for workflow-only items
# ---------------------------------------------------------------------------

class TestRenderQueueHeaderWorkflow:
    def test_header_shows_cleared_for_run_scan(self, capsys):
        from desloppify.app.commands.next_parts.render_support import render_queue_header
        queue = {
            "total": 1,
            "items": [{"id": "workflow::run-scan", "kind": "workflow_action"}],
        }
        render_queue_header(queue, explain=False)
        output = capsys.readouterr().out
        assert "Queue cleared" in output
        assert "workflow step" in output

    def test_header_shows_count_for_real_items(self, capsys):
        from desloppify.app.commands.next_parts.render_support import render_queue_header
        queue = {
            "total": 5,
            "items": [{"id": "f1", "kind": "issue"}],
        }
        render_queue_header(queue, explain=False)
        output = capsys.readouterr().out
        assert "5 items" in output
        assert "cleared" not in output


# ---------------------------------------------------------------------------
# Fix 6: queue_guard passes scan_path
# ---------------------------------------------------------------------------

class TestQueueGuardScanPath:
    def test_queue_guard_respects_scan_path_from_state(self):
        """_check_queue_order_guard uses build_work_queue which auto-reads
        scan_path from state, so out-of-scope items don't appear in the queue."""
        from desloppify.app.commands.resolve.queue_guard import _check_queue_order_guard

        state = {
            "issues": {
                "f1": {"id": "f1", "status": "open", "file": "src/a.ts"},
            },
            "scan_path": "src",
        }
        mock_result = {
            "total": 1,
            "items": [{"id": "f1", "kind": "issue"}],
            "grouped": {},
            "new_ids": set(),
        }
        with (
            patch("desloppify.app.commands.resolve.queue_guard.has_living_plan", return_value=True),
            patch("desloppify.app.commands.resolve.queue_guard.load_plan", return_value={
                "queue_order": ["f1"],
                "skipped": {},
            }),
            patch(
                "desloppify.app.commands.resolve.queue_guard.build_work_queue",
                return_value=mock_result,
            ) as mock_build,
        ):
            # Should not raise — f1 is at front of queue
            result = _check_queue_order_guard(state, ["f1"], "fixed")
            assert result is False
            # Verify build_work_queue was called (scan_path resolved internally)
            mock_build.assert_called_once()
