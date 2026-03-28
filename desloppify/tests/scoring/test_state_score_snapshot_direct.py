"""Direct coverage for the canonical state score snapshot facade."""

from __future__ import annotations

import desloppify.state_score_snapshot as state_score_snapshot_mod
from desloppify.engine._state.scoring import suppression_metrics as engine_suppression_metrics


def test_state_score_snapshot_loads_all_canonical_scores(monkeypatch) -> None:
    state = {"issues": {}}
    monkeypatch.setattr(state_score_snapshot_mod, "get_overall_score", lambda _state: 81.0)
    monkeypatch.setattr(state_score_snapshot_mod, "get_objective_score", lambda _state: 73.0)
    monkeypatch.setattr(state_score_snapshot_mod, "get_strict_score", lambda _state: 69.0)
    monkeypatch.setattr(
        state_score_snapshot_mod,
        "get_verified_strict_score",
        lambda _state: 64.0,
    )

    snapshot = state_score_snapshot_mod.score_snapshot(state)

    assert snapshot == state_score_snapshot_mod.ScoreSnapshot(
        overall=81.0,
        objective=73.0,
        strict=69.0,
        verified=64.0,
    )


def test_state_score_snapshot_reexports_public_helpers() -> None:
    assert state_score_snapshot_mod.suppression_metrics is engine_suppression_metrics
    assert "ScoreSnapshot" in state_score_snapshot_mod.__all__
    assert "score_snapshot" in state_score_snapshot_mod.__all__
    assert "suppression_metrics" in state_score_snapshot_mod.__all__
