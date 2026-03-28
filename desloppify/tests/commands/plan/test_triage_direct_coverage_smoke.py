"""Direct-coverage smoke tests for triage helper modules."""

from __future__ import annotations

import inspect

from desloppify.app.commands.plan.shared.cluster_membership import cluster_issue_ids
from desloppify.app.commands.plan.triage.plan_state_access import ensure_execution_log
import desloppify.app.commands.plan.triage.command as triage_command_mod
import desloppify.app.commands.plan.triage.helpers as triage_helpers_mod
import desloppify.app.commands.plan.triage.services as triage_services_mod
import desloppify.app.commands.plan.triage.stages.completion as triage_completion_mod
import desloppify.app.commands.plan.triage.workflow as triage_workflow_mod
import desloppify.app.commands.plan.triage.runner.codex_runner as triage_codex_runner_mod
import desloppify.app.commands.plan.triage.runner.orchestrator_common as triage_orchestrator_mod
import desloppify.app.commands.plan.triage.runner.orchestrator_codex_observe as triage_observe_mod
import desloppify.app.commands.plan.triage.runner.orchestrator_codex_parallel as triage_parallel_mod
import desloppify.app.commands.plan.triage.display.dashboard as triage_display_mod
import desloppify.app.commands.plan.triage.display.layout as triage_display_layout_mod


def test_triage_helper_modules_direct_coverage_smoke() -> None:
    assert callable(triage_helpers_mod.has_triage_in_queue)
    assert callable(triage_helpers_mod.triage_coverage)
    assert callable(triage_helpers_mod.group_issues_into_observe_batches)
    assert callable(cluster_issue_ids)

    services = triage_services_mod.default_triage_services()
    assert isinstance(services, triage_services_mod.TriageServices)
    assert callable(services.load_plan)
    assert callable(services.save_plan)

    assert callable(triage_completion_mod.cmd_triage_complete)
    assert callable(triage_completion_mod.cmd_confirm_existing)
    assert callable(triage_workflow_mod.run_triage_workflow)

    assert callable(triage_codex_runner_mod.run_triage_stage)
    assert callable(triage_codex_runner_mod._output_file_has_text)

    assert callable(triage_orchestrator_mod.parse_only_stages)
    assert triage_orchestrator_mod.parse_only_stages("observe,reflect") == [
        "observe",
        "reflect",
    ]

    codex_src = inspect.getsource(triage_codex_runner_mod)
    observe_src = inspect.getsource(triage_observe_mod)
    parallel_src = inspect.getsource(triage_parallel_mod)
    assert "app.commands.review.runner_process_impl.types" not in codex_src
    assert "app.commands.review.runner_parallel.types" not in observe_src
    assert "app.commands.review.runner_parallel.types" not in parallel_src

    display_src = inspect.getsource(triage_display_mod)
    display_layout_src = inspect.getsource(triage_display_layout_mod)
    assert "from . import display as display_mod" not in display_layout_src
    assert "from .primitives import print_stage_progress" in display_src

    command_src = inspect.getsource(triage_command_mod)
    assert "run_triage_workflow(" in command_src
    assert "default_triage_services()" in command_src
    assert "runner.orchestrator_codex_pipeline" not in command_src
    assert "runner.orchestrator_claude" not in command_src
    assert "stages import commands" not in command_src


def test_count_log_activity_since_ignores_malformed_entries() -> None:
    plan = {
        "execution_log": [
            {"timestamp": "2026-01-01T00:00:00Z", "action": "resolve"},
            {"timestamp": "2026-01-01T00:00:00Z", "action": 123},
            {"timestamp": 123, "action": "skip"},
            {"action": "skip"},
            {"timestamp": "2026-01-01T00:00:00Z"},
            "bad-entry",
        ]
    }
    counts = triage_helpers_mod.count_log_activity_since(plan, "2025-12-31T00:00:00Z")
    assert counts == {"resolve": 1}


def test_count_log_activity_since_includes_all_entries_when_since_is_none() -> None:
    plan = {
        "execution_log": [
            {"timestamp": "2026-01-01T00:00:00Z", "action": "resolve"},
            {"timestamp": "2026-01-02T00:00:00Z", "action": "skip"},
            {"timestamp": "2026-01-03T00:00:00Z", "action": "done"},
        ]
    }

    counts = triage_helpers_mod.count_log_activity_since(plan, None)

    assert counts == {"resolve": 1, "skip": 1, "done": 1}


def test_ensure_execution_log_replaces_malformed_entries_in_plan() -> None:
    plan = {
        "execution_log": [
            {"timestamp": "2026-01-01T00:00:00Z", "action": "resolve"},
            "bad-entry",
            123,
        ]
    }

    normalized = ensure_execution_log(plan)

    assert normalized == [{"timestamp": "2026-01-01T00:00:00Z", "action": "resolve"}]
    assert plan["execution_log"] == normalized
