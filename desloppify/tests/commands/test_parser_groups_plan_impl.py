"""Direct tests for plan parser group builder."""

from __future__ import annotations

import argparse

import desloppify.app.cli_support.parser_groups_plan_impl as plan_group_mod


def test_add_plan_parser_registers_plan_command_and_subcommands() -> None:
    parser = argparse.ArgumentParser(prog="desloppify")
    sub = parser.add_subparsers(dest="command")

    plan_group_mod.add_plan_parser(sub)

    args = parser.parse_args(["plan", "--state", "state.json", "show"])
    assert args.command == "plan"
    assert args.state == "state.json"
    assert args.plan_action == "show"


def test_add_plan_parser_invokes_section_builders_once(monkeypatch) -> None:
    parser = argparse.ArgumentParser(prog="desloppify")
    sub = parser.add_subparsers(dest="command")
    calls: list[str] = []

    monkeypatch.setattr(plan_group_mod, "_add_queue_subparser", lambda p: calls.append("queue"))
    monkeypatch.setattr(plan_group_mod, "_add_reorder_subparser", lambda p: calls.append("reorder"))
    monkeypatch.setattr(plan_group_mod, "_add_annotation_subparsers", lambda p: calls.append("annotation"))
    monkeypatch.setattr(plan_group_mod, "_add_skip_subparsers", lambda p: calls.append("skip"))
    monkeypatch.setattr(plan_group_mod, "_add_resolve_subparser", lambda p: calls.append("resolve"))
    monkeypatch.setattr(plan_group_mod, "_add_cluster_subparser", lambda p: calls.append("cluster"))
    monkeypatch.setattr(plan_group_mod, "_add_triage_subparser", lambda p: calls.append("triage"))
    monkeypatch.setattr(plan_group_mod, "_add_scan_gate_subparser", lambda p: calls.append("scan_gate"))
    monkeypatch.setattr(plan_group_mod, "_add_commit_log_subparser", lambda p: calls.append("commit_log"))

    plan_group_mod.add_plan_parser(sub)
    assert calls == [
        "queue",
        "reorder",
        "annotation",
        "skip",
        "resolve",
        "cluster",
        "triage",
        "scan_gate",
        "commit_log",
    ]
    assert len(calls) == 9
    assert calls[0] == "queue"
    assert calls[1] == "reorder"
    assert calls[-1] == "commit_log"
    assert "annotation" in calls
    assert "skip" in calls
    assert "cluster" in calls
    assert "triage" in calls
    assert "scan_gate" in calls
