"""Direct tests for review packet builder helpers."""

from __future__ import annotations

from pathlib import Path

import desloppify.app.commands.review.packet.build as packet_build_mod


def test_build_run_batches_next_command_preserves_state_scope(tmp_path: Path) -> None:
    context = packet_build_mod.ReviewPacketContext(
        path=tmp_path,
        state_path=tmp_path / "alt-state.json",
        dimensions=["logic_clarity"],
        retrospective=False,
        retrospective_max_issues=30,
        retrospective_max_batch_items=20,
    )

    command = packet_build_mod.build_run_batches_next_command(context)

    assert "--state" in command
    assert str(tmp_path / "alt-state.json") in command
    assert "--no-retrospective" in command


def test_build_external_submit_next_command_preserves_state_scope(tmp_path: Path) -> None:
    context = packet_build_mod.ReviewPacketContext(
        path=tmp_path,
        state_path=tmp_path / "alt-state.json",
        dimensions=None,
        retrospective=False,
        retrospective_max_issues=30,
        retrospective_max_batch_items=20,
    )

    command = packet_build_mod.build_external_submit_next_command(context)

    assert "--state" in command
    assert str(tmp_path / "alt-state.json") in command
    assert "--no-retrospective" in command


def test_prepared_packet_contract_includes_state_scope(tmp_path: Path) -> None:
    context = packet_build_mod.ReviewPacketContext(
        path=tmp_path / "repo",
        state_path=tmp_path / "alt-state.json",
        dimensions=["logic_clarity"],
        retrospective=True,
        retrospective_max_issues=30,
        retrospective_max_batch_items=20,
    )

    contract = packet_build_mod.prepared_packet_contract(context, config={})

    assert contract["state_path"] == str((tmp_path / "alt-state.json").resolve())


def test_attach_plan_deferral_context_uses_plan_for_selected_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    seen: dict[str, Path] = {}
    state_path = tmp_path / "alt-state.json"
    expected_plan_path = tmp_path / "alt-plan.json"

    def fake_plan_path_for_state(path: Path) -> Path:
        seen["state_path"] = path
        return expected_plan_path

    def fake_load_plan(path=None):
        seen["plan_path"] = path
        return {
            "subjective_defer_meta": {
                "defer_count": 2,
                "deferred_review_ids": ["subjective::naming_quality"],
            }
        }

    monkeypatch.setattr(packet_build_mod, "plan_path_for_state", fake_plan_path_for_state)
    monkeypatch.setattr("desloppify.engine.plan_state.load_plan", fake_load_plan)

    packet = {
        "investigation_batches": [
            {"dimensions": ["naming_quality", "logic_clarity"]},
        ]
    }

    packet_build_mod._attach_plan_deferral_context(packet, state_path=state_path)

    assert seen["state_path"] == state_path
    assert seen["plan_path"] == expected_plan_path
    assert packet["investigation_batches"][0]["subjective_defer_meta"] == {
        "naming_quality": {"deferred_cycles": 2}
    }
