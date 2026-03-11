"""Direct tests for status command flow helpers."""

from __future__ import annotations

import argparse
from types import SimpleNamespace

import desloppify.app.commands.status.flow as flow_mod
from desloppify.app.commands.helpers.queue_progress import QueueBreakdown


def test_print_score_section_frozen_mode_uses_frozen_renderer(monkeypatch) -> None:
    frozen_calls: list[tuple[float, float]] = []
    breakdown = QueueBreakdown(queue_total=3, subjective=1)
    monkeypatch.setattr(flow_mod, "get_plan_start_strict", lambda _plan: 80.0)
    monkeypatch.setattr(flow_mod, "plan_aware_queue_breakdown", lambda *_a, **_k: breakdown)
    monkeypatch.setattr(
        flow_mod,
        "print_frozen_score_with_queue_context",
        lambda _breakdown, frozen_strict, live_score: frozen_calls.append((frozen_strict, live_score)),
    )

    result = flow_mod.print_score_section(
        state={},
        scores=SimpleNamespace(overall=90.0, objective=95.0, strict=85.0, verified=84.0),
        plan={},
        target_strict_score=95.0,
        ctx=SimpleNamespace(),
    )

    assert result is breakdown
    assert result.queue_total == 3
    assert result.subjective == 1
    assert result.objective_actionable == 2
    assert frozen_calls == [(80.0, 85.0)]


def test_print_score_section_phase_transition_renders_live_scores(capsys, monkeypatch) -> None:
    breakdown = QueueBreakdown(queue_total=2, subjective=1, workflow=1)
    monkeypatch.setattr(flow_mod, "get_plan_start_strict", lambda _plan: 80.0)
    monkeypatch.setattr(flow_mod, "plan_aware_queue_breakdown", lambda *_a, **_k: breakdown)
    monkeypatch.setattr(flow_mod, "colorize", lambda text, _style=None: text)

    result = flow_mod.print_score_section(
        state={},
        scores=SimpleNamespace(overall=90.0, objective=95.0, strict=85.0, verified=84.0),
        plan={},
        target_strict_score=95.0,
        ctx=SimpleNamespace(),
    )

    out = capsys.readouterr().out
    assert result == breakdown
    assert "Scores: overall 90.0/100" in out
    assert "objective 95.0/100" in out
    assert "strict 85.0/100" in out
    assert "verified 84.0/100" in out
    assert "Queue: 2 items" in out
    assert "Objective queue complete (plan-start was 80.0)." in out
    assert "subjective + workflow items remain" in out


def test_render_terminal_status_writes_query_payload_with_empty_plan(monkeypatch) -> None:
    written: list[flow_mod.StatusQueryRequest] = []
    monkeypatch.setattr(flow_mod, "load_plan", lambda: {})
    monkeypatch.setattr(flow_mod, "write_status_query", lambda request: written.append(request))

    flow_mod.render_terminal_status(
        argparse.Namespace(path=".", lang=None),
        state={
            "issues": {},
            "potentials": {},
            "scan_path": ".",
            "scan_root": ".",
            "suppression": {},
            "files_scanned": 0,
            "scan_count": 0,
        },
        config={"review_max_age_days": 7},
        stats={"by_tier": {}},
        dim_scores={},
        scorecard_dims=[],
        subjective_measures=[],
        suppression={},
    )

    assert len(written) == 1
    payload = written[0]
    assert payload.plan is None
    assert payload.state["scan_path"] == "."
    assert payload.stats["by_tier"] == {}
    assert payload.by_tier == {}
    assert payload.dim_scores == {}
    assert payload.scorecard_dims == []
    assert payload.subjective_measures == []
    assert payload.suppression == {}
