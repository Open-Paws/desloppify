"""Tests for desloppify.app.commands.exclude."""

from __future__ import annotations

from types import SimpleNamespace

import desloppify.app.commands.exclude as exclude_mod
from desloppify.app.commands.helpers.command_runtime import CommandRuntime


def _args(pattern: str, runtime: CommandRuntime) -> SimpleNamespace:
    return SimpleNamespace(pattern=pattern, runtime=runtime)


def test_cmd_exclude_marks_config_stale_without_state_changes(
    monkeypatch,
    tmp_path,
    capsys,
):
    state_file = tmp_path / "state-python.json"
    state_file.write_text("{}")

    config: dict = {}
    state = {
        "issues": {},
        "subjective_assessments": {"naming_quality": {"score": 72}},
    }
    runtime = CommandRuntime(config=config, state=state, state_path=state_file)

    monkeypatch.setattr(exclude_mod.config_mod, "save_config", lambda cfg: None)
    save_state_calls: list[tuple[dict, object]] = []
    monkeypatch.setattr(
        exclude_mod.state_mod,
        "save_state",
        lambda st, path: save_state_calls.append((st, path)),
    )

    exclude_mod.cmd_exclude(_args(".claude", runtime))

    assert config["exclude"] == [".claude"]
    assert config["needs_rescan"] is True
    assert save_state_calls == []
    assert state["subjective_assessments"]["naming_quality"]["score"] == 72

    out = capsys.readouterr().out
    assert "Added exclude pattern: .claude" in out
    assert "Config changed — scores may be stale. Run: desloppify scan" in out


def test_cmd_exclude_prunes_matching_issues_and_plan(
    monkeypatch,
    tmp_path,
    capsys,
):
    state_file = tmp_path / "state-python.json"
    state_file.write_text("{}")

    removed_id = "smells::.claude/worktrees/repo/a.py::debug_log"
    kept_id = "smells::src/main.py::debug_log"
    state = {
        "issues": {
            removed_id: {"file": ".claude/worktrees/repo/a.py"},
            kept_id: {"file": "src/main.py"},
        },
        "subjective_assessments": {"naming_quality": {"score": 81}},
    }
    config: dict = {}
    runtime = CommandRuntime(config=config, state=state, state_path=state_file)

    monkeypatch.setattr(exclude_mod.config_mod, "save_config", lambda cfg: None)

    saved_state: dict[str, object] = {}
    monkeypatch.setattr(
        exclude_mod.state_mod,
        "save_state",
        lambda st, path: saved_state.update({"state": st, "path": path}),
    )

    plan = {
        "queue_order": [removed_id, kept_id],
        "clusters": {"cleanup": {"name": "cleanup", "issue_ids": [removed_id]}},
        "promoted_ids": [removed_id],
    }
    monkeypatch.setattr(exclude_mod, "load_plan", lambda path=None: plan)
    saved_plan: dict[str, object] = {}
    monkeypatch.setattr(
        exclude_mod,
        "save_plan",
        lambda payload, path=None: saved_plan.update({"plan": payload, "path": path}),
    )

    exclude_mod.cmd_exclude(_args(".claude", runtime))

    assert removed_id not in state["work_items"]
    assert kept_id in state["work_items"]
    assert state["subjective_assessments"]["naming_quality"]["score"] == 81
    assert saved_state["path"] == state_file

    assert removed_id not in plan["queue_order"]
    assert removed_id not in plan["clusters"]["cleanup"]["issue_ids"]
    assert saved_plan["path"] == exclude_mod.plan_path_for_state(state_file)

    out = capsys.readouterr().out
    assert "Removed 1 matching issues from state." in out
    assert "Plan updated: 1 item(s) removed from queue." in out
