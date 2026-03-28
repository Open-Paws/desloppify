"""Direct tests for resolve message helpers."""

from __future__ import annotations

import argparse

import desloppify.app.commands.resolve.messages as messages_mod
from desloppify.app.commands.resolve.living_plan import ClusterContext


def _args(*, status: str = "fixed", patterns: list[str] | None = None) -> argparse.Namespace:
    return argparse.Namespace(status=status, patterns=patterns or ["smells::*"])


def test_print_no_match_warning_uses_open_vs_resolved_label(capsys) -> None:
    messages_mod.print_no_match_warning(_args(status="open", patterns=["a", "b"]))
    out = capsys.readouterr().out
    assert "No resolved issues matching: a b" in out

    messages_mod.print_no_match_warning(_args(status="fixed", patterns=["x"]))
    out_fixed = capsys.readouterr().out
    assert "No open issues matching: x" in out_fixed


def test_print_fixed_next_user_message_handles_cluster_states(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(messages_mod, "print_user_message", lambda msg: messages.append(msg))

    args = _args(status="fixed")
    messages_mod.print_fixed_next_user_message(
        args=args,
        plan={},
        next_command="desloppify next",
        mid_cluster=True,
        cluster_ctx=ClusterContext(
            cluster_name="epic/a",
            cluster_completed=False,
            cluster_remaining=3,
        ),
    )
    assert "3 left in cluster 'epic/a'" in messages[-1]

    messages_mod.print_fixed_next_user_message(
        args=args,
        plan={},
        next_command="desloppify next",
        mid_cluster=False,
        cluster_ctx=ClusterContext(
            cluster_name="epic/a",
            cluster_completed=True,
            cluster_remaining=0,
        ),
    )
    assert "finished cluster 'epic/a'" in messages[-1]

    messages_mod.print_fixed_next_user_message(
        args=args,
        plan={},
        next_command="desloppify next",
        mid_cluster=False,
        cluster_ctx=ClusterContext(
            cluster_name=None,
            cluster_completed=False,
            cluster_remaining=0,
        ),
    )
    assert "on to the next one" in messages[-1]


def test_print_fixed_next_user_message_noop_when_not_fixed_or_not_next(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(messages_mod, "print_user_message", lambda msg: calls.append(msg))

    messages_mod.print_fixed_next_user_message(
        args=_args(status="open"),
        plan={},
        next_command="desloppify next",
        mid_cluster=False,
        cluster_ctx=ClusterContext(None, False, 0),
    )
    messages_mod.print_fixed_next_user_message(
        args=_args(status="fixed"),
        plan={},
        next_command="desloppify plan",
        mid_cluster=False,
        cluster_ctx=ClusterContext(None, False, 0),
    )
    messages_mod.print_fixed_next_user_message(
        args=_args(status="fixed"),
        plan=None,
        next_command="desloppify next",
        mid_cluster=False,
        cluster_ctx=ClusterContext(None, False, 0),
    )

    assert calls == []
