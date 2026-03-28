"""Behavior tests for status command runtime flow."""

from __future__ import annotations

import json
from types import SimpleNamespace

from desloppify.state_io import empty_state
import desloppify.app.commands.status.cmd as status_cmd_mod


def _runtime(*, state: dict | None = None, config: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        state=state if state is not None else empty_state(),
        config=config if config is not None else {},
        state_path=None,
    )


def test_cmd_status_json_mode_bypasses_scan_gate(monkeypatch, capsys) -> None:
    state = empty_state()
    state["scan_count"] = 7
    runtime = _runtime(state=state)

    monkeypatch.setattr(status_cmd_mod, "command_runtime", lambda _args: runtime)
    monkeypatch.setattr(
        status_cmd_mod,
        "scorecard_dimensions_payload",
        lambda *_args, **_kwargs: [
            {"name": "api_surface", "subjective": True},
            {"name": "objective", "subjective": False},
        ],
    )
    monkeypatch.setattr(status_cmd_mod, "suppression_metrics", lambda _state: {})

    def _scan_gate_should_not_run(_state: dict) -> bool:
        raise AssertionError("require_issue_inventory should not run for --json")

    monkeypatch.setattr(status_cmd_mod, "require_issue_inventory", _scan_gate_should_not_run)

    status_cmd_mod.cmd_status(SimpleNamespace(json=True))
    payload = json.loads(capsys.readouterr().out)
    assert payload["scan_count"] == 7
    assert payload["subjective_measures"] == [{"name": "api_surface", "subjective": True}]


def test_cmd_status_terminal_mode_stops_when_scan_incomplete(monkeypatch) -> None:
    runtime = _runtime()
    monkeypatch.setattr(status_cmd_mod, "command_runtime", lambda _args: runtime)
    monkeypatch.setattr(status_cmd_mod, "scorecard_dimensions_payload", lambda *_a, **_k: [])
    monkeypatch.setattr(status_cmd_mod, "suppression_metrics", lambda _state: {})
    monkeypatch.setattr(status_cmd_mod, "require_issue_inventory", lambda _state: False)

    called = {"rendered": False}

    def _render(*_args, **_kwargs) -> None:
        called["rendered"] = True

    monkeypatch.setattr(status_cmd_mod, "render_terminal_status", _render)

    status_cmd_mod.cmd_status(SimpleNamespace(json=False))
    assert called["rendered"] is False


def test_cmd_status_terminal_mode_passes_computed_context(monkeypatch) -> None:
    state = empty_state()
    state["stats"] = {"open": 3}
    state["dimension_scores"] = {"code quality": {"score": 88.0}}
    runtime = _runtime(state=state, config={"target_strict_score": 95})

    scorecard = [
        {"name": "quality", "subjective": False},
        {"name": "design", "subjective": True},
    ]
    captured: dict[str, object] = {}

    monkeypatch.setattr(status_cmd_mod, "command_runtime", lambda _args: runtime)
    monkeypatch.setattr(
        status_cmd_mod,
        "scorecard_dimensions_payload",
        lambda *_args, **_kwargs: scorecard,
    )
    monkeypatch.setattr(status_cmd_mod, "suppression_metrics", lambda _state: {"x": 1})
    monkeypatch.setattr(status_cmd_mod, "require_issue_inventory", lambda _state: True)

    def _render(args, **kwargs) -> None:
        captured["args"] = args
        captured.update(kwargs)

    monkeypatch.setattr(status_cmd_mod, "render_terminal_status", _render)

    args = SimpleNamespace(json=False)
    status_cmd_mod.cmd_status(args)

    assert captured["args"] is args
    assert captured["state"] is state
    assert captured["config"] == {"target_strict_score": 95}
    assert captured["stats"] == {"open": 3}
    assert captured["scorecard_dims"] == scorecard
    assert captured["subjective_measures"] == [{"name": "design", "subjective": True}]
    assert captured["suppression"] == {"x": 1}
