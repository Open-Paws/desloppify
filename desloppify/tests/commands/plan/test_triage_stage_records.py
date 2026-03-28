"""Direct coverage tests for triage stage record helpers."""

from __future__ import annotations

import desloppify.app.commands.plan.triage.stages.records as stage_records_mod


def test_resolve_reusable_report_prefers_explicit_report() -> None:
    report, reused = stage_records_mod.resolve_reusable_report(
        report="new report",
        existing_stage={"report": "old report"},
    )
    assert report == "new report"
    assert reused is False


def test_resolve_reusable_report_reuses_existing_report() -> None:
    report, reused = stage_records_mod.resolve_reusable_report(
        report=None,
        existing_stage={"report": "existing report"},
    )
    assert report == "existing report"
    assert reused is True


def test_record_observe_stage_clears_later_confirmations(monkeypatch) -> None:
    monkeypatch.setattr(stage_records_mod, "utc_now", lambda: "2026-03-08T00:00:00+00:00")
    stages = {
        "reflect": {
            "confirmed_at": "2026-03-01T00:00:00+00:00",
            "confirmed_text": "confirmed",
        }
    }

    cleared = stage_records_mod.record_observe_stage(
        stages,
        report="observe analysis",
        issue_count=3,
        cited_ids=["review::abc"],
        existing_stage={"confirmed_at": "2026-03-01T00:00:00+00:00", "confirmed_text": "x"},
        is_reuse=False,
    )

    assert cleared == ["reflect"]
    assert "confirmed_at" not in stages["observe"]
    assert "confirmed_text" not in stages["observe"]
    assert "confirmed_at" not in stages["reflect"]
    assert stages["observe"]["issue_count"] == 3
    assert stages["observe"]["cited_ids"] == ["review::abc"]


def test_record_organize_stage_reuse_keeps_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(stage_records_mod, "utc_now", lambda: "2026-03-08T00:00:00+00:00")
    stages: dict = {}

    _cleared = stage_records_mod.record_organize_stage(
        stages,
        report="organize analysis",
        issue_count=7,
        existing_stage={
            "confirmed_at": "2026-03-07T00:00:00+00:00",
            "confirmed_text": "looks good",
        },
        is_reuse=True,
    )

    assert stages["organize"]["issue_count"] == 7
    assert stages["organize"]["confirmed_at"] == "2026-03-07T00:00:00+00:00"
    assert stages["organize"]["confirmed_text"] == "looks good"


def test_record_confirm_existing_completion_sets_confirmed_fields(monkeypatch) -> None:
    monkeypatch.setattr(stage_records_mod, "utc_now", lambda: "2026-03-08T00:00:00+00:00")
    stages: dict = {}

    stage_records_mod.record_confirm_existing_completion(
        stages=stages,
        note="existing plan is still valid",
        issue_count=11,
        confirmed_text="confirmed by reviewer",
    )

    organize = stages["organize"]
    assert organize["stage"] == "organize"
    assert organize["issue_count"] == 11
    assert organize["confirmed_at"] == "2026-03-08T00:00:00+00:00"
    assert organize["confirmed_text"] == "confirmed by reviewer"
    assert organize["report"].startswith("[confirmed-existing]")
    assert organize["reused_existing_plan"] is True
    assert organize["completion_note"] == "existing plan is still valid"
