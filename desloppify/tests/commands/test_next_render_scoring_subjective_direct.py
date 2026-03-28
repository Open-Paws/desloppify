"""Direct tests for next render_scoring and subjective helper modules."""

from __future__ import annotations

from types import SimpleNamespace

import desloppify.app.commands.next.render_scoring as render_scoring_mod
import desloppify.app.commands.next.subjective as subjective_mod


def _colorize(text: str, _tone: str | None = None) -> str:
    return text


def test_low_subjective_dimensions_ignores_placeholders_and_sorts(monkeypatch) -> None:
    monkeypatch.setattr(
        subjective_mod,
        "_scorecard_subjective_impl",
        lambda _state, _dims: [
            {"name": "Naming quality", "strict": 92.0, "failing": 1},
            {"name": "Error consistency", "score": 81.0, "failing": 4},
            {"name": "Elegance", "strict": 70.0, "failing": 2, "placeholder": True},
            {"name": "Logic clarity", "strict": 67.5, "failing": 3},
        ],
    )

    low = subjective_mod._low_subjective_dimensions({}, {}, threshold=90.0)
    assert low == [
        ("Logic clarity", 67.5, 3),
        ("Error consistency", 81.0, 4),
    ]


def test_scorecard_subjective_passthrough(monkeypatch) -> None:
    expected = [{"name": "Naming quality"}]
    monkeypatch.setattr(
        subjective_mod,
        "_scorecard_subjective_impl",
        lambda _state, _scores: expected,
    )
    assert subjective_mod._scorecard_subjective({}, {}) is expected


def test_render_dimension_context_prints_dimension_details(capsys) -> None:
    dim_scores = {
        "Test health": {
            "score": 82.0,
            "strict": 80.0,
            "checks": 200,
            "failing": 8,
        }
    }

    render_scoring_mod.render_dimension_context(
        "unused",
        dim_scores,
        colorize_fn=_colorize,
        get_dimension_for_detector_fn=lambda _det: SimpleNamespace(name="Test health"),
    )
    out = capsys.readouterr().out
    assert "Dimension: Test health" in out
    assert "strict: 80.0%" in out


def test_render_detector_impact_estimate_supports_single_and_bulk_paths(capsys) -> None:
    dim_scores = {"Code quality": {"score": 75.0, "checks": 100, "failing": 5}}

    render_scoring_mod.render_detector_impact_estimate(
        "smells",
        dim_scores,
        {"smells": 5},
        colorize_fn=_colorize,
        log_fn=lambda _msg: None,
        compute_score_impact_fn=lambda *_a, **_k: 0.4,
        get_dimension_for_detector_fn=lambda _det: SimpleNamespace(name="Code quality"),
    )
    single_out = capsys.readouterr().out
    assert "worth ~+0.4 pts" in single_out

    def _impact(_scores, _pots, _detector, issues_to_fix):
        return 0.0 if issues_to_fix == 1 else 1.3

    render_scoring_mod.render_detector_impact_estimate(
        "smells",
        dim_scores,
        {"smells": 5},
        colorize_fn=_colorize,
        log_fn=lambda _msg: None,
        compute_score_impact_fn=_impact,
        get_dimension_for_detector_fn=lambda _det: SimpleNamespace(name="Code quality"),
    )
    bulk_out = capsys.readouterr().out
    assert "fixing all 5 smells issues" in bulk_out
    assert "~+1.3 pts" in bulk_out


def test_render_detector_impact_estimate_logs_exceptions() -> None:
    logs: list[str] = []

    render_scoring_mod.render_detector_impact_estimate(
        "unused",
        {"Test health": {"score": 90.0, "checks": 10, "failing": 2}},
        {"unused": 2},
        colorize_fn=_colorize,
        log_fn=logs.append,
        compute_score_impact_fn=lambda *_a, **_k: (_ for _ in ()).throw(TypeError("bad")),
        get_dimension_for_detector_fn=lambda _det: SimpleNamespace(name="Test health"),
    )
    assert logs
    assert "score impact estimate skipped" in logs[0]


def test_render_review_dimension_drag_and_score_impact_branch(capsys) -> None:
    item = {"detector": "review", "detail": {"dimension": "naming_quality"}}

    render_scoring_mod.render_score_impact(
        item,
        dim_scores={"Naming quality": {"score": 77.0, "checks": 10, "failing": 1}},
        potentials=None,
        colorize_fn=_colorize,
        log_fn=lambda _msg: None,
        compute_health_breakdown_fn=lambda _scores: {
            "entries": [{"name": "Naming quality", "overall_drag": 0.22}]
        },
        compute_score_impact_fn=lambda *_a, **_k: 0.0,
        get_dimension_for_detector_fn=lambda _det: None,
    )
    out = capsys.readouterr().out
    assert "Dimension drag" in out
    assert "-0.22 pts" in out


def test_render_item_explain_covers_detector_and_review_dimension_paths(capsys) -> None:
    dim_scores = {"Test health": {"score": 88.0, "failing": 6}}
    render_scoring_mod.render_item_explain(
        item={
            "id": "unused::a.py::x",
            "detector": "unused",
            "explain": {"count": 6, "policy": "priority from plan"},
        },
        detail={"count": 3},
        confidence="high",
        dim_scores=dim_scores,
        colorize_fn=_colorize,
        get_dimension_for_detector_fn=lambda _det: SimpleNamespace(name="Test health"),
    )
    detector_out = capsys.readouterr().out
    assert "confidence=high" in detector_out
    assert "Dimension: Test health at 88.0%" in detector_out
    assert "priority from plan" in detector_out

    render_scoring_mod.render_item_explain(
        item={
            "id": "review::naming",
            "detector": "review",
            "detail": {"dimension": "naming_quality"},
            "explain": {},
        },
        detail={"count": 1},
        confidence="medium",
        dim_scores={"Naming quality": {"score": 85.5}},
        colorize_fn=_colorize,
        get_dimension_for_detector_fn=lambda _det: None,
    )
    review_out = capsys.readouterr().out
    assert "Subjective dimension: Naming quality at 85.5%" in review_out
