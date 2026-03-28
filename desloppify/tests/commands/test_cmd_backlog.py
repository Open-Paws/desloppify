"""Tests for desloppify.app.commands.backlog."""

from __future__ import annotations

from types import SimpleNamespace

import desloppify.app.commands.backlog.cmd as backlog_mod
from desloppify.app.commands.helpers.command_runtime import CommandRuntime


def _args(**overrides):
    base = {
        "count": 1,
        "scope": None,
        "status": "open",
        "group": "item",
        "format": "terminal",
        "explain": False,
        "output": None,
        "lang": None,
        "path": ".",
        "state": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_cmd_backlog_uses_backlog_queue(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        backlog_mod,
        "command_runtime",
        lambda _args: CommandRuntime(
            config={},
            state={"issues": {}, "dimension_scores": {}, "scan_path": ".", "last_scan": "2026-01-01"},
            state_path="/tmp/fake-state.json",
        ),
    )
    monkeypatch.setattr(backlog_mod, "require_issue_inventory", lambda _state: True)
    monkeypatch.setattr(backlog_mod, "check_config_staleness", lambda _config: None)

    def _build_and_render(*_args, **kwargs):
        captured["view"] = kwargs["view"]
        captured["deps"] = kwargs["deps"]

    monkeypatch.setattr(backlog_mod, "build_and_render_queue", _build_and_render)

    backlog_mod.cmd_backlog(_args())

    assert captured["view"] is backlog_mod.BACKLOG_QUEUE_VIEW
    deps = captured["deps"]
    assert isinstance(deps, backlog_mod.QueueRenderDeps)
    assert deps.build_work_queue_fn is backlog_mod.build_backlog_queue
