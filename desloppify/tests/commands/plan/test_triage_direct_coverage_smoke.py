"""Direct-coverage smoke tests for triage helper modules."""

from __future__ import annotations

import desloppify.app.commands.plan.triage.helpers as triage_helpers_mod
import desloppify.app.commands.plan.triage.services as triage_services_mod
import desloppify.app.commands.plan.triage.stage_completion_commands as triage_completion_mod
import desloppify.app.commands.plan.triage.runner.codex_runner as triage_codex_runner_mod
import desloppify.app.commands.plan.triage.runner.orchestrator_common as triage_orchestrator_mod


def test_triage_helper_modules_direct_coverage_smoke() -> None:
    assert callable(triage_helpers_mod.has_triage_in_queue)
    assert callable(triage_helpers_mod.triage_coverage)
    assert callable(triage_helpers_mod.group_issues_into_observe_batches)

    services = triage_services_mod.default_triage_services()
    assert isinstance(services, triage_services_mod.TriageServices)
    assert callable(services.load_plan)
    assert callable(services.save_plan)

    assert callable(triage_completion_mod.cmd_triage_complete)
    assert callable(triage_completion_mod.cmd_confirm_existing)

    assert callable(triage_codex_runner_mod.run_triage_stage)
    assert callable(triage_codex_runner_mod._output_file_has_text)

    assert callable(triage_orchestrator_mod.parse_only_stages)
    assert triage_orchestrator_mod.parse_only_stages("observe,reflect") == [
        "observe",
        "reflect",
    ]
