from __future__ import annotations

from desloppify.app.commands.plan.shared import patterns as resolve_mod


def test_resolve_ids_from_patterns_matches_literal_synthetic_queue_id(
    monkeypatch,
) -> None:
    state = {"issues": {}}

    monkeypatch.setattr(
        resolve_mod,
        "build_work_queue",
        lambda *_args, **_kwargs: {"items": [{"id": "subjective::design_coherence"}]},
    )

    result = resolve_mod.resolve_ids_from_patterns(
        state,
        ["subjective::design_coherence"],
        plan={},
    )

    assert result == ["subjective::design_coherence"]


def test_resolve_ids_from_patterns_matches_wildcard_synthetic_queue_ids(
    monkeypatch,
) -> None:
    state = {"issues": {}}

    monkeypatch.setattr(
        resolve_mod,
        "build_work_queue",
        lambda *_args, **_kwargs: {
            "items": [
                {"id": "subjective::design_coherence"},
                {"id": "subjective::error_consistency"},
                {"id": "workflow::create-plan"},
            ]
        },
    )

    result = resolve_mod.resolve_ids_from_patterns(
        state,
        ["subjective::*"],
        plan={},
    )

    assert result == [
        "subjective::design_coherence",
        "subjective::error_consistency",
    ]
