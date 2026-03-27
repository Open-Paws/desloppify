"""Tests for status score sparklines."""

from __future__ import annotations

from types import SimpleNamespace

import desloppify.app.commands.status.flow as flow_mod
from desloppify.app.commands.status.sparkline import (
    extract_strict_trend,
    render_sparkline,
)

SPARK_CHARS = set("▁▂▃▄▅▆▇█")


def _sparkline_lines(output: str) -> list[str]:
    return [
        line
        for line in output.splitlines()
        if line.startswith("  ") and set(line.strip()) <= SPARK_CHARS and line.strip()
    ]


def test_render_sparkline_returns_empty_for_short_sequences() -> None:
    assert render_sparkline([]) == ""
    assert render_sparkline([80.0, 81.0]) == ""


def test_render_sparkline_preserves_exact_length_for_short_input() -> None:
    spark = render_sparkline([70.0, 72.0, 74.0, 76.0])
    assert len(spark) == 4


def test_render_sparkline_returns_flat_line_for_equal_values() -> None:
    assert render_sparkline([80.0, 80.0, 80.0]) == "▄▄▄"


def test_render_sparkline_increasing_sequence_spans_low_to_high() -> None:
    spark = render_sparkline([70.0, 75.0, 80.0, 85.0])
    assert spark[0] == "▁"
    assert spark[-1] == "█"


def test_render_sparkline_decreasing_sequence_spans_high_to_low() -> None:
    spark = render_sparkline([85.0, 80.0, 75.0, 70.0])
    assert spark[0] == "█"
    assert spark[-1] == "▁"


def test_render_sparkline_resamples_longer_input_to_requested_width() -> None:
    spark = render_sparkline([float(score) for score in range(30)], width=10)
    assert len(spark) == 10
    assert spark[0] == "▁"
    assert spark[-1] == "█"


def test_extract_strict_trend_filters_to_plan_checkpoints() -> None:
    events = [
        {"event_type": "scan_complete", "payload": {"scores": {"strict": 70.0}}},
        {"event_type": "plan_checkpoint", "payload": {"scores": {"strict": 71.0}}},
        {"event_type": "plan_checkpoint", "payload": {"scores": {"strict": 72.5}}},
    ]

    assert extract_strict_trend(events) == [71.0, 72.5]


def test_extract_strict_trend_returns_empty_without_checkpoints() -> None:
    assert extract_strict_trend([]) == []
    assert extract_strict_trend([{"event_type": "scan_complete"}]) == []


def test_extract_strict_trend_skips_malformed_entries() -> None:
    events = [
        None,
        {"event_type": "plan_checkpoint"},
        {"event_type": "plan_checkpoint", "payload": []},
        {"event_type": "plan_checkpoint", "payload": {"scores": []}},
        {"event_type": "plan_checkpoint", "payload": {"scores": {"strict": "82.0"}}},
        {"event_type": "plan_checkpoint", "payload": {"scores": {"strict": True}}},
        {"event_type": "plan_checkpoint", "payload": {"scores": {"strict": 83.0}}},
    ]

    assert extract_strict_trend(events) == [83.0]


def test_print_score_section_renders_sparkline_when_three_checkpoints_exist(
    capsys, monkeypatch
) -> None:
    monkeypatch.setattr(flow_mod, "get_plan_start_strict", lambda _plan: None)
    monkeypatch.setattr(flow_mod, "plan_aware_queue_breakdown", lambda *_a, **_k: None)
    monkeypatch.setattr(flow_mod, "colorize", lambda text, _style=None: text)

    def fake_load_progression():
        return [
            {"event_type": "plan_checkpoint", "payload": {"scores": {"strict": 70.0}}},
            {"event_type": "plan_checkpoint", "payload": {"scores": {"strict": 72.0}}},
            {"event_type": "plan_checkpoint", "payload": {"scores": {"strict": 75.0}}},
        ]

    monkeypatch.setattr("desloppify.engine._state.progression.load_progression", fake_load_progression)

    flow_mod.print_score_section(
        state={},
        scores=SimpleNamespace(overall=90.0, objective=95.0, strict=85.0, verified=84.0),
        plan={},
        target_strict_score=95.0,
        ctx=SimpleNamespace(),
    )

    out = capsys.readouterr().out
    spark_lines = _sparkline_lines(out)
    assert len(spark_lines) == 1
    assert spark_lines[0].startswith("  ")
    assert "Trend" not in spark_lines[0]
    assert "70" not in spark_lines[0]


def test_print_score_section_omits_sparkline_when_checkpoint_count_is_below_three(
    capsys, monkeypatch
) -> None:
    monkeypatch.setattr(flow_mod, "get_plan_start_strict", lambda _plan: None)
    monkeypatch.setattr(flow_mod, "plan_aware_queue_breakdown", lambda *_a, **_k: None)
    monkeypatch.setattr(flow_mod, "colorize", lambda text, _style=None: text)

    def fake_load_progression():
        return [
            {"event_type": "plan_checkpoint", "payload": {"scores": {"strict": 70.0}}},
            {"event_type": "plan_checkpoint", "payload": {"scores": {"strict": 72.0}}},
        ]

    monkeypatch.setattr("desloppify.engine._state.progression.load_progression", fake_load_progression)

    flow_mod.print_score_section(
        state={},
        scores=SimpleNamespace(overall=90.0, objective=95.0, strict=85.0, verified=84.0),
        plan={},
        target_strict_score=95.0,
        ctx=SimpleNamespace(),
    )

    out = capsys.readouterr().out
    assert _sparkline_lines(out) == []


def test_print_score_section_ignores_sparkline_failures(
    capsys, monkeypatch
) -> None:
    monkeypatch.setattr(flow_mod, "get_plan_start_strict", lambda _plan: None)
    monkeypatch.setattr(flow_mod, "plan_aware_queue_breakdown", lambda *_a, **_k: None)
    monkeypatch.setattr(flow_mod, "colorize", lambda text, _style=None: text)

    def raising_load_progression():
        raise OSError("broken progression")

    monkeypatch.setattr(
        "desloppify.engine._state.progression.load_progression",
        raising_load_progression,
    )

    flow_mod.print_score_section(
        state={},
        scores=SimpleNamespace(overall=90.0, objective=95.0, strict=85.0, verified=84.0),
        plan={},
        target_strict_score=95.0,
        ctx=SimpleNamespace(),
    )

    out = capsys.readouterr().out
    assert "Scores: overall 90.0/100" in out
    assert _sparkline_lines(out) == []
