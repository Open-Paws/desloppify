"""Direct tests for triage stage-policy and reflect-accounting helpers."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from desloppify.base.exception_sets import CommandError
from desloppify.app.commands.plan.triage import workflow as triage_workflow_mod
from desloppify.app.commands.plan.triage.validation import (
    reflect_accounting as reflect_accounting_mod,
)
from desloppify.app.commands.plan.triage.validation import (
    stage_policy as stage_policy_mod,
)
from desloppify.engine.plan_triage import compute_triage_progress


def test_confirm_stage_records_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(stage_policy_mod, "utc_now", lambda: "2026-03-12T12:00:00Z")
    saved: list[dict] = []
    plan = {"clusters": {}}
    stage_record: dict[str, str] = {}

    ok = stage_policy_mod.confirm_stage(
        plan=plan,
        stage_record=stage_record,
        attestation=(
            "I verified the observe stage against the naming_quality findings "
            "in this batch and confirmed the stage summary is accurate."
        ),
        request=stage_policy_mod.AutoConfirmStageRequest(
            stage_name="observe",
            stage_label="Observe",
            blocked_heading="blocked",
            confirm_cmd="cmd",
            inline_hint="hint",
            dimensions=["naming_quality"],
        ),
        save_plan_fn=lambda current_plan: saved.append(dict(current_plan)),
    )

    assert ok is True
    assert stage_record["confirmed_at"] == "2026-03-12T12:00:00Z"
    assert "verified the observe stage" in stage_record["confirmed_text"]
    assert len(saved) == 1


def test_compute_triage_progress_blocks_sense_check_until_enrich_confirmed() -> None:
    stages = {
        "observe": {"report": "obs", "confirmed_at": "2026-03-12T12:00:00Z"},
        "reflect": {"report": "ref", "confirmed_at": "2026-03-12T12:05:00Z"},
        "organize": {"report": "org", "confirmed_at": "2026-03-12T12:10:00Z"},
        "enrich": {"report": "ready but not confirmed"},
    }

    progress = compute_triage_progress(stages)

    assert progress.current_stage is None
    assert progress.next_command == "desloppify plan triage --confirm enrich"
    assert progress.blocked_reason == (
        "Verify accuracy, structure & value blocked until Make steps executor-ready (detail, refs) is confirmed."
    )


def test_validate_reflect_accounting_accepts_coverage_ledger() -> None:
    report = """
## Coverage Ledger
- abc12345 -> cluster "triage-runtime"
- def67890 -> skip "duplicate"
""".strip()

    ok, cited, missing, duplicates = reflect_accounting_mod.validate_reflect_accounting(
        report=report,
        valid_ids={
            "review::runtime::abc12345",
            "review::runtime::def67890",
        },
    )

    assert ok is True
    assert cited == {
        "review::runtime::abc12345",
        "review::runtime::def67890",
    }
    assert missing == []
    assert duplicates == []


def test_read_report_file_raises_command_error_for_missing_file() -> None:
    with pytest.raises(CommandError, match="--report-file not found"):
        triage_workflow_mod._read_report_file("missing-report.txt")


def test_run_staged_runner_raises_command_error_for_invalid_stage() -> None:
    args = argparse.Namespace(runner="codex", only_stages="observe,invalid")

    with pytest.raises(CommandError, match="Unknown stage"):
        triage_workflow_mod._run_staged_runner(
            args,
            services=object(),  # type: ignore[arg-type]
        )


def test_run_staged_runner_raises_command_error_for_unknown_runner() -> None:
    args = argparse.Namespace(runner="invalid", only_stages=None)

    with pytest.raises(CommandError, match="Unknown runner"):
        triage_workflow_mod._run_staged_runner(
            args,
            services=object(),  # type: ignore[arg-type]
        )


def test_reflect_accounting_module_is_file_backed() -> None:
    module_path = Path(reflect_accounting_mod.__file__)
    assert module_path.name == "reflect_accounting.py"
