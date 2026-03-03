"""show command: dig into issues by file, directory, detector, or pattern."""

from __future__ import annotations

import argparse

from desloppify.app.commands.helpers.guardrails import print_triage_guardrail_info
from desloppify.app.commands.helpers.lang import resolve_lang
from desloppify.app.commands.helpers.query import write_query
from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.app.commands.helpers.score import target_strict_score_from_config
from desloppify.app.commands.helpers.state import require_completed_scan
from desloppify.core.exception_sets import PLAN_LOAD_EXCEPTIONS
from desloppify.core.output_api import colorize
from desloppify.core.skill_docs import check_skill_version
from desloppify.core.tooling import check_config_staleness
from desloppify.engine.plan import load_plan
from desloppify.intelligence.narrative import NarrativeContext, compute_narrative

from .concerns_view import _show_concerns
from .dimension_views import (
    _load_dimension_issues,
    _render_clean_mechanical_dimension,
    _render_no_matches,
    _render_subjective_dimension,
    _render_subjective_views_guide,
)
from .payload import ShowPayloadMeta, build_show_payload
from .render import (
    render_issues,
    show_agent_plan,
    show_subjective_followup,
    write_show_output_file,
)
from .scope import load_matches, resolve_entity, resolve_noise, resolve_show_scope


def cmd_show(args: argparse.Namespace) -> None:
    """Show all issues for a file, directory, detector, or pattern."""
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

    pattern_raw = getattr(args, "pattern", "")
    show_code = getattr(args, "code", False)
    chronic = getattr(args, "chronic", False)
    ok, pattern, status_filter, scope = resolve_show_scope(args)
    if not ok or pattern is None:
        return

    lang = resolve_lang(args)
    lang_name = lang.name if lang else None
    narrative = compute_narrative(
        state,
        context=NarrativeContext(lang=lang_name, command="show"),
    )

    entity = resolve_entity(pattern, state)

    if entity.kind == "special_view" and entity.pattern.strip().lower() == "concerns":
        _show_concerns(state, lang_name)
        return

    if entity.kind == "dimension" and entity.is_subjective:
        _render_subjective_dimension(state, config, entity, pattern_raw)
        return

    if entity.kind == "dimension" and not entity.is_subjective:
        matches = _load_dimension_issues(state, entity, status_filter)
        if not matches:
            _render_clean_mechanical_dimension(state, entity)
            return
        pattern = entity.display_name
    else:
        matches = load_matches(
            state, scope=scope, status_filter=status_filter, chronic=chronic
        )

    if not matches:
        _render_no_matches(entity, pattern, status_filter, narrative, state, config)
        return

    no_budget = getattr(args, "no_budget", False)
    (
        surfaced_matches,
        hidden_by_detector,
        noise_budget,
        global_noise_budget,
        budget_warning,
    ) = resolve_noise(
        config,
        matches,
        no_budget=no_budget,
    )
    hidden_total = sum(hidden_by_detector.values())

    payload = build_show_payload(
        surfaced_matches,
        pattern,
        status_filter,
        ShowPayloadMeta(
            total_matches=len(matches),
            hidden_by_detector=hidden_by_detector,
            noise_budget=noise_budget,
            global_noise_budget=global_noise_budget,
        ),
    )
    write_query({"command": "show", **payload, "narrative": narrative})

    output_file = getattr(args, "output", None)
    if output_file:
        if write_show_output_file(output_file, payload, len(surfaced_matches)):
            return
        raise SystemExit(1)

    top = getattr(args, "top", 20) or 20
    render_issues(
        surfaced_matches,
        pattern=pattern,
        status_filter=status_filter,
        show_code=show_code,
        top=top,
        hidden_by_detector=hidden_by_detector,
        hidden_total=hidden_total,
        noise_budget=noise_budget,
        global_noise_budget=global_noise_budget,
        budget_warning=budget_warning,
    )
    try:
        plan = load_plan()
        plan_active = plan if (plan.get("queue_order") or plan.get("clusters")) else None
    except PLAN_LOAD_EXCEPTIONS:
        plan_active = None
    show_agent_plan(narrative, surfaced_matches, plan=plan_active)
    show_subjective_followup(
        state,
        target_strict_score_from_config(config, fallback=95.0),
    )

    _render_subjective_views_guide(entity)


__all__ = ["cmd_show"]
