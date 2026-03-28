"""Direct tests for plan policy command handlers."""

from __future__ import annotations

import argparse

import desloppify.app.commands.plan.policy_cmd as policy_cmd_mod
from desloppify.engine._plan.policy.project import PolicyLoadResult


def _args(**overrides) -> argparse.Namespace:
    base = {
        "policy_action": None,
        "rule_text": "",
        "rule_index": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_cmd_policy_dispatch_routes_add_and_remove(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(policy_cmd_mod, "_cmd_policy_add", lambda _a: calls.append("add"))
    monkeypatch.setattr(policy_cmd_mod, "_cmd_policy_remove", lambda _a: calls.append("remove"))
    monkeypatch.setattr(policy_cmd_mod, "_cmd_policy_list", lambda _a: calls.append("list"))

    policy_cmd_mod.cmd_policy_dispatch(_args(policy_action="add"))
    policy_cmd_mod.cmd_policy_dispatch(_args(policy_action="remove"))
    policy_cmd_mod.cmd_policy_dispatch(_args(policy_action="list"))

    assert calls == ["add", "remove", "list"]


def test_policy_add_requires_non_blank_text(capsys) -> None:
    policy_cmd_mod._cmd_policy_add(_args(rule_text="  "))
    out = capsys.readouterr().out
    assert "Rule text is required" in out


def test_policy_add_saves_and_reports_new_rule(monkeypatch, capsys) -> None:
    saved: list[dict] = []
    monkeypatch.setattr(
        policy_cmd_mod,
        "load_policy_result",
        lambda: PolicyLoadResult(ok=True, policy={"rules": []}),
    )
    monkeypatch.setattr(policy_cmd_mod, "add_rule", lambda policy, text: policy["rules"].append({"text": text}) or 1)
    monkeypatch.setattr(policy_cmd_mod, "save_policy", lambda policy: saved.append(policy))

    policy_cmd_mod._cmd_policy_add(_args(rule_text="Prefer explicit error messages"))
    out = capsys.readouterr().out

    assert "Added rule #1" in out
    assert saved and saved[0]["rules"][0]["text"] == "Prefer explicit error messages"


def test_policy_list_handles_empty_and_populated_policy(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        policy_cmd_mod,
        "load_policy_result",
        lambda: PolicyLoadResult(ok=True, policy={"rules": []}),
    )
    policy_cmd_mod._cmd_policy_list(_args())
    empty_out = capsys.readouterr().out
    assert "No project policy rules defined" in empty_out

    monkeypatch.setattr(
        policy_cmd_mod,
        "load_policy_result",
        lambda: PolicyLoadResult(
            ok=True,
            policy={"rules": [{"text": "Rule A"}, {"text": "Rule B"}]},
        ),
    )
    policy_cmd_mod._cmd_policy_list(_args())
    populated_out = capsys.readouterr().out
    assert "1. Rule A" in populated_out
    assert "2. Rule B" in populated_out
    assert "2 rule(s)" in populated_out


def test_policy_remove_validates_index_and_saves_when_found(monkeypatch, capsys) -> None:
    saved: list[dict] = []
    monkeypatch.setattr(
        policy_cmd_mod,
        "load_policy_result",
        lambda: PolicyLoadResult(ok=True, policy={"rules": [{"text": "Rule A"}]}),
    )
    monkeypatch.setattr(policy_cmd_mod, "save_policy", lambda policy: saved.append(policy))

    policy_cmd_mod._cmd_policy_remove(_args(rule_index=None))
    out_missing_index = capsys.readouterr().out
    assert "--index is required" in out_missing_index

    monkeypatch.setattr(policy_cmd_mod, "remove_rule", lambda _policy, _idx: None)
    policy_cmd_mod._cmd_policy_remove(_args(rule_index=9))
    out_missing_rule = capsys.readouterr().out
    assert "No rule at index 9" in out_missing_rule

    monkeypatch.setattr(policy_cmd_mod, "remove_rule", lambda _policy, idx: f"rule-{idx}")
    policy_cmd_mod._cmd_policy_remove(_args(rule_index=1))
    out_removed = capsys.readouterr().out
    assert "Removed rule #1: rule-1" in out_removed
    assert saved


def test_policy_commands_warn_when_policy_file_is_malformed(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        policy_cmd_mod,
        "load_policy_result",
        lambda: PolicyLoadResult(
            ok=False,
            policy={"rules": []},
            message="bad json",
            error_kind="policy_parse_error",
        ),
    )

    policy_cmd_mod._cmd_policy_list(_args())

    out = capsys.readouterr().out
    assert "ignoring malformed project policy" in out
