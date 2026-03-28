"""Direct coverage tests for next-command helper modules."""

from __future__ import annotations

import argparse
from types import SimpleNamespace

import desloppify.app.commands.helpers.queue_progress_render as queue_render_mod
import desloppify.app.commands.next.flow_helpers as flow_helpers_mod
import desloppify.app.commands.next.options as options_mod
import desloppify.app.commands.next.render_support as support_mod
import desloppify.app.commands.next.render_workflow as workflow_render_mod


def test_next_options_from_args_defaults_and_overrides() -> None:
    defaults = options_mod.NextOptions.from_args(argparse.Namespace())
    assert defaults.count == 1
    assert defaults.status == "open"
    assert defaults.output_format == "terminal"

    args = argparse.Namespace(
        count=5,
        scope="src/",
        status="all",
        group="detector",
        explain=True,
        cluster="auto/test",
        include_skipped=True,
        output="out.txt",
        format="json",
    )
    parsed = options_mod.NextOptions.from_args(args)
    assert parsed.count == 5
    assert parsed.scope == "src/"
    assert parsed.output_file == "out.txt"
    assert parsed.output_format == "json"


def test_flow_helpers_focus_context_and_safe_merge(monkeypatch) -> None:
    plan = {"active_cluster": "auto/test"}
    assert flow_helpers_mod.resolve_cluster_focus(plan, cluster_arg=None, scope=None) == "auto/test"
    assert flow_helpers_mod.resolve_cluster_focus(plan, cluster_arg="manual", scope=None) == "manual"

    monkeypatch.setattr(flow_helpers_mod, "get_plan_start_strict", lambda _plan: 88.1)
    monkeypatch.setattr(flow_helpers_mod, "plan_aware_queue_breakdown", lambda *_a, **_k: {"ok": True})
    strict, breakdown = flow_helpers_mod.plan_queue_context(state={}, plan_data=plan, context=None)
    assert strict == 88.1
    assert breakdown == {"ok": True}

    monkeypatch.setattr(flow_helpers_mod, "merge_potentials", lambda _raw: (_ for _ in ()).throw(TypeError("bad")))
    raw = {"a": 1}
    assert flow_helpers_mod.merge_potentials_safe(raw) == raw


def test_queue_progress_render_helpers() -> None:
    breakdown = SimpleNamespace(
        queue_total=3,
        workflow=1,
        plan_ordered=2,
        skipped=1,
        subjective=0,
        focus_cluster=None,
        focus_cluster_count=0,
        focus_cluster_total=0,
    )
    assert queue_render_mod.format_plan_delta(80.0, 79.0) == "+1.0"
    assert queue_render_mod.format_plan_delta(80.0, 80.02) == ""
    headline = queue_render_mod.format_queue_headline(breakdown)
    assert headline.startswith("Queue: 3")
    assert "1 planning step" in headline
    assert "2 planned" in headline
    assert "1 skipped" in headline
    block = queue_render_mod.format_queue_block(breakdown, frozen_score=79.0, live_score=80.0)
    assert any("strict 80.0/100" in line and "+1.0" in line for line, _tone in block)


def test_cluster_action_commands_are_parseable_semantic_fields() -> None:
    commands = support_mod.cluster_action_commands("manual/refactor-a")
    assert sorted(commands) == ["drill_in", "resolve_all", "skip"]
    assert commands["drill_in"] == "desloppify next --cluster manual/refactor-a --count 10"
    assert commands["skip"] == "desloppify plan skip manual/refactor-a"
    assert (
        commands["resolve_all"]
        == 'desloppify plan resolve "manual/refactor-a" --note "<what>" --confirm'
    )


def test_workflow_render_helpers(capsys) -> None:
    assert workflow_render_mod.step_text("x") == "x"
    assert workflow_render_mod.step_text({"title": "Do thing"}) == "Do thing"

    workflow_render_mod.render_workflow_action(
        {"summary": "Create plan", "primary_command": "desloppify plan triage"},
        colorize_fn=lambda text, _tone=None: text,
    )
    stage_item = {
        "summary": "Triage: Reflect",
        "detail": {"total_review_issues": 5},
        "is_blocked": True,
        "blocked_by": ["triage::observe"],
    }
    workflow_render_mod.render_workflow_stage(
        stage_item,
        colorize_fn=lambda text, _tone=None: text,
        workflow_stage_name_fn=lambda _item: "reflect",
    )
    out = capsys.readouterr().out
    assert "Planning step" in out
    assert "Blocked by: observe" in out


def test_workflow_render_action_shows_decision_options(capsys) -> None:
    workflow_render_mod.render_workflow_action(
        {
            "summary": "Deferred backlog",
            "detail": {
                "planning_tools": [
                    {
                        "label": "Review deferred backlog",
                        "command": "desloppify plan queue --include-skipped",
                    },
                ],
                "decision_options": [
                    {"label": "Reactivate", "command": 'desloppify plan unskip "*"'},
                    {"label": "Wontfix", "command": 'desloppify plan skip --permanent "*"'},
                ]
            },
            "primary_command": 'desloppify plan unskip "*"',
        },
        colorize_fn=lambda text, _tone=None: text,
    )
    out = capsys.readouterr().out
    assert "Planning tools" in out
    assert "plan queue --include-skipped" in out
    assert "Decision options" in out
    assert "Reactivate" in out
    assert "Wontfix" in out
