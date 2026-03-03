"""next command: show next highest-priority queue items."""

from __future__ import annotations

import argparse

from desloppify import state as state_mod
import desloppify.app.commands.next_parts.output as next_output_mod
import desloppify.app.commands.next_parts.render as next_render_mod
import desloppify.app.commands.next_parts.render_nudges as next_nudges_mod
from desloppify.app.commands.next_parts.render_support import (
    render_queue_header as _render_queue_header,
    scorecard_subjective as _scorecard_subjective_impl,
    show_empty_queue as _show_empty_queue,
)
from desloppify.app.commands.helpers.lang import resolve_lang
from desloppify.app.commands.helpers.query import write_query
from desloppify.app.commands.helpers.queue_progress import (
    QueueBreakdown,
    get_plan_start_strict,
    plan_aware_queue_breakdown,
)
from desloppify.app.commands.helpers.guardrails import print_triage_guardrail_info
from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.app.commands.helpers.score import target_strict_score_from_config
from desloppify.app.commands.helpers.state import require_completed_scan
from desloppify.engine.planning.scorecard_projection import (
    scorecard_dimensions_payload,
)
from desloppify.engine.plan import load_plan
from desloppify.engine.work_queue import (
    QueueBuildOptions,
    build_work_queue,
    queue_context,
)
from desloppify.core.exception_sets import PLAN_LOAD_EXCEPTIONS
from desloppify.core.output_api import colorize
from desloppify.core.skill_docs import check_skill_version
from desloppify.core.tooling import check_config_staleness
from desloppify.core.discovery_api import safe_write_text
from desloppify.intelligence.narrative import NarrativeContext, compute_narrative
from desloppify.scoring import merge_potentials


def _scorecard_subjective(
    state: dict,
    dim_scores: dict,
) -> list[dict]:
    """Return scorecard-aligned subjective entries for current dimension scores."""
    return _scorecard_subjective_impl(state, dim_scores)


def _low_subjective_dimensions(
    state: dict,
    dim_scores: dict,
    *,
    threshold: float = 95.0,
) -> list[tuple[str, float, int]]:
    """Return assessed scorecard-subjective entries below the threshold."""
    low: list[tuple[str, float, int]] = []
    for entry in _scorecard_subjective(state, dim_scores):
        if entry.get("placeholder"):
            continue
        strict_val = float(entry.get("strict", entry.get("score", 100.0)))
        if strict_val < threshold:
            low.append(
                (
                    str(entry.get("name", "Subjective")),
                    strict_val,
                    int(entry.get("failing", 0)),
                )
            )
    low.sort(key=lambda item: item[1])
    return low


def cmd_next(args: argparse.Namespace) -> None:
    """Show next highest-priority queue items."""
    runtime = command_runtime(args)
    state = runtime.state
    config = runtime.config
    if not require_completed_scan(state):
        return

    skill_warning = check_skill_version()
    if skill_warning:
        print(colorize(f"  {skill_warning}", "yellow"))
    config_warning = check_config_staleness(config)
    if config_warning:
        print(colorize(f"  {config_warning}", "yellow"))

    print_triage_guardrail_info(state=state)
    _get_items(args, state, config)


def _resolve_cluster_focus(
    plan_data: dict | None,
    *,
    cluster_arg: str | None,
    scope: str | None,
) -> str | None:
    effective_cluster = cluster_arg
    if plan_data and not cluster_arg and not scope:
        active_cluster = plan_data.get("active_cluster")
        if active_cluster:
            effective_cluster = active_cluster
    return effective_cluster


def _build_next_payload(
    *,
    queue: dict,
    items: list[dict],
    state: dict,
    narrative: dict,
    plan_data: dict | None,
) -> dict:
    payload = next_output_mod.build_query_payload(
        queue, items, command="next", narrative=narrative, plan=plan_data
    )
    payload["overall_score"] = state_mod.get_overall_score(state)
    payload["objective_score"] = state_mod.get_objective_score(state)
    payload["strict_score"] = state_mod.get_strict_score(state)
    payload["scorecard_dimensions"] = scorecard_dimensions_payload(
        state,
        dim_scores=state.get("dimension_scores", {}),
    )
    payload["subjective_measures"] = [
        row for row in payload["scorecard_dimensions"] if row.get("subjective")
    ]
    return payload


def _emit_requested_output(
    args,
    payload: dict,
    items: list[dict],
) -> bool:
    output_file = getattr(args, "output", None)
    if output_file:
        if next_output_mod.write_output_file(
            output_file,
            payload,
            len(items),
            safe_write_text_fn=safe_write_text,
            colorize_fn=colorize,
        ):
            return True
        raise SystemExit(1)

    output_format = getattr(args, "format", "terminal")
    if next_output_mod.emit_non_terminal_output(output_format, payload, items):
        return True
    return False


def _plan_queue_context(
    *,
    state: dict,
    plan_data: dict | None,
    context=None,
) -> tuple[float | None, QueueBreakdown | None]:
    effective_plan = context.plan if context is not None else plan_data
    plan_start_strict = get_plan_start_strict(effective_plan)
    try:
        breakdown = plan_aware_queue_breakdown(state, plan_data, context=context)
    except PLAN_LOAD_EXCEPTIONS:
        breakdown = None
    return plan_start_strict, breakdown


def _merge_potentials_safe(raw_potentials: dict | None) -> dict | None:
    try:
        return merge_potentials(raw_potentials) or None
    except (ImportError, TypeError, ValueError):
        return raw_potentials or None


def _get_items(args, state: dict, config: dict) -> None:
    count = getattr(args, "count", 1) or 1
    scope = getattr(args, "scope", None)
    status = getattr(args, "status", "open")
    group = getattr(args, "group", "item")
    explain = bool(getattr(args, "explain", False))
    cluster_arg = getattr(args, "cluster", None)
    include_skipped = bool(getattr(args, "include_skipped", False))

    target_strict = target_strict_score_from_config(config, fallback=95.0)

    # Load the living plan
    plan = load_plan()
    plan_data: dict | None = None
    if (
        plan.get("queue_order")
        or plan.get("overrides")
        or plan.get("clusters")
    ):
        plan_data = plan

    # Build unified context once — all downstream consumers agree on
    # plan, target_strict, and subjective visibility policy.
    ctx = queue_context(
        state, config=config, plan=plan_data, target_strict=target_strict,
    )

    # Auto-scope to focus cluster if set and no explicit scope/cluster
    effective_cluster = _resolve_cluster_focus(
        plan_data,
        cluster_arg=cluster_arg,
        scope=scope,
    )

    queue = build_work_queue(
        state,
        options=QueueBuildOptions(
            count=count,
            scope=scope,
            status=status,
            include_subjective=True,
            subjective_threshold=target_strict,
            explain=explain,
            include_skipped=include_skipped,
            cluster=effective_cluster,
            context=ctx,
        ),
    )
    items = queue.get("items", [])

    lang = resolve_lang(args)
    lang_name = lang.name if lang else None
    narrative = compute_narrative(
        state,
        context=NarrativeContext(lang=lang_name, command="next", plan=plan_data),
    )

    payload = _build_next_payload(
        queue=queue,
        items=items,
        state=state,
        narrative=narrative,
        plan_data=plan_data,
    )
    write_query(payload)

    if _emit_requested_output(args, payload, items):
        return

    dim_scores = state.get("dimension_scores", {})
    issues_scoped = state_mod.path_scoped_issues(
        state.get("issues", {}),
        state.get("scan_path"),
    )

    # Extract frozen plan-start score and queue breakdown for lifecycle display
    plan_start_strict, breakdown = _plan_queue_context(
        state=state,
        plan_data=plan_data,
        context=ctx,
    )
    queue_total = breakdown.queue_total if breakdown else 0

    _render_queue_header(queue, explain)
    strict_score = state_mod.get_strict_score(state)
    if _show_empty_queue(
        queue,
        strict_score,
        plan_start_strict=plan_start_strict,
        target_strict=target_strict,
    ):
        return

    raw_potentials = state.get("potentials", {})
    potentials = _merge_potentials_safe(raw_potentials)
    next_render_mod.render_terminal_items(
        items, dim_scores, issues_scoped, group=group, explain=explain,
        potentials=potentials, plan=plan_data,
        cluster_filter=effective_cluster,
    )
    next_nudges_mod.render_single_item_resolution_hint(items)
    next_nudges_mod.render_uncommitted_reminder(plan_data)
    next_nudges_mod.render_followup_nudges(
        state,
        dim_scores,
        issues_scoped,
        strict_score=strict_score,
        target_strict_score=target_strict,
        queue_total=queue_total,
        plan_start_strict=plan_start_strict,
        breakdown=breakdown,
    )
    print()


__all__ = ["_low_subjective_dimensions", "cmd_next"]
