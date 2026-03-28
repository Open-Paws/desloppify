"""Direct coverage tests for triage stage display helpers."""

from __future__ import annotations

from types import SimpleNamespace

import desloppify.app.commands.plan.triage.stages.rendering as stage_rendering_mod


def test_print_observe_report_requirement_emits_guidance(monkeypatch, capsys) -> None:
    monkeypatch.setattr(stage_rendering_mod, "colorize", lambda text, _style: text)

    stage_rendering_mod._print_observe_report_requirement()

    out = capsys.readouterr().out
    assert "--report is required for --stage observe" in out
    assert "Verify the queued issues one by one against the code" in out
    assert "Cite the files you read" in out


def test_print_complete_summary_emits_stage_details(monkeypatch, capsys) -> None:
    monkeypatch.setattr(stage_rendering_mod, "colorize", lambda text, _style: text)
    monkeypatch.setattr(
        stage_rendering_mod,
        "manual_clusters_with_issues",
        lambda _plan: ["cluster-alpha"],
    )
    plan = {
        "clusters": {
            "cluster-alpha": {
                "action_steps": [
                    "extract module",
                    "add tests",
                ]
            }
        }
    }
    stages = {
        "observe": {"issue_count": 5},
        "reflect": {"recurring_dims": ["structure"]},
        "organize": {"issue_count": 5},
        "enrich": {"shallow_count": 0},
        "sense-check": {"ok": True},
    }

    stage_rendering_mod._print_complete_summary(plan, stages)

    out = capsys.readouterr().out
    assert "Triage summary" in out
    assert "Observe: 5 issues analysed" in out
    assert "cluster-alpha: 2 steps" in out
    assert "Sense-check: content, structure & value verified" in out


def test_print_new_issues_since_last_lists_ids_and_summaries(monkeypatch, capsys) -> None:
    monkeypatch.setattr(stage_rendering_mod, "colorize", lambda text, _style: text)
    monkeypatch.setattr(stage_rendering_mod, "short_issue_id", lambda fid: fid.split("::")[-1])

    si = SimpleNamespace(
        new_since_last={"review::abc123"},
        open_issues={"review::abc123": {"summary": "new summary"}},
    )

    stage_rendering_mod._print_new_issues_since_last(si)

    out = capsys.readouterr().out
    assert "1 new issue(s) since last triage" in out
    assert "[abc123] new summary" in out
