"""Regression tests for subjective issue visibility in `desloppify status` output."""

from __future__ import annotations

from desloppify.app.commands.status import render as status_render
from desloppify.app.commands.status import render_dimensions as render_dims_mod


def _subjective_dim(score: float, strict: float, dimension_key: str) -> dict:
    return {
        "score": score,
        "strict": strict,
        "checks": 0,
        "failing": 0,
        "tier": 4,
        "detectors": {
            "subjective_assessment": {
                "dimension_key": dimension_key,
            }
        },
    }


def test_status_renders_open_issue_count_for_subjective_dimension(monkeypatch, capsys):
    monkeypatch.setattr(status_render, "colorize", lambda text, _style: text)
    monkeypatch.setattr(render_dims_mod, "dimension_bar", lambda *_args, **_kwargs: "BAR")

    state = {
        "issues": {
            "review-1": {
                "status": "open",
                "detector": "review",
                "detail": {"dimension": "abstraction_fitness"},
            }
        }
    }
    dim_scores = {
        "Abstraction fit": _subjective_dim(68.8, 68.8, "abstraction_fitness"),
    }

    status_render.show_dimension_table(state, dim_scores)
    out = capsys.readouterr().out

    assert "[open issues: 1]" in out


def test_status_renders_zero_open_issue_hint_for_low_subjective_score(monkeypatch, capsys):
    monkeypatch.setattr(status_render, "colorize", lambda text, _style: text)
    monkeypatch.setattr(render_dims_mod, "dimension_bar", lambda *_args, **_kwargs: "BAR")

    state = {"issues": {}}
    dim_scores = {
        "Abstraction fit": _subjective_dim(68.8, 68.8, "abstraction_fitness"),
    }

    status_render.show_dimension_table(state, dim_scores)
    out = capsys.readouterr().out

    assert "[open issues: 0]" in out
