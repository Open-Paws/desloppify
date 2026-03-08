"""Regression tests for plan override state/plan transaction boundaries."""

from __future__ import annotations

import argparse
import copy

import pytest

from desloppify import state as state_mod
from desloppify.app.commands.helpers.runtime import CommandRuntime
from desloppify.app.commands.plan import override_io
from desloppify.app.commands.plan import override_skip
from desloppify.engine.plan import empty_plan, load_plan, save_plan, skip_items

_ATTEST = "I have actually reviewed this and I am not gaming the score."


def _seed_state() -> tuple[dict, str]:
    state = state_mod.empty_state()
    state["last_scan"] = "2026-03-01T00:00:00+00:00"
    state["scan_count"] = 3
    issue = state_mod.make_issue(
        "review",
        "src/example.py",
        "sample-issue",
        tier=1,
        confidence="high",
        summary="sample",
    )
    issue_id = issue["id"]
    state["issues"][issue_id] = issue
    return state, issue_id


def _seed_plan(issue_id: str) -> dict:
    plan = empty_plan()
    plan["queue_order"] = [issue_id]
    return plan


def test_save_plan_state_transactional_rolls_back_on_plan_write_failure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "state.json"
    plan_file = tmp_path / "plan.json"

    initial_state, issue_id = _seed_state()
    initial_plan = _seed_plan(issue_id)
    state_mod.save_state(initial_state, state_file)
    save_plan(initial_plan, plan_file)
    before_state = state_file.read_text()
    before_plan = plan_file.read_text()

    changed_state = copy.deepcopy(initial_state)
    state_mod.resolve_issues(
        changed_state,
        issue_id,
        "wontfix",
        note="intentional debt",
        attestation=_ATTEST,
    )
    changed_plan = copy.deepcopy(initial_plan)
    skip_items(
        changed_plan,
        [issue_id],
        kind="permanent",
        note="intentional debt",
        attestation=_ATTEST,
    )

    def _boom(*_args, **_kwargs):
        raise OSError("simulated plan write failure")

    monkeypatch.setattr(override_io, "save_plan", _boom)
    with pytest.raises(OSError):
        override_io.save_plan_state_transactional(
            plan=changed_plan,
            plan_path=plan_file,
            state_data=changed_state,
            state_path_value=state_file,
        )

    assert state_file.read_text() == before_state
    assert plan_file.read_text() == before_plan


def test_cmd_plan_skip_permanent_rollback_when_plan_write_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "state.json"
    plan_file = tmp_path / "plan.json"

    initial_state, issue_id = _seed_state()
    initial_plan = _seed_plan(issue_id)
    state_mod.save_state(initial_state, state_file)
    save_plan(initial_plan, plan_file)

    runtime = CommandRuntime(
        config={},
        state=copy.deepcopy(initial_state),
        state_path=state_file,
    )
    args = argparse.Namespace(
        runtime=runtime,
        patterns=[issue_id],
        reason=None,
        review_after=None,
        permanent=True,
        false_positive=False,
        note="intentional debt",
        attest=_ATTEST,
    )

    monkeypatch.setattr(override_skip, "resolve_ids_from_patterns", lambda *_a, **_k: [issue_id])

    def _boom(*_args, **_kwargs):
        raise OSError("simulated plan write failure")

    monkeypatch.setattr(override_io, "save_plan", _boom)

    with pytest.raises(OSError):
        override_skip.cmd_plan_skip(args)

    state_after = state_mod.load_state(state_file)
    plan_after = load_plan(plan_file)
    assert state_after["issues"][issue_id]["status"] == "open"
    assert plan_after.get("queue_order", []) == [issue_id]
    assert plan_after.get("skipped", {}) == {}
