"""status command: score dashboard with per-tier progress."""

from __future__ import annotations

import argparse
import json

from desloppify.app.commands.helpers.by_language import (
    aggregate_language_scores,
    detect_present_languages,
    language_score_row,
    language_state_path,
)
from desloppify.app.commands.helpers.command_runtime import command_runtime
from desloppify.app.commands.helpers.state import require_issue_inventory
from desloppify.base.discovery.paths import get_project_root
from desloppify.base.output.terminal import colorize
from desloppify.engine._state.filtering import open_scope_breakdown
from desloppify.engine._scoring.results.core import compute_health_breakdown
from desloppify.engine.planning.scorecard_projection import (
    scorecard_dimensions_payload,
)
from desloppify.state_scoring import score_snapshot, suppression_metrics
from desloppify.state_io import load_state

from .flow import render_terminal_status


def cmd_status(args: argparse.Namespace) -> None:
    """Show score dashboard."""
    if getattr(args, "by_language", False):
        _cmd_status_by_language(args)
        return
    runtime = command_runtime(args)
    state = runtime.state
    config = runtime.config

    stats = state.get("stats", {})
    dim_scores = state.get("dimension_scores", {}) or {}
    scorecard_dims = scorecard_dimensions_payload(state, dim_scores=dim_scores)
    subjective_measures = [row for row in scorecard_dims if row.get("subjective")]
    suppression = suppression_metrics(state)

    if getattr(args, "json", False):
        print(
            json.dumps(
                _status_json_payload(
                    state,
                    stats,
                    dim_scores,
                    scorecard_dims,
                    subjective_measures,
                    suppression,
                ),
                indent=2,
            )
        )
        return

    if not require_issue_inventory(state):
        return

    render_terminal_status(
        args,
        state=state,
        config=config,
        stats=stats,
        dim_scores=dim_scores,
        scorecard_dims=scorecard_dims,
        subjective_measures=subjective_measures,
        suppression=suppression,
    )


def _cmd_status_by_language(args: argparse.Namespace) -> None:
    project_root = get_project_root()
    languages = detect_present_languages(project_root)
    rows = []
    for lang_name in languages:
        path = language_state_path(lang_name)
        if not path.exists():
            continue
        state = load_state(path)
        rows.append(language_score_row(lang_name, state))

    aggregate = aggregate_language_scores(rows)
    payload = {"languages": rows, "aggregate": aggregate}
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
        return

    if not rows:
        print(colorize("No per-language scans yet. Run: desloppify scan --by-language", "yellow"))
        return

    print(colorize("\nDesloppify Status by Language\n", "bold"))
    print(colorize("  Aggregate: equal-weight average over scanned language states", "dim"))
    if aggregate:
        print(
            f"  Overall {aggregate['overall_score']:.1f} | "
            f"Strict {aggregate['strict_score']:.1f} | "
            f"Open {aggregate['open']}"
        )
    print()
    for row in rows:
        print(
            f"  {row['language']}: overall {row['overall_score']:.1f}, "
            f"strict {row['strict_score']:.1f}, open {row['open']}, "
            f"scans {row['scan_count']}"
        )


def _status_json_payload(
    state: dict,
    stats: dict,
    dim_scores: dict,
    scorecard_dims: list[dict],
    subjective_measures: list[dict],
    suppression: dict,
) -> dict:
    scores = score_snapshot(state)
    issues = (state.get("work_items") or state.get("issues", {}))
    open_scope = (
        open_scope_breakdown(issues, state.get("scan_path"))
        if isinstance(issues, dict)
        else None
    )
    return {
        "overall_score": scores.overall,
        "objective_score": scores.objective,
        "strict_score": scores.strict,
        "verified_strict_score": scores.verified,
        "dimension_scores": dim_scores,
        "score_breakdown": compute_health_breakdown(dim_scores) if dim_scores else None,
        "scorecard_dimensions": scorecard_dims,
        "subjective_measures": subjective_measures,
        "potentials": state.get("potentials"),
        "codebase_metrics": state.get("codebase_metrics"),
        "stats": stats,
        "open_scope": open_scope,
        "suppression": suppression,
        "scan_count": state.get("scan_count", 0),
        "last_scan": state.get("last_scan"),
        "scan_metadata": state.get("scan_metadata", {}),
    }

__all__ = ["cmd_status"]
