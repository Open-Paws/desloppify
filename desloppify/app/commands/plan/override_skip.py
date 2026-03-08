"""Skip and unskip command handlers for plan overrides."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from desloppify import state as state_mod
from desloppify.app.commands.helpers.attestation import (
    show_attestation_requirement,
    validate_attestation,
)
from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.app.commands.helpers.state import require_completed_scan
from desloppify.app.commands.plan._resolve import resolve_ids_from_patterns
from desloppify.app.commands.plan.override_io import (
    _plan_file_for_state,
    save_plan_state_transactional,
)
from desloppify.base.exception_sets import CommandError
from desloppify.base.output.terminal import colorize
from desloppify.base.output.user_message import print_user_message
from desloppify.engine._work_queue.core import ATTEST_EXAMPLE
from desloppify.engine.plan import (
    SKIP_KIND_LABELS,
    append_log_entry,
    load_plan,
    save_plan,
    skip_items,
    skip_kind_from_flags,
    skip_kind_requires_attestation,
    skip_kind_requires_note,
    skip_kind_state_status,
    unskip_items,
)

logger = logging.getLogger(__name__)

_BULK_SKIP_THRESHOLD = 5


def _validate_skip_requirements(
    *,
    kind: str,
    attestation: str | None,
    note: str | None,
) -> bool:
    if not skip_kind_requires_attestation(kind):
        return True
    if not validate_attestation(attestation):
        show_attestation_requirement(
            "Permanent skip" if kind == "permanent" else "False positive",
            attestation,
            ATTEST_EXAMPLE,
        )
        return False
    if skip_kind_requires_note(kind) and not note:
        print(
            colorize("  --permanent requires --note to explain the decision.", "yellow"),
            file=sys.stderr,
        )
        return False
    return True


def _apply_state_skip_resolution(
    *,
    kind: str,
    state_file: Path | None,
    issue_ids: list[str],
    note: str | None,
    attestation: str | None,
) -> dict | None:
    status = skip_kind_state_status(kind)
    if status is None:
        return None
    state_data = state_mod.load_state(state_file)
    for fid in issue_ids:
        state_mod.resolve_issues(
            state_data,
            fid,
            status,
            note or "",
            attestation=attestation,
        )
    return state_data


def cmd_plan_skip(args: argparse.Namespace) -> None:
    """Skip issues — unified command for temporary/permanent/false-positive."""
    runtime = command_runtime(args)
    state = runtime.state
    if not require_completed_scan(state):
        return

    patterns: list[str] = getattr(args, "patterns", [])
    reason: str | None = getattr(args, "reason", None)
    review_after: int | None = getattr(args, "review_after", None)
    permanent: bool = getattr(args, "permanent", False)
    false_positive: bool = getattr(args, "false_positive", False)
    note: str | None = getattr(args, "note", None)
    attestation: str | None = getattr(args, "attest", None)

    kind = skip_kind_from_flags(permanent=permanent, false_positive=false_positive)
    if not _validate_skip_requirements(kind=kind, attestation=attestation, note=note):
        return

    state_file = runtime.state_path
    plan_file = _plan_file_for_state(state_file)
    plan = load_plan(plan_file)
    issue_ids = resolve_ids_from_patterns(state, patterns, plan=plan)
    if not issue_ids:
        print(colorize("  No matching issues found.", "yellow"))
        return

    if len(issue_ids) > _BULK_SKIP_THRESHOLD:
        print(
            colorize(
                f"  Bulk skip: {len(issue_ids)} items will be removed from the active queue.",
                "yellow",
            ),
            file=sys.stderr,
        )
        if not getattr(args, "confirm", False):
            raise CommandError(
                f"Skipping {len(issue_ids)} items requires --confirm. "
                "Review the items first, or skip individually."
            )

    state_data = _apply_state_skip_resolution(
        kind=kind,
        state_file=state_file,
        issue_ids=issue_ids,
        note=note,
        attestation=attestation,
    )

    scan_count = state.get("scan_count", 0)
    count = skip_items(
        plan,
        issue_ids,
        kind=kind,
        reason=reason,
        note=note,
        attestation=attestation,
        review_after=review_after,
        scan_count=scan_count,
    )

    append_log_entry(
        plan,
        "skip",
        issue_ids=issue_ids,
        actor="user",
        note=note,
        detail={"kind": kind, "reason": reason},
    )
    if state_data is not None:
        save_plan_state_transactional(
            plan=plan,
            plan_path=plan_file,
            state_data=state_data,
            state_path_value=state_file,
        )
    else:
        save_plan(plan, plan_file)

    print(colorize(f"  {SKIP_KIND_LABELS[kind]} {count} item(s).", "green"))
    if review_after:
        print(colorize(f"  Will re-surface after {review_after} scan(s).", "dim"))
    print_user_message(
        "Hey — if skipping was the right call, just continue with"
        " what you were doing. If you think a broader re-triage is"
        " needed, use `desloppify plan triage`. Run `desloppify"
        " plan --help` to see all available plan tools. Otherwise"
        " no need to reply, just keep going."
    )


def cmd_plan_unskip(args: argparse.Namespace) -> None:
    """Unskip issues — bring back to queue."""
    runtime = command_runtime(args)
    state = runtime.state
    if not require_completed_scan(state):
        return

    patterns: list[str] = getattr(args, "patterns", [])

    state_file = runtime.state_path
    plan_file = _plan_file_for_state(state_file)
    plan = load_plan(plan_file)
    issue_ids = resolve_ids_from_patterns(state, patterns, plan=plan, status_filter="all")
    if not issue_ids:
        print(colorize("  No matching issues found.", "yellow"))
        return

    include_protected = bool(getattr(args, "force", False))
    count, need_reopen, protected_kept = unskip_items(
        plan,
        issue_ids,
        include_protected=include_protected,
    )
    unskipped_ids = [fid for fid in issue_ids if fid not in protected_kept]
    append_log_entry(
        plan,
        "unskip",
        issue_ids=unskipped_ids,
        actor="user",
        detail={"need_reopen": need_reopen},
    )

    reopened: list[str] = []
    if need_reopen:
        state_data = state_mod.load_state(state_file)
        for fid in need_reopen:
            reopened.extend(state_mod.resolve_issues(state_data, fid, "open"))
        save_plan_state_transactional(
            plan=plan,
            plan_path=plan_file,
            state_data=state_data,
            state_path_value=state_file,
        )
        print(colorize(f"  Reopened {len(reopened)} issue(s) in state.", "dim"))
    else:
        save_plan(plan, plan_file)

    print(colorize(f"  Unskipped {count} item(s) — back in queue.", "green"))
    if protected_kept:
        print(
            colorize(
                f"  Kept {len(protected_kept)} protected skip(s) "
                f"(permanent/false_positive with notes). Use --force to override.",
                "yellow",
            )
        )


__all__ = [
    "_apply_state_skip_resolution",
    "_validate_skip_requirements",
    "cmd_plan_skip",
    "cmd_plan_unskip",
]
