"""Resolve command handlers."""

from __future__ import annotations

import argparse
import logging
import sys

from desloppify import state as state_mod
from desloppify.app.commands.helpers.lang import resolve_lang
from desloppify.app.commands.helpers.queue_progress import show_score_with_plan_context
from desloppify.app.commands.helpers.state import state_path
from desloppify.app.commands.helpers.guardrails import require_triage_current_or_exit
from desloppify.core import config as config_mod  # noqa: F401 (compat export)
from desloppify.core.exception_sets import PLAN_LOAD_EXCEPTIONS
from desloppify.core.output_api import colorize

_logger = logging.getLogger(__name__)
from desloppify.engine.plan import (
    add_uncommitted_issues,
    append_log_entry,
    has_living_plan,
    load_plan,
    purge_ids,
    purge_uncommitted_ids,
    save_plan,
)
from desloppify.intelligence import narrative as narrative_mod
from desloppify.state import coerce_assessment_score

from .apply import _resolve_all_patterns, _write_resolve_query_entry
from .suppress_cmd import cmd_suppress_pattern
from .persist import _save_state_or_exit
from .queue_guard import _check_queue_order_guard
from .render import (
    _print_next_command,
    _print_resolve_summary,
    _print_subjective_reset_hint,
    _print_wontfix_batch_warning,
    render_commit_guidance,
)
from .selection import (
    ResolveQueryContext,
    _enforce_batch_wontfix_confirmation,
    _previous_score_snapshot,
    _validate_resolve_inputs,
    show_note_length_requirement,
    validate_note_length,
)


def cmd_resolve(args: argparse.Namespace) -> None:
    """Resolve issue(s) matching one or more patterns."""
    attestation = getattr(args, "attest", None)
    _validate_resolve_inputs(args, attestation)

    if args.status == "fixed":
        note = getattr(args, "note", None)
        if not validate_note_length(note):
            show_note_length_requirement(note)
            return

    state_file = state_path(args)
    state = state_mod.load_state(state_file)

    if _check_queue_order_guard(state, args.patterns, args.status):
        return

    if args.status == "fixed":
        require_triage_current_or_exit(
            state=state,
            bypass=bool(getattr(args, "force_resolve", False)),
            attest=getattr(args, "attest", "") or "",
        )

    _enforce_batch_wontfix_confirmation(
        state,
        args,
        attestation=attestation,
        resolve_all_patterns_fn=_resolve_all_patterns,
    )
    prev = _previous_score_snapshot(state)
    prev_subjective_scores = {
        str(dim): (coerce_assessment_score(payload) or 0.0)
        for dim, payload in (state.get("subjective_assessments") or {}).items()
        if isinstance(dim, str)
    }

    all_resolved = _resolve_all_patterns(state, args, attestation=attestation)
    if not all_resolved:
        status_label = "resolved" if args.status == "open" else "open"
        print(colorize(f"No {status_label} issues matching: {' '.join(args.patterns)}", "yellow"))
        return

    _save_state_or_exit(state, state_file)

    plan = None
    try:
        if has_living_plan():
            plan = load_plan()
            purged = purge_ids(plan, all_resolved)
            append_log_entry(
                plan,
                "resolve",
                issue_ids=all_resolved,
                actor="user",
                note=getattr(args, "note", None),
                detail={"status": args.status, "attestation": attestation},
            )
            # Commit tracking: add to uncommitted on fix, remove on reopen
            if args.status == "fixed":
                add_uncommitted_issues(plan, all_resolved)
            elif args.status == "open":
                purge_uncommitted_ids(plan, all_resolved)
            if purged:
                save_plan(plan)
                print(colorize(f"  Plan updated: {purged} item(s) removed from queue.", "dim"))
            else:
                save_plan(plan)
    except PLAN_LOAD_EXCEPTIONS as exc:
        _logger.debug("plan update failed after resolve", exc_info=True)
        print(colorize("  Warning: could not update living plan.", "yellow"), file=sys.stderr)

    _print_resolve_summary(status=args.status, all_resolved=all_resolved)
    _print_wontfix_batch_warning(
        state,
        status=args.status,
        resolved_count=len(all_resolved),
    )
    show_score_with_plan_context(state, prev)
    render_commit_guidance(state, plan, all_resolved, args.status)
    _print_subjective_reset_hint(
        args=args,
        state=state,
        all_resolved=all_resolved,
        prev_subjective_scores=prev_subjective_scores,
    )

    lang = resolve_lang(args)
    lang_name = lang.name if lang else None
    narrative = narrative_mod.compute_narrative(
        state,
        context=narrative_mod.NarrativeContext(lang=lang_name, command="resolve"),
    )
    if narrative.get("milestone"):
        print(colorize(f"  → {narrative['milestone']}", "green"))

    next_command = _print_next_command(state)
    _write_resolve_query_entry(
        ResolveQueryContext(
            patterns=args.patterns,
            status=args.status,
            resolved=all_resolved,
            next_command=next_command,
            prev_overall=prev.overall,
            prev_objective=prev.objective,
            prev_strict=prev.strict,
            prev_verified=prev.verified,
            attestation=attestation,
            narrative=narrative,
            state=state,
        )
    )


__all__ = ["_check_queue_order_guard", "cmd_suppress_pattern", "cmd_resolve"]
