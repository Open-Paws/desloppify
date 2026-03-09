"""Direct tests for triage stage prompt and enrich/sense flow split modules."""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import desloppify.app.commands.plan.triage.runner.stage_prompts_instructions as prompts_instructions_mod
import desloppify.app.commands.plan.triage.runner.stage_prompts_observe as prompts_observe_mod
import desloppify.app.commands.plan.triage.runner.stage_prompts_sense as prompts_sense_mod
import desloppify.app.commands.plan.triage.runner.stage_prompts_validation as prompts_validation_mod
import desloppify.app.commands.plan.triage.stage_flow_enrich_sense as stage_flow_mod


class _Services:
    def __init__(self, plan: dict):
        self.plan = plan
        self.save_calls = 0
        self.logs: list[dict] = []

    def load_plan(self) -> dict:
        return self.plan

    def save_plan(self, _plan: dict) -> None:
        self.save_calls += 1

    def append_log_entry(self, _plan: dict, _action: str, **kwargs) -> None:
        self.logs.append(kwargs)


def test_stage_prompt_instruction_blocks_and_validation_requirements() -> None:
    assert "OBSERVE" in prompts_instructions_mod._observe_instructions()
    assert "REFLECT" in prompts_instructions_mod._reflect_instructions()
    assert "ORGANIZE" in prompts_instructions_mod._organize_instructions()
    assert "ENRICH" in prompts_instructions_mod._enrich_instructions()
    assert "SENSE-CHECK" in prompts_instructions_mod._sense_check_instructions()

    for stage in ("observe", "reflect", "organize", "enrich", "sense-check"):
        text = prompts_validation_mod._validation_requirements(stage)
        assert text.startswith("## Validation Requirements")


def test_observe_and_sense_prompt_builders_include_expected_context(tmp_path) -> None:
    observe = prompts_observe_mod.build_observe_batch_prompt(
        batch_index=1,
        total_batches=2,
        dimension_group=["naming_quality"],
        issues_subset={
            "review::src/a.py::abcdef12": {
                "title": "Naming issue",
                "description": "rename to clear name",
                "detail": {"dimension": "naming_quality", "file_path": "src/a.py"},
            }
        },
        repo_root=tmp_path,
    )
    assert "observe batch 1/2" in observe
    assert "naming_quality" in observe
    assert "[review::s" not in observe  # hash prefix truncation is used

    plan = {
        "clusters": {
            "cluster-a": {
                "issue_ids": ["id1"],
                "action_steps": [
                    {
                        "title": "Update handler",
                        "detail": "Edit src/a.py and rename fields",
                        "issue_refs": ["id1"],
                        "effort": "small",
                    }
                ],
            }
        }
    }
    content_prompt = prompts_sense_mod.build_sense_check_content_prompt(
        cluster_name="cluster-a",
        plan=plan,
        repo_root=tmp_path,
    )
    structure_prompt = prompts_sense_mod.build_sense_check_structure_prompt(
        plan=plan,
        repo_root=tmp_path,
    )
    assert "cluster `cluster-a`" in content_prompt
    assert "Current Steps" in content_prompt
    assert "cross-cluster dependencies" in structure_prompt


def test_run_stage_enrich_handles_no_queue_and_records_stage(tmp_path, capsys) -> None:
    args = argparse.Namespace(report="x" * 120, attestation=None)

    empty_services = _Services(plan={})
    stage_flow_mod.run_stage_enrich(
        args,
        services=empty_services,
        has_triage_in_queue_fn=lambda _plan: False,
        require_organize_stage_for_enrich_fn=lambda _stages: True,
        underspecified_steps_fn=lambda _plan: [],
        steps_with_bad_paths_fn=lambda _plan, _root: [],
        steps_without_effort_fn=lambda _plan: [],
        enrich_report_or_error_fn=lambda report: report,
        resolve_reusable_report_fn=lambda report, _existing: (report, False),
        record_enrich_stage_fn=lambda *_a, **_k: [],
    )
    assert "nothing to enrich" in capsys.readouterr().out.lower()

    plan = {
        "epic_triage_meta": {
            "triage_stages": {
                "organize": {"confirmed_at": "2026-03-09T00:00:00+00:00"}
            }
        }
    }
    services = _Services(plan=plan)

    def _record_enrich(stages: dict, *, report: str, shallow_count: int, existing_stage, is_reuse):
        stages["enrich"] = {
            "stage": "enrich",
            "report": report,
            "timestamp": "2026-03-09T00:00:00+00:00",
        }
        return []

    stage_flow_mod.run_stage_enrich(
        args,
        services=services,
        has_triage_in_queue_fn=lambda _plan: True,
        require_organize_stage_for_enrich_fn=lambda _stages: True,
        underspecified_steps_fn=lambda _plan: [],
        steps_with_bad_paths_fn=lambda _plan, _root: [],
        steps_without_effort_fn=lambda _plan: [],
        enrich_report_or_error_fn=lambda report: report,
        resolve_reusable_report_fn=lambda report, _existing: (report, False),
        record_enrich_stage_fn=_record_enrich,
        get_project_root_fn=lambda: tmp_path,
        print_user_message_fn=lambda _msg: None,
    )
    out = capsys.readouterr().out
    assert "Enrich stage recorded" in out
    assert "enrich" in plan["epic_triage_meta"]["triage_stages"]
    assert services.save_calls >= 2


def test_record_sense_stage_and_run_stage_sense_check(tmp_path, capsys) -> None:
    stages: dict = {}
    cleared = stage_flow_mod.record_sense_check_stage(
        stages,
        report="x" * 120,
        existing_stage=None,
        is_reuse=False,
        utc_now_fn=lambda: "2026-03-09T00:00:00+00:00",
        cascade_clear_later_confirmations_fn=lambda _stages, _name: ["sense-check"],
    )
    assert stages["sense-check"]["stage"] == "sense-check"
    assert cleared == ["sense-check"]

    plan = {
        "epic_triage_meta": {
            "triage_stages": {
                "enrich": {"confirmed_at": "2026-03-09T00:00:00+00:00"}
            }
        }
    }
    services = _Services(plan=plan)
    args = argparse.Namespace(report="y" * 120)

    def _record_sense(stages: dict, *, report: str, existing_stage, is_reuse):
        stages["sense-check"] = {
            "stage": "sense-check",
            "report": report,
            "timestamp": "2026-03-09T00:00:00+00:00",
        }
        return []

    stage_flow_mod.run_stage_sense_check(
        args,
        services=services,
        has_triage_in_queue_fn=lambda _plan: True,
        resolve_reusable_report_fn=lambda report, _existing: (report, False),
        record_sense_check_stage_fn=_record_sense,
        get_project_root_fn=lambda: tmp_path,
        underspecified_steps_fn=lambda _plan: [],
        steps_missing_issue_refs_fn=lambda _plan: [],
        steps_with_bad_paths_fn=lambda _plan, _root: [],
        steps_with_vague_detail_fn=lambda _plan, _root: [],
        steps_without_effort_fn=lambda _plan: [],
    )
    out = capsys.readouterr().out
    assert "Sense-check stage recorded" in out
    assert "sense-check" in plan["epic_triage_meta"]["triage_stages"]
    assert services.save_calls >= 2
