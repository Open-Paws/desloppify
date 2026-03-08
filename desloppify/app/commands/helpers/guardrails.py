"""Shared triage guardrail helpers for command entrypoints."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from desloppify.app.commands.helpers.display import short_issue_id
from desloppify.base.exception_sets import PLAN_LOAD_EXCEPTIONS, CommandError
from desloppify.base.output.terminal import colorize
from desloppify.engine.plan import (
    compute_new_issue_ids,
    is_triage_stale,
    load_plan,
    triage_phase_banner,
)

logger = logging.getLogger(__name__)


@dataclass
class TriageGuardrailResult:
    """Structured result from triage staleness detection."""

    is_stale: bool = False
    new_ids: set[str] = field(default_factory=set)
    _plan: dict | None = field(default=None, repr=False)


def triage_guardrail_status(
    *,
    plan: dict | None = None,
    state: dict | None = None,
) -> TriageGuardrailResult:
    """Pure detection: is triage stale? Returns structured result, no side effects."""
    try:
        resolved_plan = plan if isinstance(plan, dict) else load_plan()
    except PLAN_LOAD_EXCEPTIONS as exc:
        logger.debug("Triage guardrail status skipped: plan could not be loaded.", exc_info=exc)
        return TriageGuardrailResult()

    resolved_state = state or {}

    if not is_triage_stale(resolved_plan, resolved_state):
        return TriageGuardrailResult(_plan=resolved_plan)

    new_ids: set[str] = set()
    if resolved_state:
        new_ids = compute_new_issue_ids(resolved_plan, resolved_state)

    return TriageGuardrailResult(is_stale=True, new_ids=new_ids, _plan=resolved_plan)


def triage_guardrail_messages(
    *,
    plan: dict | None = None,
    state: dict | None = None,
) -> list[str]:
    """Return warning strings without printing."""
    result = triage_guardrail_status(plan=plan, state=state)
    if not result.is_stale:
        return []

    messages: list[str] = []
    if result.new_ids:
        messages.append(
            f"{len(result.new_ids)} new review issue(s) not yet triaged."
            " Run `desloppify plan triage` to incorporate."
        )

    if result._plan is not None:
        banner = triage_phase_banner(result._plan)
        if banner:
            messages.append(banner)

    return messages


def print_triage_guardrail_info(
    *,
    plan: dict | None = None,
    state: dict | None = None,
) -> bool:
    """Print yellow info banner if triage is stale. Returns True if banner was shown."""
    messages = triage_guardrail_messages(plan=plan, state=state)
    for msg in messages:
        print(colorize(f"  {msg}", "yellow"))
    return bool(messages)


def require_triage_current_or_exit(
    *,
    state: dict,
    bypass: bool = False,
    attest: str = "",
) -> None:
    """Gate: exit(1) if triage is stale and not bypassed. Name signals the exit."""
    result = triage_guardrail_status(state=state)
    if not result.is_stale:
        return

    if bypass and attest and len(attest.strip()) >= 30:
        print(colorize(
            "  Triage guardrail bypassed with attestation.",
            "yellow",
        ))
        return

    new_ids = result.new_ids
    lines = [
        f"BLOCKED: {len(new_ids) or 'some'} new review issue(s) have not been triaged."
    ]
    if new_ids:
        for fid in sorted(new_ids)[:5]:
            issue = state.get("issues", {}).get(fid, {})
            lines.append(f"    * [{short_issue_id(fid)}] {issue.get('summary', '')}")
        if len(new_ids) > 5:
            lines.append(f"    ... and {len(new_ids) - 5} more")
    lines.append("")
    lines.append("  NEXT STEP: desloppify plan triage")
    lines.append("  (Review new issues, then either --confirm-existing or re-plan.)")
    lines.append("")
    lines.append("  View new items:  desloppify plan queue --sort recent")
    lines.append('  To bypass: --force-resolve --attest "I understand the plan may be stale..."')
    raise CommandError("\n".join(lines))


__all__ = [
    "TriageGuardrailResult",
    "print_triage_guardrail_info",
    "require_triage_current_or_exit",
    "triage_guardrail_messages",
    "triage_guardrail_status",
]
