"""Plan override subcommand handlers: describe, note, skip, unskip, done, reopen, focus."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from desloppify import state as state_mod
from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.app.commands.helpers.state import require_completed_scan, state_path
from desloppify.app.commands.plan._resolve import resolve_ids_from_patterns
from desloppify.app.commands.resolve.selection import (
    show_attestation_requirement,
    show_note_length_requirement,
    validate_attestation,
    validate_note_length,
)
from desloppify.core.exception_sets import PLAN_LOAD_EXCEPTIONS
from desloppify.core.output_api import colorize
from desloppify.engine.plan import (
    annotate_issue,
    append_log_entry,
    clear_focus,
    describe_issue,
    PLAN_FILE,
    load_plan,
    plan_path_for_state,
    purge_ids,
    save_plan,
    set_focus,
    skip_items,
    unskip_items,
)
from desloppify.engine.work_queue import ATTEST_EXAMPLE
from desloppify.core.discovery_api import safe_write_text


def _resolve_state_file(path: Path | None) -> Path:
    return path if path is not None else state_mod.STATE_FILE


def _resolve_plan_file(path: Path | None) -> Path:
    return path if path is not None else PLAN_FILE


def _plan_file_for_state(state_file: Path | None) -> Path | None:
    if state_file is None:
        return None
    return plan_path_for_state(state_file)


def _snapshot_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text()


def _restore_file_snapshot(path: Path, snapshot: str | None) -> None:
    if snapshot is None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
        return
    safe_write_text(path, snapshot)


def _save_plan_state_transactional(
    *,
    plan: dict,
    plan_path: Path | None,
    state_data: dict,
    state_path_value: Path | None,
) -> None:
    """Persist plan+state together; rollback both files on partial write failure."""
    effective_plan_path = _resolve_plan_file(plan_path)
    effective_state_path = _resolve_state_file(state_path_value)
    plan_snapshot = _snapshot_file(effective_plan_path)
    state_snapshot = _snapshot_file(effective_state_path)

    try:
        state_mod.save_state(state_data, effective_state_path)
        save_plan(plan, effective_plan_path)
    except Exception:
        _restore_file_snapshot(effective_state_path, state_snapshot)
        _restore_file_snapshot(effective_plan_path, plan_snapshot)
        raise


def cmd_plan_describe(args: argparse.Namespace) -> None:
    """Set augmented description on issues."""
    state = command_runtime(args).state
    if not require_completed_scan(state):
        return

    patterns: list[str] = getattr(args, "patterns", [])
    text: str = getattr(args, "text", "")

    plan = load_plan()
    issue_ids = resolve_ids_from_patterns(state, patterns, plan=plan)
    if not issue_ids:
        print(colorize("  No matching issues found.", "yellow"))
        return

    for fid in issue_ids:
        describe_issue(plan, fid, text or None)
    append_log_entry(
        plan, "describe", issue_ids=issue_ids, actor="user",
        detail={"text": text or None},
    )
    save_plan(plan)
    print(colorize(f"  Set description on {len(issue_ids)} issue(s).", "green"))


def cmd_plan_note(args: argparse.Namespace) -> None:
    """Set note on issues."""
    state = command_runtime(args).state
    if not require_completed_scan(state):
        return

    patterns: list[str] = getattr(args, "patterns", [])
    text: str | None = getattr(args, "text", None)

    plan = load_plan()
    issue_ids = resolve_ids_from_patterns(state, patterns, plan=plan)
    if not issue_ids:
        print(colorize("  No matching issues found.", "yellow"))
        return

    for fid in issue_ids:
        annotate_issue(plan, fid, text)
    append_log_entry(
        plan, "note", issue_ids=issue_ids, actor="user",
        note=text,
    )
    save_plan(plan)
    print(colorize(f"  Set note on {len(issue_ids)} issue(s).", "green"))


# ---------------------------------------------------------------------------
# Skip / unskip
# ---------------------------------------------------------------------------

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

    # Determine skip kind
    if false_positive:
        kind = "false_positive"
    elif permanent:
        kind = "permanent"
    else:
        kind = "temporary"

    # Validate requirements for permanent/false_positive
    if kind in ("permanent", "false_positive"):
        if not validate_attestation(attestation):
            show_attestation_requirement(
                "Permanent skip" if kind == "permanent" else "False positive",
                attestation,
                ATTEST_EXAMPLE,
            )
            return
        if kind == "permanent" and not note:
            print(
                colorize("  --permanent requires --note to explain the decision.", "yellow"),
                file=sys.stderr,
            )
            return

    state_file = runtime.state_path
    plan_file = _plan_file_for_state(state_file)
    plan = load_plan(plan_file)
    issue_ids = resolve_ids_from_patterns(state, patterns, plan=plan)
    if not issue_ids:
        print(colorize("  No matching issues found.", "yellow"))
        return

    # For permanent/false_positive: delegate to state layer for score impact
    state_data: dict | None = None
    if kind in ("permanent", "false_positive"):
        state_data = state_mod.load_state(state_file)
        status = "wontfix" if kind == "permanent" else "false_positive"
        for fid in issue_ids:
            state_mod.resolve_issues(
                state_data, fid, status, note or "", attestation=attestation
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

    # Log the skip action
    append_log_entry(
        plan,
        "skip",
        issue_ids=issue_ids,
        actor="user",
        note=note,
        detail={"kind": kind, "reason": reason},
    )
    if state_data is not None:
        _save_plan_state_transactional(
            plan=plan,
            plan_path=plan_file,
            state_data=state_data,
            state_path_value=state_file,
        )
    else:
        save_plan(plan, plan_file)

    label = {"temporary": "Skipped", "permanent": "Wontfixed", "false_positive": "Marked false positive"}
    print(colorize(f"  {label[kind]} {count} item(s).", "green"))
    if review_after:
        print(colorize(f"  Will re-surface after {review_after} scan(s).", "dim"))


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
    # For unskip we need to match against all statuses (skipped items may be wontfix/fp)
    issue_ids = resolve_ids_from_patterns(state, patterns, plan=plan, status_filter="all")
    if not issue_ids:
        print(colorize("  No matching issues found.", "yellow"))
        return

    count, need_reopen = unskip_items(plan, issue_ids)
    append_log_entry(
        plan, "unskip", issue_ids=issue_ids, actor="user",
        detail={"need_reopen": need_reopen},
    )

    # Reopen permanent/false_positive items in state
    reopened: list[str] = []
    if need_reopen:
        state_data = state_mod.load_state(state_file)
        for fid in need_reopen:
            reopened.extend(state_mod.resolve_issues(state_data, fid, "open"))
        _save_plan_state_transactional(
            plan=plan,
            plan_path=plan_file,
            state_data=state_data,
            state_path_value=state_file,
        )
        print(colorize(f"  Reopened {len(reopened)} issue(s) in state.", "dim"))
    else:
        save_plan(plan, plan_file)

    print(colorize(f"  Unskipped {count} item(s) — back in queue.", "green"))


# ---------------------------------------------------------------------------
# Reopen
# ---------------------------------------------------------------------------

def cmd_plan_reopen(args: argparse.Namespace) -> None:
    """Reopen resolved issues from plan context."""
    patterns: list[str] = getattr(args, "patterns", [])

    raw_state_path = state_path(args)
    state_file = raw_state_path if isinstance(raw_state_path, Path) else Path(raw_state_path) if raw_state_path else None
    state_data = state_mod.load_state(state_file)
    plan_file = _plan_file_for_state(state_file)

    reopened: list[str] = []
    for pattern in patterns:
        reopened.extend(
            state_mod.resolve_issues(state_data, pattern, "open")
        )

    if not reopened:
        print(colorize("  No resolved issues matching: " + " ".join(patterns), "yellow"))
        return

    # Remove from skipped if present, and ensure all reopened IDs are in queue
    plan = load_plan(plan_file)

    # Remove from commit tracking uncommitted list
    from desloppify.engine.plan import purge_uncommitted_ids as _purge_uncommitted
    _purge_uncommitted(plan, reopened)

    skipped = plan.get("skipped", {})
    count = 0
    order = set(plan.get("queue_order", []))
    for fid in reopened:
        if fid in skipped:
            skipped.pop(fid)
            count += 1
        if fid not in order:
            plan["queue_order"].append(fid)
            order.add(fid)
            count += 1
    append_log_entry(
        plan, "reopen", issue_ids=reopened, actor="user",
    )
    _save_plan_state_transactional(
        plan=plan,
        plan_path=plan_file,
        state_data=state_data,
        state_path_value=state_file,
    )

    print(colorize(f"  Reopened {len(reopened)} issue(s).", "green"))
    if count:
        print(colorize(f"  Plan updated: items moved back to queue.", "dim"))


_CLUSTER_INDIVIDUAL_THRESHOLD = 10


def _check_cluster_guard(patterns: list[str], plan: dict, state: dict) -> bool:
    """Return True if blocked by cluster guard, False if OK to proceed."""
    clusters = plan.get("clusters", {})
    issues = state.get("issues", {})
    for pattern in patterns:
        if pattern in clusters:
            cluster = clusters[pattern]
            # Filter to alive issues only — stale IDs should not count
            ids = [
                fid for fid in cluster.get("issue_ids", [])
                if fid in issues and issues[fid].get("status") == "open"
            ]
            if len(ids) == 0:
                print(colorize(
                    f"\n  Cluster '{pattern}' is empty — add items before marking it done.\n",
                    "yellow",
                ))
                print(colorize(
                    f"  Use: desloppify plan cluster add {pattern} <issue-id>",
                    "dim",
                ))
                return True  # blocked
            if len(ids) <= _CLUSTER_INDIVIDUAL_THRESHOLD:
                _print_cluster_guard(pattern, ids, state)
                return True  # blocked
    return False  # OK


def _print_cluster_guard(cluster_name: str, issue_ids: list[str], state: dict) -> None:
    issues = state.get("issues", {})
    print(colorize(
        f"\n  Cluster '{cluster_name}' has {len(issue_ids)} item(s) — mark them done individually first:\n",
        "yellow",
    ))
    for fid in issue_ids:
        f = issues.get(fid, {})
        summary = f.get("summary", "(no summary)")[:80]
        detector = f.get("detector", "?")
        print(f"    {fid}  [{detector}]  {summary}")
    print(colorize(
        f"\n  Use: desloppify resolve <id> --status fixed --note '...' --attest '...'",
        "dim",
    ))
    print(colorize(
        f"  Or mark each resolved: desloppify plan resolve <id> --note '...' --confirm\n",
        "dim",
    ))


def _is_synthetic_id(fid: str) -> bool:
    """Return True if the ID is a synthetic workflow/triage item, not a real issue."""
    return fid.startswith("triage::") or fid.startswith("workflow::") or fid.startswith("subjective::")


def _resolve_synthetic_ids(patterns: list[str]) -> tuple[list[str], list[str]]:
    """Separate synthetic IDs from real issue patterns.

    Returns (synthetic_ids, remaining_patterns).
    """
    synthetic = [p for p in patterns if _is_synthetic_id(p)]
    remaining = [p for p in patterns if not _is_synthetic_id(p)]
    return synthetic, remaining


def _blocked_triage_stages(plan: dict) -> dict[str, list[str]]:
    """Return ``{stage_id: [blocked_by_ids]}`` for triage stages that can't run yet.

    Uses the dependency graph and confirmed-stage metadata directly —
    no state needed, no queue item construction.
    """
    from desloppify.app.commands.plan.triage_playbook import TRIAGE_STAGE_DEPENDENCIES
    from desloppify.engine.plan import TRIAGE_IDS, TRIAGE_STAGE_IDS

    order_set = set(plan.get("queue_order", []))
    present = order_set & TRIAGE_IDS
    if not present:
        return {}

    confirmed = set(plan.get("epic_triage_meta", {}).get("triage_stages", {}).keys())
    stage_names = ("observe", "reflect", "organize", "commit")

    blocked: dict[str, list[str]] = {}
    for sid, name in zip(TRIAGE_STAGE_IDS, stage_names):
        if sid not in present or name in confirmed:
            continue
        deps = TRIAGE_STAGE_DEPENDENCIES.get(name, set())
        unmet = sorted(
            f"triage::{dep}" for dep in deps
            if f"triage::{dep}" in present and dep not in confirmed
        )
        if unmet:
            blocked[sid] = unmet
    return blocked


def cmd_plan_resolve(args: argparse.Namespace) -> None:
    """Mark issues as fixed — delegates to cmd_resolve for rich UX."""
    patterns: list[str] = getattr(args, "patterns", [])
    attestation: str | None = getattr(args, "attest", None)
    note: str | None = getattr(args, "note", None)

    # --confirm: auto-generate attestation from --note
    if getattr(args, "confirm", False):
        if not note:
            print(colorize("  --confirm requires --note to describe what you did.", "red"))
            return
        attestation = f"I have actually {note} and I am not gaming the score."
        args.attest = attestation

    # Handle synthetic IDs (triage::*, workflow::*, subjective::*) directly
    synthetic_ids, real_patterns = _resolve_synthetic_ids(patterns)
    if synthetic_ids:
        plan = load_plan()
        # Validate triage dependency chain
        blocked_map = _blocked_triage_stages(plan)
        for sid in synthetic_ids:
            if sid in blocked_map:
                deps = ", ".join(b.replace("triage::", "") for b in blocked_map[sid])
                print(colorize(f"  Cannot resolve {sid} — blocked by: {deps}", "red"))
                print(colorize("  Complete those stages first, or use --force-resolve to override.", "dim"))
                if not getattr(args, "force_resolve", False):
                    return
        purge_ids(plan, synthetic_ids)
        append_log_entry(
            plan, "done", issue_ids=synthetic_ids, actor="user", note=note,
        )
        save_plan(plan)
        for sid in synthetic_ids:
            print(colorize(f"  Resolved: {sid}", "green"))
        if not real_patterns:
            return
        # Continue with remaining real patterns
        patterns = real_patterns
        args.patterns = patterns

    # Validate note length
    if not validate_note_length(note):
        show_note_length_requirement(note)
        return

    # Pre-validate attestation before delegating (avoids stale hint in resolve)
    if not validate_attestation(attestation):
        show_attestation_requirement("Plan resolve", attestation, ATTEST_EXAMPLE)
        return

    # Cluster completion guard: block bulk-completing small clusters
    try:
        runtime = command_runtime(args)
        state = runtime.state
        plan = load_plan()
        if _check_cluster_guard(patterns, plan, state):
            return
    except PLAN_LOAD_EXCEPTIONS:
        plan = None

    # Log the done action (best-effort)
    try:
        if plan is None:
            plan = load_plan()
        clusters = plan.get("clusters", {})
        cluster_name = None
        for p in patterns:
            if p in clusters:
                cluster_name = p
                break
        append_log_entry(
            plan,
            "done",
            issue_ids=patterns,
            cluster_name=cluster_name,
            actor="user",
            note=note,
        )
        save_plan(plan)
    except PLAN_LOAD_EXCEPTIONS as exc:
        print(colorize(f"  Note: unable to append plan resolve log entry ({exc}).", "dim"))

    # Deferred import: cmd_resolve has a heavy import chain that isn't needed
    # for synthetic-ID handling above.
    from desloppify.app.commands.resolve.cmd import cmd_resolve

    # Build a Namespace that cmd_resolve expects
    resolve_args = argparse.Namespace(
        status="fixed",
        patterns=patterns,
        note=note,
        attest=attestation,
        confirm_batch_wontfix=False,
        force_resolve=bool(getattr(args, "force_resolve", False)),
        state=getattr(args, "state", None),
        lang=getattr(args, "lang", None),
        path=getattr(args, "path", None),
        exclude=getattr(args, "exclude", None),
    )

    cmd_resolve(resolve_args)


def cmd_plan_focus(args: argparse.Namespace) -> None:
    """Set or clear the active cluster focus."""
    clear_flag = getattr(args, "clear", False)
    cluster_name: str | None = getattr(args, "cluster_name", None)

    plan = load_plan()
    if clear_flag:
        prev = plan.get("active_cluster")
        clear_focus(plan)
        append_log_entry(
            plan, "focus", actor="user",
            detail={"action": "clear", "previous": prev},
        )
        save_plan(plan)
        print(colorize("  Focus cleared.", "green"))
        return

    if not cluster_name:
        active = plan.get("active_cluster")
        if active:
            print(f"  Focused on: {active}")
        else:
            print("  No active focus.")
        return

    try:
        set_focus(plan, cluster_name)
    except ValueError as ex:
        print(colorize(f"  {ex}", "red"))
        return
    append_log_entry(
        plan, "focus", cluster_name=cluster_name, actor="user",
        detail={"action": "set"},
    )
    save_plan(plan)
    print(colorize(f"  Focused on: {cluster_name}", "green"))


__all__ = [
    "cmd_plan_describe",
    "cmd_plan_resolve",
    "cmd_plan_focus",
    "cmd_plan_note",
    "cmd_plan_reopen",
    "cmd_plan_skip",
    "cmd_plan_unskip",
]
