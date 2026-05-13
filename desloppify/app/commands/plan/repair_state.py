"""Repair command for rebuilding state from surviving plan metadata."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from desloppify.app.commands.helpers.command_runtime import command_runtime
from desloppify.base.output.terminal import colorize
from desloppify.engine.plan_state import load_plan, plan_path_for_state
from desloppify.engine._state.recovery import (
    has_saved_plan_without_scan,
    reconcile_saved_plan_skips,
    reconstruct_state_from_saved_plan,
)
from desloppify.state_io import (
    StateModel,
    empty_state,
    get_state_file,
    save_state,
    scan_reconstructed_issue_count,
    scan_source,
)


def _resolved_state_file(runtime) -> Path:
    state_path = runtime.state_path
    if isinstance(state_path, Path):
        return state_path
    return get_state_file()


def cmd_plan_repair_state(args: argparse.Namespace) -> None:
    """Rebuild persisted state from live plan metadata when scan data is gone."""
    runtime = command_runtime(args)
    state_file = _resolved_state_file(runtime)
    plan_path = plan_path_for_state(state_file)
    plan = load_plan(plan_path)

    state = runtime.state
    rebuilt_from_plan = False
    if scan_source(state) != "scan" and has_saved_plan_without_scan(empty_state(), plan):
        state = reconstruct_state_from_saved_plan(empty_state(), plan)
        rebuilt_from_plan = True

    repaired, restored_skips = reconcile_saved_plan_skips(state, plan)
    if not rebuilt_from_plan and not restored_skips:
        print(colorize("  No saved plan metadata available to rebuild state.", "yellow"))
        return

    save_state(cast(StateModel, repaired), state_file)

    reconstructed_count = scan_reconstructed_issue_count(repaired)
    if reconstructed_count:
        print(
            colorize(
                f"  Rebuilt {state_file.name} from {plan_path.name} "
                f"({reconstructed_count} open review item(s)).",
                "green",
            )
        )
    if restored_skips:
        print(
            colorize(
                f"  Restored {restored_skips} plan skip disposition(s) into state.",
                "green",
            )
        )
    if scan_source(repaired) != "scan":
        print(
            colorize(
                "  Scan-derived scores and metrics remain unavailable until you run `desloppify scan`.",
                "dim",
            )
        )


__all__ = ["cmd_plan_repair_state"]
