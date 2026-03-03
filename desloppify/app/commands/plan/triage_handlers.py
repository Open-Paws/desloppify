"""Handler for ``plan triage`` subcommand.

Implements a staged workflow: OBSERVE → REFLECT → ORGANIZE → COMMIT
with a fast-track CONFIRM-EXISTING skip path.

Stage gates validate **plan data enrichment**, not text reports:
- OBSERVE: lightweight — write an analysis of themes/root causes (100 char min)
- REFLECT: compare current issues against completed work (recurring patterns)
- ORGANIZE: structural — each manual cluster must have description + action_steps
- COMMIT: strategy must be substantive (200 char min) or "same"
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.app.commands.helpers.state import require_completed_scan
from desloppify.app.commands.plan.triage_playbook import (
    TRIAGE_STAGE_DEPENDENCIES,
    TRIAGE_STAGE_LABELS,
    TRIAGE_CMD_CLUSTER_ADD,
    TRIAGE_CMD_CLUSTER_CREATE,
    TRIAGE_CMD_CLUSTER_ENRICH_COMPACT,
    TRIAGE_CMD_CLUSTER_STEPS,
    TRIAGE_CMD_COMPLETE_VERBOSE,
    TRIAGE_CMD_CONFIRM_EXISTING,
    TRIAGE_CMD_OBSERVE,
    TRIAGE_CMD_ORGANIZE,
    TRIAGE_CMD_REFLECT,
)
from desloppify.app.commands.plan.triage.shared import _unenriched_clusters
from desloppify.app.commands.helpers.display import short_issue_id
from desloppify.core.output_api import colorize
from desloppify.engine.plan import (
    TRIAGE_IDS,
    TRIAGE_STAGE_IDS,
    append_log_entry,
    build_triage_prompt,
    collect_triage_input,
    detect_recurring_patterns,
    extract_issue_citations,
    load_plan,
    purge_ids,
    review_issue_snapshot_hash,
    save_plan,
)
from desloppify.state import utc_now


_STAGE_ORDER = ["observe", "reflect", "organize"]


def _has_triage_in_queue(plan: dict) -> bool:
    """Check if any triage stage ID is in the queue."""
    order = set(plan.get("queue_order", []))
    return bool(order & TRIAGE_IDS)


def _inject_triage_stages(plan: dict) -> None:
    """Inject all 4 triage stage IDs into the queue (fresh start)."""
    order: list[str] = plan.setdefault("queue_order", [])
    existing = set(order)
    for sid in TRIAGE_STAGE_IDS:
        if sid not in existing:
            order.insert(0 if sid == TRIAGE_STAGE_IDS[0] else len(order), sid)
    # Re-insert in correct order at front
    for sid in reversed(TRIAGE_STAGE_IDS):
        if sid in order:
            order.remove(sid)
    insert_at = 0
    for sid in TRIAGE_STAGE_IDS:
        order.insert(insert_at, sid)
        insert_at += 1


def _purge_triage_stage(plan: dict, stage_name: str) -> None:
    """Purge a single triage stage ID from the queue."""
    sid = f"triage::{stage_name}"
    purge_ids(plan, [sid])


def _cascade_clear_later_confirmations(stages: dict, from_stage: str) -> list[str]:
    """Clear confirmed_at/confirmed_text on stages AFTER *from_stage*. Returns cleared names."""
    try:
        idx = _STAGE_ORDER.index(from_stage)
    except ValueError:
        return []
    cleared: list[str] = []
    for later in _STAGE_ORDER[idx + 1:]:
        if later in stages and stages[later].get("confirmed_at"):
            stages[later].pop("confirmed_at", None)
            stages[later].pop("confirmed_text", None)
            cleared.append(later)
    return cleared


def _print_cascade_clear_feedback(cleared: list[str], stages: dict) -> None:
    """Print yellow cascade-clear message with next-step guidance."""
    if not cleared:
        return
    print(colorize(f"  Cleared confirmations on: {', '.join(cleared)}", "yellow"))
    next_unconfirmed = next(
        (s for s in _STAGE_ORDER if s in stages and not stages[s].get("confirmed_at")),
        None,
    )
    if next_unconfirmed:
        print(colorize(
            f"  Re-confirm with: desloppify plan triage --confirm {next_unconfirmed}",
            "dim",
        ))


def _observe_dimension_breakdown(si) -> tuple[dict[str, int], list[str]]:
    """Count issues per dimension from a TriageInput. Returns (by_dim, sorted_dim_names)."""
    by_dim: dict[str, int] = defaultdict(int)
    for _fid, f in si.open_issues.items():
        detail = f.get("detail", {}) if isinstance(f.get("detail"), dict) else {}
        dim = detail.get("dimension", "unknown")
        by_dim[dim] += 1
    dim_names = sorted(by_dim, key=lambda d: (-by_dim[d], d))
    return dict(by_dim), dim_names


def _open_review_ids_from_state(state: dict) -> set[str]:
    """Return IDs of all open review/concerns issues in state."""
    return {
        fid for fid, f in state.get("issues", {}).items()
        if f.get("status") == "open" and f.get("detector") in ("review", "concerns")
    }


def _triage_coverage(
    plan: dict,
    open_review_ids: set[str] | None = None,
) -> tuple[int, int, dict]:
    """Return (organized, total, clusters) for review issues in triage.

    When *open_review_ids* is provided, use it as the full set of review
    issues (from state) instead of falling back to queue_order.
    """
    clusters = plan.get("clusters", {})
    all_cluster_ids: set[str] = set()
    for c in clusters.values():
        all_cluster_ids.update(c.get("issue_ids", []))
    if open_review_ids is not None:
        review_ids = list(open_review_ids)
    else:
        review_ids = [
            fid for fid in plan.get("queue_order", [])
            if not fid.startswith("triage::") and not fid.startswith("workflow::") and (fid.startswith("review::") or fid.startswith("concerns::"))
        ]
    organized = sum(1 for fid in review_ids if fid in all_cluster_ids)
    return organized, len(review_ids), clusters


def _manual_clusters_with_issues(plan: dict) -> list[str]:
    """Return names of non-auto clusters that have issues."""
    return [
        name for name, c in plan.get("clusters", {}).items()
        if c.get("issue_ids") and not c.get("auto")
    ]


def _print_stage_progress(stages: dict, plan: dict | None = None) -> None:
    """Print the 4-stage progress indicator."""
    print(colorize("  Stages:", "dim"))
    for stage_name, label in TRIAGE_STAGE_LABELS:
        if stage_name in stages:
            if stages[stage_name].get("confirmed_at"):
                print(colorize(f"    \u2713 {label} (confirmed)", "green"))
            else:
                print(colorize(f"    \u2713 {label} (needs confirm)", "yellow"))
        elif TRIAGE_STAGE_DEPENDENCIES[stage_name].issubset(stages):
            print(colorize(f"    \u2192 {label} (current)", "yellow"))
        else:
            print(colorize(f"    \u25cb {label}", "dim"))

    # Show enrichment gaps when in the organize stage
    if plan and "reflect" in stages and "organize" not in stages:
        gaps = _unenriched_clusters(plan)
        manual = _manual_clusters_with_issues(plan)
        if not manual:
            print(colorize("\n    No manual clusters yet. Create clusters and enrich them.", "yellow"))
        elif gaps:
            print(colorize(f"\n    {len(gaps)} cluster(s) need enrichment:", "yellow"))
            for name, missing in gaps:
                print(colorize(f"      {name}: missing {', '.join(missing)}", "yellow"))
            print(colorize(
                f"      Fix: {TRIAGE_CMD_CLUSTER_ENRICH_COMPACT}",
                "dim",
            ))
        else:
            print(colorize(f"\n    All {len(manual)} manual cluster(s) enriched.", "green"))


def _print_progress(plan: dict, open_issues: dict) -> None:
    """Show cluster state and unclustered issues."""
    clusters = plan.get("clusters", {})
    # Only show clusters that actually have issues (hide empty/stale ones)
    active_clusters = {
        name: c for name, c in clusters.items()
        if c.get("issue_ids")
    }
    if active_clusters:
        print(colorize("\n  Current clusters:", "cyan"))
        for name, cluster in active_clusters.items():
            count = len(cluster.get("issue_ids", []))
            desc = cluster.get("description") or ""
            steps = cluster.get("action_steps", [])
            auto = cluster.get("auto", False)
            tags: list[str] = []
            if auto:
                tags.append("auto")
            if desc:
                tags.append("desc")
            else:
                tags.append("no desc")
            if steps:
                tags.append(f"{len(steps)} steps")
            else:
                if not auto:
                    tags.append("no steps")
            tag_str = f" [{', '.join(tags)}]"
            desc_str = f" \u2014 {desc}" if desc else ""
            print(f"    {name}: {count} items{tag_str}{desc_str}")

    all_clustered: set[str] = set()
    for c in clusters.values():
        all_clustered.update(c.get("issue_ids", []))
    unclustered = [fid for fid in open_issues if fid not in all_clustered]
    if unclustered:
        print(colorize(f"\n  {len(unclustered)} issues not yet in a cluster:", "yellow"))
        for fid in unclustered[:10]:
            f = open_issues[fid]
            dim = (f.get("detail", {}) or {}).get("dimension", "") if isinstance(f.get("detail"), dict) else ""
            short = short_issue_id(fid)
            print(f"    [{short}] [{dim}] {f.get('summary', '')}")
        if len(unclustered) > 10:
            print(colorize(f"    ... and {len(unclustered) - 10} more", "dim"))
    elif open_issues:
        organized, total, _ = _triage_coverage(plan, open_review_ids=set(open_issues.keys()))
        print(colorize(f"\n  All {organized}/{total} issues are in clusters.", "green"))


def _apply_completion(args: argparse.Namespace, plan: dict, strategy: str) -> None:
    """Shared completion logic: update meta, remove triage::pending, save."""
    runtime = command_runtime(args)
    state = runtime.state

    organized, total, clusters = _triage_coverage(
        plan, open_review_ids=_open_review_ids_from_state(state),
    )

    # Purge all triage stage IDs.
    purge_ids(plan, list(TRIAGE_IDS))

    current_hash = review_issue_snapshot_hash(state)

    meta = plan.setdefault("epic_triage_meta", {})
    meta["issue_snapshot_hash"] = current_hash
    open_review_ids = sorted(
        fid for fid, f in state.get("issues", {}).items()
        if f.get("status") == "open" and f.get("detector") in ("review", "concerns")
    )
    meta["triaged_ids"] = open_review_ids
    if strategy.strip().lower() != "same":
        meta["strategy_summary"] = strategy
    meta["trigger"] = "manual_triage"
    meta["last_completed_at"] = utc_now()
    # Archive stages before clearing so previous analysis is preserved
    stages = meta.get("triage_stages", {})
    if stages:
        meta["last_triage"] = {
            "completed_at": utc_now(),
            "stages": {k: dict(v) for k, v in stages.items()},
            "strategy": strategy if strategy.strip().lower() != "same" else meta.get("strategy_summary", ""),
        }
    meta["triage_stages"] = {}  # clear stages on completion
    meta.pop("stage_refresh_required", None)
    meta.pop("stage_snapshot_hash", None)

    save_plan(plan)

    cluster_count = len([c for c in clusters.values() if c.get("issue_ids")])
    print(colorize(f"  Triage complete: {organized}/{total} issues in {cluster_count} cluster(s).", "green"))
    effective_strategy = strategy if strategy.strip().lower() != "same" else meta.get("strategy_summary", "")
    if effective_strategy:
        print(colorize(f"  Strategy: {effective_strategy}", "cyan"))
    print(colorize("  Run `desloppify next` to start implementation.", "green"))


# ---------------------------------------------------------------------------
# Stage handlers
# ---------------------------------------------------------------------------

def _cmd_stage_observe(args: argparse.Namespace) -> None:
    """Record the OBSERVE stage: agent analyses themes and root causes.

    No citation gate — the point is genuine analysis, not ID-stuffing.
    Just requires a 100-char report describing what the agent observed.
    """
    report: str | None = getattr(args, "report", None)

    runtime = command_runtime(args)
    state = runtime.state
    plan = load_plan()

    # Auto-start: inject triage stage IDs if not present
    if not _has_triage_in_queue(plan):
        _inject_triage_stages(plan)
        meta = plan.setdefault("epic_triage_meta", {})
        meta["triage_stages"] = {}
        save_plan(plan)
        print(colorize("  Planning mode auto-started (4 stages queued).", "cyan"))

    meta = plan.setdefault("epic_triage_meta", {})
    stages = meta.setdefault("triage_stages", {})
    existing_stage = stages.get("observe")

    # Jump-back: reuse existing report if no --report provided
    is_reuse = False
    if not report and existing_stage and existing_stage.get("report"):
        report = existing_stage["report"]
        is_reuse = True
    elif not report:
        print(colorize("  --report is required for --stage observe.", "red"))
        print(colorize("  Write an analysis of the issues: themes, root causes, contradictions.", "dim"))
        print(colorize("  Identify issues that contradict each other (opposite recommendations).", "dim"))
        print(colorize("  Do NOT just list issue IDs — describe what you actually observe.", "dim"))
        return

    si = collect_triage_input(plan, state)
    issue_count = len(si.open_issues)

    # Edge case: 0 issues
    if issue_count == 0:
        stages["observe"] = {
            "stage": "observe",
            "report": report,
            "cited_ids": [],
            "timestamp": utc_now(),
            "issue_count": 0,
        }
        if is_reuse and existing_stage and existing_stage.get("confirmed_at"):
            stages["observe"]["confirmed_at"] = existing_stage["confirmed_at"]
            stages["observe"]["confirmed_text"] = existing_stage.get("confirmed_text", "")
        cleared = _cascade_clear_later_confirmations(stages, "observe")
        if not is_reuse:
            stages["observe"].pop("confirmed_at", None)
            stages["observe"].pop("confirmed_text", None)
        save_plan(plan)
        print(colorize("  Observe stage recorded (no issues to analyse).", "green"))
        if is_reuse:
            print(colorize("  Observe data preserved (no changes).", "dim"))
            if cleared:
                _print_cascade_clear_feedback(cleared, stages)
        return

    # Validation: report length (no citation counting)
    min_chars = 50 if issue_count <= 3 else 100
    if len(report) < min_chars:
        print(colorize(f"  Report too short: {len(report)} chars (minimum {min_chars}).", "red"))
        print(colorize("  Describe themes, root causes, contradictions, and how issues relate.", "dim"))
        return

    # Save stage (still extract citations for analytics, but don't gate on them)
    valid_ids = set(si.open_issues.keys())
    cited = extract_issue_citations(report, valid_ids)

    stages["observe"] = {
        "stage": "observe",
        "report": report,
        "cited_ids": sorted(cited),
        "timestamp": utc_now(),
        "issue_count": issue_count,
    }

    # Jump-back: preserve or clear confirmation
    if is_reuse and existing_stage and existing_stage.get("confirmed_at"):
        stages["observe"]["confirmed_at"] = existing_stage["confirmed_at"]
        stages["observe"]["confirmed_text"] = existing_stage.get("confirmed_text", "")
    cleared = _cascade_clear_later_confirmations(stages, "observe")

    save_plan(plan)

    append_log_entry(plan, "triage_observe", actor="user",
                     detail={"issue_count": issue_count, "cited_ids": sorted(cited),
                             "reuse": is_reuse})
    save_plan(plan)

    print(colorize(
        f"  Observe stage recorded: {issue_count} issues analysed.",
        "green",
    ))
    if is_reuse:
        print(colorize("  Observe data preserved (no changes).", "dim"))
        if cleared:
            _print_cascade_clear_feedback(cleared, stages)
    else:
        print(colorize("  Now confirm your analysis.", "yellow"))
        print(colorize("    desloppify plan triage --confirm observe", "dim"))


def _cmd_stage_reflect(args: argparse.Namespace) -> None:
    """Record the REFLECT stage: compare current issues against completed work.

    Forces the agent to consider what was previously resolved and whether
    similar issues are recurring. Requires a 100-char report (50 if ≤3 issues).
    If recurring patterns are detected, the report must mention at least one
    recurring dimension name.
    """
    report: str | None = getattr(args, "report", None)
    attestation: str | None = getattr(args, "attestation", None)

    runtime = command_runtime(args)
    state = runtime.state
    plan = load_plan()

    if not _has_triage_in_queue(plan):
        print(colorize("  No planning stages in the queue — nothing to reflect on.", "yellow"))
        return

    meta = plan.get("epic_triage_meta", {})
    stages = meta.get("triage_stages", {})

    # Jump-back: reuse existing report if no --report provided
    existing_stage = stages.get("reflect")
    is_reuse = False
    if not report and existing_stage and existing_stage.get("report"):
        report = existing_stage["report"]
        is_reuse = True
    elif not report:
        print(colorize("  --report is required for --stage reflect.", "red"))
        print(colorize("  Compare current issues against completed work and form a holistic strategy:", "dim"))
        print(colorize("  - What clusters were previously completed? Did fixes hold?", "dim"))
        print(colorize("  - Are any dimensions recurring (resolved before, open again)?", "dim"))
        print(colorize("  - What contradictions did you find? Which direction will you take?", "dim"))
        print(colorize("  - Big picture: what to prioritize, what to defer, what to skip?", "dim"))
        return

    if "observe" not in stages:
        print(colorize("  Cannot reflect: observe stage not complete.", "red"))
        print(colorize('  Run: desloppify plan triage --stage observe --report "..."', "dim"))
        return

    si = collect_triage_input(plan, state)

    # Fold-confirm: auto-confirm observe if attestation provided
    if not stages["observe"].get("confirmed_at"):
        if attestation and len(attestation.strip()) >= _MIN_ATTESTATION_LEN:
            _by_dim, dim_names = _observe_dimension_breakdown(si)
            validation_err = _validate_attestation(attestation.strip(), "observe", dimensions=dim_names)
            if validation_err:
                print(colorize(f"  {validation_err}", "red"))
                return
            stages["observe"]["confirmed_at"] = utc_now()
            stages["observe"]["confirmed_text"] = attestation.strip()
            save_plan(plan)
            print(colorize("  \u2713 Observe auto-confirmed via --attestation.", "green"))
        else:
            print(colorize("  Cannot reflect: observe stage not confirmed.", "red"))
            print(colorize("  Run: desloppify plan triage --confirm observe", "dim"))
            print(colorize("  Or pass --attestation to auto-confirm observe inline.", "dim"))
            return

    issue_count = len(si.open_issues)

    # Validation: report length
    min_chars = 50 if issue_count <= 3 else 100
    if len(report) < min_chars:
        print(colorize(f"  Report too short: {len(report)} chars (minimum {min_chars}).", "red"))
        print(colorize("  Describe how current issues relate to previously completed work.", "dim"))
        return

    # Detect recurring patterns
    recurring = detect_recurring_patterns(si.open_issues, si.resolved_issues)
    recurring_dims = sorted(recurring.keys())

    # If recurring patterns exist, report must mention at least one dimension
    if recurring_dims:
        report_lower = report.lower()
        mentioned = [dim for dim in recurring_dims if dim.lower() in report_lower]
        if not mentioned:
            print(colorize("  Recurring patterns detected but not addressed in report:", "red"))
            for dim in recurring_dims:
                info = recurring[dim]
                print(colorize(
                    f"    {dim}: {len(info['resolved'])} resolved, "
                    f"{len(info['open'])} still open — potential loop",
                    "yellow",
                ))
            print(colorize(
                "  Your report must mention at least one recurring dimension name.",
                "dim",
            ))
            return

    # Save stage
    stages = meta.setdefault("triage_stages", {})
    reflect_stage = {
        "stage": "reflect",
        "report": report,
        "cited_ids": [],
        "timestamp": utc_now(),
        "issue_count": issue_count,
        "recurring_dims": recurring_dims,
    }
    stages["reflect"] = reflect_stage

    # Jump-back: preserve or clear confirmation
    if is_reuse and existing_stage and existing_stage.get("confirmed_at"):
        stages["reflect"]["confirmed_at"] = existing_stage["confirmed_at"]
        stages["reflect"]["confirmed_text"] = existing_stage.get("confirmed_text", "")
    cleared = _cascade_clear_later_confirmations(stages, "reflect")

    save_plan(plan)

    append_log_entry(plan, "triage_reflect", actor="user",
                     detail={"issue_count": issue_count, "recurring_dims": recurring_dims,
                             "reuse": is_reuse})
    save_plan(plan)

    _print_reflect_result(
        issue_count=issue_count,
        recurring_dims=recurring_dims,
        recurring=recurring,
        report=report,
        is_reuse=is_reuse,
        cleared=cleared,
        stages=stages,
    )


def _print_reflect_result(
    *,
    issue_count: int,
    recurring_dims: list[str],
    recurring: dict,
    report: str,
    is_reuse: bool,
    cleared: list,
    stages: dict,
) -> None:
    """Print the reflect stage output including briefing box and next steps."""
    print(colorize(
        f"  Reflect stage recorded: {issue_count} issues, "
        f"{len(recurring_dims)} recurring dimension(s).",
        "green",
    ))
    if is_reuse:
        print(colorize("  Reflect data preserved (no changes).", "dim"))
        if cleared:
            _print_cascade_clear_feedback(cleared, stages)
    else:
        print(colorize("  Now confirm your strategy.", "yellow"))
        print(colorize("    desloppify plan triage --confirm reflect", "dim"))
    if recurring_dims:
        for dim in recurring_dims:
            info = recurring[dim]
            print(colorize(
                f"    {dim}: {len(info['resolved'])} resolved, {len(info['open'])} still open",
                "dim",
            ))

    print()
    print(colorize("  \u250c\u2500 Strategic briefing (share with user before organizing) \u2500\u2510", "cyan"))
    for line in report.strip().splitlines():
        print(colorize(f"  \u2502 {line}", "cyan"))
    print(colorize("  \u2514" + "\u2500" * 57 + "\u2518", "cyan"))
    print()
    print(colorize(
        "  IMPORTANT: Present your holistic strategy to the user. Explain:",
        "yellow",
    ))
    print(colorize(
        "  - What themes and root causes you see",
        "yellow",
    ))
    print(colorize(
        "  - What contradictions you found and which direction you'll take",
        "yellow",
    ))
    print(colorize(
        "  - What you'll prioritize, what you'll defer, the overall arc of work",
        "yellow",
    ))
    print(colorize(
        "  Wait for their input before creating clusters.",
        "yellow",
    ))
    print()
    print(colorize(
        "  Then create clusters and enrich each with action steps:",
        "dim",
    ))
    print(colorize(
        '    desloppify plan cluster create <name> --description "..."',
        "dim",
    ))
    print(colorize(
        "    desloppify plan cluster add <name> <issue-patterns>",
        "dim",
    ))
    print(colorize(
        '    desloppify plan cluster update <name> --steps "step 1" "step 2" ...',
        "dim",
    ))
    print(colorize(
        "    desloppify plan triage --stage organize --report \"summary of what was organized...\"",
        "dim",
    ))


def _cmd_stage_organize(args: argparse.Namespace) -> None:
    """Record the ORGANIZE stage: validates cluster enrichment.

    Instead of gating on a text report, validates that the plan data
    itself has been enriched: each manual cluster needs description +
    action_steps. This forces the agent to actually think about each
    cluster's execution plan.
    """
    report: str | None = getattr(args, "report", None)
    attestation: str | None = getattr(args, "attestation", None)

    plan = load_plan()

    if not _has_triage_in_queue(plan):
        print(colorize("  No planning stages in the queue \u2014 nothing to organize.", "yellow"))
        return

    meta = plan.get("epic_triage_meta", {})
    stages = meta.get("triage_stages", {})

    # Jump-back: reuse existing report if no --report provided
    existing_stage = stages.get("organize")
    is_reuse = False
    if not report and existing_stage and existing_stage.get("report"):
        report = existing_stage["report"]
        is_reuse = True

    if "reflect" not in stages:
        if "observe" not in stages:
            print(colorize("  Cannot organize: observe stage not complete.", "red"))
            print(colorize('  Run: desloppify plan triage --stage observe --report "..."', "dim"))
        else:
            print(colorize("  Cannot organize: reflect stage not complete.", "red"))
            print(colorize('  Run: desloppify plan triage --stage reflect --report "..."', "dim"))
        return

    # Fold-confirm: auto-confirm reflect if attestation provided
    if not stages["reflect"].get("confirmed_at"):
        if attestation and len(attestation.strip()) >= _MIN_ATTESTATION_LEN:
            runtime = command_runtime(args)
            si = collect_triage_input(plan, runtime.state)
            recurring = detect_recurring_patterns(si.open_issues, si.resolved_issues)
            _by_dim, observe_dims = _observe_dimension_breakdown(si)
            reflect_dims = sorted(set((list(recurring.keys()) if recurring else []) + observe_dims))
            reflect_clusters = [n for n in plan.get("clusters", {}) if not plan["clusters"][n].get("auto")]
            validation_err = _validate_attestation(
                attestation.strip(), "reflect",
                dimensions=reflect_dims, cluster_names=reflect_clusters,
            )
            if validation_err:
                print(colorize(f"  {validation_err}", "red"))
                return
            stages["reflect"]["confirmed_at"] = utc_now()
            stages["reflect"]["confirmed_text"] = attestation.strip()
            save_plan(plan)
            print(colorize("  \u2713 Reflect auto-confirmed via --attestation.", "green"))
        else:
            print(colorize("  Cannot organize: reflect stage not confirmed.", "red"))
            print(colorize("  Run: desloppify plan triage --confirm reflect", "dim"))
            print(colorize("  Or pass --attestation to auto-confirm reflect inline.", "dim"))
            return

    # Validate: at least 1 manual cluster with issues
    manual_clusters = _manual_clusters_with_issues(plan)
    if not manual_clusters:
        # Check if there are ANY clusters with issues (including auto)
        any_clusters = [
            name for name, c in plan.get("clusters", {}).items()
            if c.get("issue_ids")
        ]
        if any_clusters:
            print(colorize("  Cannot organize: only auto-clusters exist.", "red"))
            print(colorize("  Create manual clusters that group issues by root cause:", "dim"))
        else:
            print(colorize("  Cannot organize: no clusters with issues exist.", "red"))
        print(colorize('    desloppify plan cluster create <name> --description "..."', "dim"))
        print(colorize("    desloppify plan cluster add <name> <issue-patterns>", "dim"))
        return

    # Validate: all manual clusters are enriched
    gaps = _unenriched_clusters(plan)
    if gaps:
        print(colorize(f"  Cannot organize: {len(gaps)} cluster(s) need enrichment.", "red"))
        for name, missing in gaps:
            print(colorize(f"    {name}: missing {', '.join(missing)}", "yellow"))
        print()
        print(colorize("  Each cluster needs a description and action steps:", "dim"))
        print(colorize(
            '    desloppify plan cluster update <name> --description "what this cluster addresses" '
            '--steps "step 1" "step 2"',
            "dim",
        ))
        return

    # Require report
    if not report:
        print(colorize("  --report is required for --stage organize.", "red"))
        print(colorize("  Summarize your prioritized organization:", "dim"))
        print(colorize("  - Did you defer contradictory issues before clustering?", "dim"))
        print(colorize("  - What clusters did you create and why?", "dim"))
        print(colorize("  - Explicit priority ordering: which cluster 1st, 2nd, 3rd and why?", "dim"))
        print(colorize("  - What depends on what? What unblocks the most?", "dim"))
        return
    if len(report) < 100:
        print(colorize(f"  Report too short: {len(report)} chars (minimum 100).", "red"))
        print(colorize("  Explain what you organized, your priorities, and focus order.", "dim"))
        return

    stages = meta.setdefault("triage_stages", {})
    stages["organize"] = {
        "stage": "organize",
        "report": report,
        "cited_ids": [],
        "timestamp": utc_now(),
        "issue_count": len(manual_clusters),
    }

    # Jump-back: preserve or clear confirmation
    if is_reuse and existing_stage and existing_stage.get("confirmed_at"):
        stages["organize"]["confirmed_at"] = existing_stage["confirmed_at"]
        stages["organize"]["confirmed_text"] = existing_stage.get("confirmed_text", "")
    cleared = _cascade_clear_later_confirmations(stages, "organize")

    save_plan(plan)

    append_log_entry(plan, "triage_organize", actor="user",
                     detail={"cluster_count": len(manual_clusters), "reuse": is_reuse})
    save_plan(plan)

    _print_organize_result(
        manual_clusters=manual_clusters,
        plan=plan,
        report=report,
        is_reuse=is_reuse,
        cleared=cleared,
        stages=stages,
    )


def _print_organize_result(
    *,
    manual_clusters: list[str],
    plan: dict,
    report: str,
    is_reuse: bool,
    cleared: list,
    stages: dict,
) -> None:
    """Print the organize stage output including cluster summary and next steps."""
    print(colorize(
        f"  Organize stage recorded: {len(manual_clusters)} enriched cluster(s).",
        "green",
    ))
    if is_reuse:
        print(colorize("  Organize data preserved (no changes).", "dim"))
        if cleared:
            _print_cascade_clear_feedback(cleared, stages)
    else:
        print(colorize("  Now confirm the plan.", "yellow"))
        print(colorize("    desloppify plan triage --confirm organize", "dim"))
    for name in manual_clusters:
        cluster = plan.get("clusters", {}).get(name, {})
        steps = cluster.get("action_steps", [])
        desc = cluster.get("description", "")
        desc_str = f" \u2014 {desc}" if desc else ""
        print(colorize(f"    {name}: {len(cluster.get('issue_ids', []))} issues, {len(steps)} steps{desc_str}", "dim"))

    print()
    print(colorize("  \u250c\u2500 Prioritized organization (share with user) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510", "cyan"))
    for line in report.strip().splitlines():
        print(colorize(f"  \u2502 {line}", "cyan"))
    print(colorize("  \u2514" + "\u2500" * 57 + "\u2518", "cyan"))
    print()
    print(colorize(
        "  IMPORTANT: Present your prioritized organization to the user. Explain",
        "yellow",
    ))
    print(colorize(
        "  each cluster, why it exists, and your explicit priority ordering \u2014",
        "yellow",
    ))
    print(colorize(
        "  which cluster comes first, second, third, what depends on what,",
        "yellow",
    ))
    print(colorize(
        "  and why that ordering matters.",
        "yellow",
    ))


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------

def _cmd_triage_complete(args: argparse.Namespace) -> None:
    """Complete triage \u2014 requires organize stage (or confirm-existing path)."""
    strategy: str | None = getattr(args, "strategy", None)
    attestation: str | None = getattr(args, "attestation", None)
    plan = load_plan()

    if not _has_triage_in_queue(plan):
        print(colorize("  No planning stages in the queue \u2014 nothing to complete.", "yellow"))
        return

    meta = plan.get("epic_triage_meta", {})
    stages = meta.get("triage_stages", {})

    state = command_runtime(args).state
    review_ids = _open_review_ids_from_state(state)

    # Require organize stage confirmed
    if "organize" not in stages:
        if "observe" not in stages:
            print(colorize("  Cannot complete: no stages done yet.", "red"))
            print(colorize('  Start with: desloppify plan triage --stage observe --report "..."', "dim"))
        else:
            print(colorize("  Cannot complete: organize stage not done.", "red"))
            gaps = _unenriched_clusters(plan)
            if gaps:
                print(colorize(f"  {len(gaps)} cluster(s) still need enrichment:", "yellow"))
                for name, missing in gaps:
                    print(colorize(f"    {name}: missing {', '.join(missing)}", "yellow"))
                print(colorize(
                    '  Fix: desloppify plan cluster update <name> --description "..." --steps "step1" "step2"',
                    "dim",
                ))
                print(colorize(
                    f"  Then: {TRIAGE_CMD_ORGANIZE}",
                    "dim",
                ))
            else:
                manual = _manual_clusters_with_issues(plan)
                if manual:
                    print(colorize("  Clusters are enriched. Record the organize stage first:", "dim"))
                    print(colorize(f"    {TRIAGE_CMD_ORGANIZE}", "dim"))
                else:
                    print(colorize("  Create enriched clusters first, then record organize:", "dim"))
                    print(colorize(f"    {TRIAGE_CMD_ORGANIZE}", "dim"))
            if meta.get("strategy_summary"):
                print(colorize('  Or fast-track: --confirm-existing --note "why plan is still valid" --strategy "..."', "dim"))
        return

    # Fold-confirm: auto-confirm organize if attestation provided
    if not stages["organize"].get("confirmed_at"):
        if attestation and len(attestation.strip()) >= _MIN_ATTESTATION_LEN:
            organize_clusters = [n for n in plan.get("clusters", {}) if not plan["clusters"][n].get("auto")]
            validation_err = _validate_attestation(
                attestation.strip(), "organize", cluster_names=organize_clusters,
            )
            if validation_err:
                print(colorize(f"  {validation_err}", "red"))
                return
            organized, total, _ = _triage_coverage(plan, open_review_ids=review_ids)
            stages["organize"]["confirmed_at"] = utc_now()
            stages["organize"]["confirmed_text"] = attestation.strip()
            save_plan(plan)
            print(colorize("  \u2713 Organize auto-confirmed via --attestation.", "green"))
        else:
            print(colorize("  Cannot complete: organize stage not confirmed.", "red"))
            print(colorize("  Run: desloppify plan triage --confirm organize", "dim"))
            print(colorize("  Or pass --attestation to auto-confirm organize inline.", "dim"))
            return

    # Re-validate cluster enrichment at completion time (prevents bypassing
    # organize gate by editing plan.json directly)
    manual_clusters = _manual_clusters_with_issues(plan)
    if not manual_clusters:
        any_clusters = [
            name for name, c in plan.get("clusters", {}).items()
            if c.get("issue_ids")
        ]
        if not any_clusters:
            print(colorize("  Cannot complete: no clusters with issues exist.", "red"))
            print(colorize('  Create clusters: desloppify plan cluster create <name> --description "..."', "dim"))
            return

    gaps = _unenriched_clusters(plan)
    if gaps:
        print(colorize(f"  Cannot complete: {len(gaps)} cluster(s) still need enrichment.", "red"))
        for name, missing in gaps:
            print(colorize(f"    {name}: missing {', '.join(missing)}", "yellow"))
        print(colorize(
            '  Fix: desloppify plan cluster update <name> --description "..." --steps "step1" "step2"',
            "dim",
        ))
        return

    # Verify cluster coverage
    organized, total, clusters = _triage_coverage(plan, open_review_ids=review_ids)

    if total > 0 and organized == 0:
        print(colorize("  Cannot complete: no issues have been organized into clusters.", "red"))
        print(colorize(f"  {total} issues are waiting.", "dim"))
        return

    if total > 0 and organized < total:
        remaining = total - organized
        print(colorize(
            f"  Warning: {remaining}/{total} issues are not yet in any cluster.",
            "yellow",
        ))

    # Strategy required
    if not strategy:
        print(colorize("  --strategy is required.", "red"))
        existing = meta.get("strategy_summary", "")
        if existing:
            print(colorize(f"  Current strategy: {existing}", "dim"))
            print(colorize('  Use --strategy "same" to keep it, or provide a new summary.', "dim"))
        else:
            print(colorize('  Provide --strategy "execution plan describing priorities, ordering, and verification approach"', "dim"))
        return

    # Strategy length check (unless "same") — 200 chars forces substantive content
    if strategy.strip().lower() != "same" and len(strategy.strip()) < 200:
        print(colorize(f"  Strategy too short: {len(strategy.strip())} chars (minimum 200).", "red"))
        print(colorize("  The strategy should describe:", "dim"))
        print(colorize("    - Execution order and priorities", "dim"))
        print(colorize("    - What each cluster accomplishes", "dim"))
        print(colorize("    - How to verify the work is correct", "dim"))
        return

    # Show summary
    print(colorize("  Triage summary:", "bold"))
    if "observe" in stages:
        obs = stages["observe"]
        print(colorize(f"    Observe: {obs.get('issue_count', '?')} issues analysed", "dim"))
    if "reflect" in stages:
        ref = stages["reflect"]
        recurring = ref.get("recurring_dims", [])
        if recurring:
            print(colorize(f"    Reflect: {len(recurring)} recurring dimension(s)", "dim"))
        else:
            print(colorize("    Reflect: no recurring patterns", "dim"))
    if "organize" in stages:
        manual = _manual_clusters_with_issues(plan)
        print(colorize(f"    Organize: {len(manual)} enriched cluster(s)", "dim"))
        for name in manual:
            cluster = plan.get("clusters", {}).get(name, {})
            steps = cluster.get("action_steps", [])
            print(colorize(f"      {name}: {len(steps)} steps", "dim"))

    organized, total, _ = _triage_coverage(plan, open_review_ids=review_ids)

    # Jump-back guidance before committing
    print()
    print(colorize("  To revise an earlier stage: desloppify plan triage --stage <observe|reflect|organize>", "dim"))
    print(colorize("  Pass --report to update, or omit to keep existing analysis.", "dim"))

    append_log_entry(plan, "triage_complete", actor="user",
                     detail={
                         "strategy_len": len(strategy.strip()),
                         "coverage": f"{organized}/{total}",
                     })

    _apply_completion(args, plan, strategy)


# ---------------------------------------------------------------------------
# Confirm-existing (skip path)
# ---------------------------------------------------------------------------

def _cmd_confirm_existing(args: argparse.Namespace) -> None:
    """Fast-track: confirm existing plan structure is still valid."""
    note: str | None = getattr(args, "note", None)
    strategy: str | None = getattr(args, "strategy", None)
    confirmed: str | None = getattr(args, "confirmed", None)
    plan = load_plan()

    if not _has_triage_in_queue(plan):
        print(colorize("  No planning stages in the queue — nothing to confirm.", "yellow"))
        return

    meta = plan.get("epic_triage_meta", {})
    stages = meta.get("triage_stages", {})

    # Require a prior completed triage — can't skip the full flow on first run
    prior_strategy = meta.get("strategy_summary", "")
    if not prior_strategy:
        print(colorize("  Cannot confirm existing: no prior triage has been completed.", "red"))
        print(colorize("  The full OBSERVE → REFLECT → ORGANIZE → COMMIT flow is required the first time.", "dim"))
        print(colorize(f"  Create and enrich clusters, then: {TRIAGE_CMD_ORGANIZE}", "dim"))
        return

    # Determine if this is a light-path (additions only) or full ceremony
    runtime = command_runtime(args)
    state = runtime.state
    si = collect_triage_input(plan, state)
    has_only_additions = bool(si.new_since_last) and not si.resolved_since_last

    if not has_only_additions:
        # Full ceremony: require observe + reflect
        if "observe" not in stages:
            print(colorize("  Cannot confirm existing: observe stage not complete.", "red"))
            print(colorize("  You must read issues first.", "dim"))
            print(colorize('  Run: desloppify plan triage --stage observe --report "..."', "dim"))
            return
        if "reflect" not in stages:
            print(colorize("  Cannot confirm existing: reflect stage not complete.", "red"))
            print(colorize("  You must compare against completed work first.", "dim"))
            print(colorize('  Run: desloppify plan triage --stage reflect --report "..."', "dim"))
            return
    else:
        # Light path: show new items for review, no prior stages needed
        print(colorize(f"  {len(si.new_since_last)} new issue(s) since last triage:", "cyan"))
        for fid in sorted(si.new_since_last):
            f = si.open_issues.get(fid, {})
            print(f"    * [{short_issue_id(fid)}] {f.get('summary', '')}")
        print()

    # Require existing enriched clusters
    clusters_with_issues = _manual_clusters_with_issues(plan)
    if not clusters_with_issues:
        print(colorize("  Cannot confirm existing: no clusters with issues exist.", "red"))
        print(colorize("  Use the full organize flow instead.", "dim"))
        return

    # Require note
    if not note:
        print(colorize("  --note is required for confirm-existing.", "red"))
        print(colorize('  Explain why the existing plan is still valid (min 100 chars).', "dim"))
        return
    if len(note) < 100:
        print(colorize(f"  Note too short: {len(note)} chars (minimum 100).", "red"))
        return

    # Require strategy (default to "same" on light path)
    if not strategy:
        if has_only_additions:
            strategy = "same"
        else:
            print(colorize("  --strategy is required.", "red"))
            existing = meta.get("strategy_summary", "")
            if existing:
                print(colorize('  Use --strategy "same" to keep it, or provide a new summary.', "dim"))
            return

    # Strategy length check (unless "same")
    if strategy.strip().lower() != "same" and len(strategy.strip()) < 200:
        print(colorize(f"  Strategy too short: {len(strategy.strip())} chars (minimum 200).", "red"))
        return

    # Require --confirmed with plan review
    if not confirmed or len(confirmed.strip()) < _MIN_ATTESTATION_LEN:
        # Show the plan and ask for confirmation
        print(colorize("  Current plan:", "bold"))
        _show_plan_summary(plan, state)
        if confirmed:
            print(colorize(
                f"\n  --confirmed text too short ({len(confirmed.strip())} chars, min {_MIN_ATTESTATION_LEN}).",
                "red",
            ))
        print(colorize('\n  Add --confirmed "I validate this plan..." to proceed.', "dim"))
        return

    # Validate: note cites at least 1 new/changed issue (if there are any)
    new_ids = si.new_since_last
    if new_ids:
        valid_ids = set(si.open_issues.keys())
        cited = extract_issue_citations(note, valid_ids)
        new_cited = cited & new_ids
        if not new_cited:
            print(colorize("  Note must cite at least 1 new/changed issue.", "red"))
            print(colorize(f"  {len(new_ids)} new issue(s) since last triage:", "dim"))
            for fid in sorted(new_ids)[:5]:
                print(colorize(f"    {fid}", "dim"))
            if len(new_ids) > 5:
                print(colorize(f"    ... and {len(new_ids) - 5} more", "dim"))
            return

    # Record organize as confirmed-existing and complete
    stages = meta.setdefault("triage_stages", {})
    stages["organize"] = {
        "stage": "organize",
        "report": f"[confirmed-existing] {note}",
        "cited_ids": [],
        "timestamp": utc_now(),
        "issue_count": len(clusters_with_issues),
        "confirmed_at": utc_now(),
        "confirmed_text": confirmed.strip(),
    }

    append_log_entry(plan, "triage_confirm_existing", actor="user",
                     detail={"confirmed_text": confirmed.strip()})

    _apply_completion(args, plan, strategy)
    print(colorize("  Confirmed existing plan — triage complete.", "green"))


# ---------------------------------------------------------------------------
# Reflect dashboard
# ---------------------------------------------------------------------------

def _print_reflect_dashboard(si: object, plan: dict) -> None:
    """Show completed clusters, resolved issues, and recurring patterns."""
    # si is a TriageInput
    completed = getattr(si, "completed_clusters", [])
    resolved = getattr(si, "resolved_issues", {})
    open_issues = getattr(si, "open_issues", {})

    if completed:
        print(colorize("\n  Previously completed clusters:", "cyan"))
        for c in completed[:10]:
            name = c.get("name", "?")
            count = len(c.get("issue_ids", []))
            thesis = c.get("thesis", "")
            print(f"    {name}: {count} issues")
            if thesis:
                print(colorize(f"      {thesis}", "dim"))
            for step in c.get("action_steps", [])[:3]:
                print(colorize(f"      - {step}", "dim"))
        if len(completed) > 10:
            print(colorize(f"    ... and {len(completed) - 10} more", "dim"))

    if resolved:
        print(colorize(f"\n  Resolved issues since last triage: {len(resolved)}", "cyan"))
        for fid, f in sorted(resolved.items())[:10]:
            status = f.get("status", "")
            summary = f.get("summary", "")
            detail = f.get("detail", {}) if isinstance(f.get("detail"), dict) else {}
            dim = detail.get("dimension", "")
            print(f"    [{status}] [{dim}] {summary}")
            print(colorize(f"      {fid}", "dim"))
        if len(resolved) > 10:
            print(colorize(f"    ... and {len(resolved) - 10} more", "dim"))

    recurring = detect_recurring_patterns(open_issues, resolved)
    if recurring:
        print(colorize("\n  Recurring patterns detected:", "yellow"))
        for dim, info in sorted(recurring.items()):
            resolved_count = len(info["resolved"])
            open_count = len(info["open"])
            label = "potential loop" if open_count >= resolved_count else "root cause unaddressed"
            print(colorize(
                f"    {dim}: {resolved_count} resolved, {open_count} still open — {label}",
                "yellow",
            ))
    elif not completed and not resolved:
        print(colorize("\n  First triage — no prior work to compare against.", "dim"))
        print(colorize("  Focus your reflect report on your strategy:", "yellow"))
        print(colorize("  - How will you resolve contradictions you identified in observe?", "dim"))
        print(colorize("  - Which issues will you cluster together vs defer?", "dim"))
        print(colorize("  - What's the overall arc of work and why?", "dim"))


# ---------------------------------------------------------------------------
# Dashboard (default view)
# ---------------------------------------------------------------------------

def _cmd_triage_dashboard(args: argparse.Namespace) -> None:
    """Default view: show issues, stage progress, and next command."""
    runtime = command_runtime(args)
    state = runtime.state
    plan = load_plan()
    si = collect_triage_input(plan, state)
    meta = plan.get("epic_triage_meta", {})
    stages = meta.get("triage_stages", {})

    print(colorize("  Epic triage \u2014 manual", "bold"))
    print(colorize("  " + "\u2500" * 60, "dim"))
    print(f"  Open review issues: {len(si.open_issues)}")
    print(colorize("  Goal: identify contradictions, resolve them, then group the coherent", "cyan"))
    print(colorize("  remainder into clusters by root cause with action steps and priorities.", "cyan"))
    if si.existing_epics:
        print(f"  Existing epics: {len(si.existing_epics)}")
    if si.new_since_last:
        print(colorize(f"  New since last triage: {len(si.new_since_last)}", "yellow"))
        for fid in sorted(si.new_since_last):
            f = si.open_issues.get(fid, {})
            dim = ""
            detail = f.get("detail")
            if isinstance(detail, dict):
                dim = detail.get("dimension", "")
            dim_tag = f" ({dim})" if dim else ""
            print(colorize(f"    * [{short_issue_id(fid)}] {f.get('summary', '')}{dim_tag}", "yellow"))
    if si.resolved_since_last:
        print(f"  Resolved since last triage: {len(si.resolved_since_last)}")

    # Stage progress (with enrichment gaps)
    print()
    _print_stage_progress(stages, plan)
    if meta.get("stage_refresh_required"):
        print(
            colorize(
                "  Note: review issues changed since stage progress started; "
                "refresh stage reports before completion.",
                "yellow",
            )
        )

    # --- Action guidance (shown early so agents see what to do first) ---
    print()
    has_only_additions = bool(si.new_since_last) and not si.resolved_since_last
    if "observe" not in stages and has_only_additions and meta.get("strategy_summary"):
        # Show both paths: accept or re-plan
        print(colorize("  Two paths available:", "yellow"))
        print()
        print(colorize("  To accept current queue (new items at end):", "cyan"))
        print(
            '    desloppify plan triage --confirm-existing '
            '--note "..." --strategy "same" --confirmed "I have reviewed..."'
        )
        print()
        print(colorize("  To re-prioritize and restructure:", "cyan"))
        print(f"    {TRIAGE_CMD_OBSERVE}")
    elif "observe" not in stages:
        print(colorize("  Next step:", "yellow"))
        print(f"    {TRIAGE_CMD_OBSERVE}")
        print(colorize("    (themes, root causes, contradictions between issues — NOT a list of IDs)", "dim"))
    elif "reflect" not in stages:
        print(colorize("  Next step: use the completed work and patterns below to write your reflect report.", "yellow"))
        print(f"    {TRIAGE_CMD_REFLECT}")
        print(colorize("    (Contradictions, recurring patterns, which direction to take, what to defer)", "dim"))
    elif "organize" not in stages:
        gaps = _unenriched_clusters(plan)
        manual = _manual_clusters_with_issues(plan)

        if not manual:
            print(colorize("  Next steps:", "yellow"))
            print("    0. Defer contradictory issues: `desloppify plan skip <hash>`")
            print(f"    1. Create clusters:  {TRIAGE_CMD_CLUSTER_CREATE}")
            print(f"    2. Add issues:     {TRIAGE_CMD_CLUSTER_ADD}")
            print(f"    3. Enrich clusters:  {TRIAGE_CMD_CLUSTER_STEPS}")
            print(f"    4. Record stage:     {TRIAGE_CMD_ORGANIZE}")
        elif gaps:
            print(colorize("  Enrich these clusters before recording organize:", "yellow"))
            for name, missing in gaps:
                print(colorize(f"    {name}: missing {', '.join(missing)}", "yellow"))
            print(colorize(
                f"    Fix: {TRIAGE_CMD_CLUSTER_ENRICH_COMPACT}",
                "dim",
            ))
            print(colorize(f"    Then: {TRIAGE_CMD_ORGANIZE}", "dim"))
        else:
            print(colorize("  All clusters enriched! Record the organize stage:", "green"))
            print(f"    {TRIAGE_CMD_ORGANIZE}")

        if meta.get("strategy_summary"):
            print()
            print(colorize("  Or fast-track (if existing plan is still valid):", "dim"))
            print(f"    {TRIAGE_CMD_CONFIRM_EXISTING}")
    else:
        print(colorize("  Ready to complete:", "green"))
        print(f"    {TRIAGE_CMD_COMPLETE_VERBOSE}")
        print(colorize('    (use --strategy "same" to keep existing strategy)', "dim"))

    # --- Prior stage reports (context for current action) ---
    if "observe" in stages:
        obs_report = stages["observe"].get("report", "")
        if obs_report:
            print(colorize("\n  Your observe analysis:", "dim"))
            for line in obs_report.strip().splitlines()[:8]:
                print(colorize(f"    {line}", "dim"))
            if len(obs_report.strip().splitlines()) > 8:
                print(colorize("    ...", "dim"))
    if "reflect" in stages:
        ref_report = stages["reflect"].get("report", "")
        if ref_report:
            print(colorize("\n  Your reflect strategy:", "dim"))
            for line in ref_report.strip().splitlines()[:8]:
                print(colorize(f"    {line}", "dim"))
            if len(ref_report.strip().splitlines()) > 8:
                print(colorize("    ...", "dim"))

    # --- Issues data ---
    # Group issues by dimension with suggestions to surface contradictions
    by_dim: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for fid, f in si.open_issues.items():
        detail = f.get("detail", {}) if isinstance(f.get("detail"), dict) else {}
        dim = detail.get("dimension", "unknown")
        by_dim[dim].append((fid, f))

    print(colorize("\n  Review issues by dimension:", "cyan"))
    print(colorize("  (Look for contradictions: issues in the same dimension that", "dim"))
    print(colorize("  recommend opposite changes. These must be resolved before clustering.)", "dim"))
    max_per_dim = 5
    for dim in sorted(by_dim, key=lambda d: (-len(by_dim[d]), d)):
        items = by_dim[dim]
        print(colorize(f"\n    {dim} ({len(items)}):", "bold"))
        for fid, f in items[:max_per_dim]:
            summary = f.get("summary", "")
            short = short_issue_id(fid)
            detail = f.get("detail", {}) if isinstance(f.get("detail"), dict) else {}
            suggestion = (detail.get("suggestion") or "")[:120]
            print(f"      [{short}] {summary}")
            if suggestion:
                print(colorize(f"        \u2192 {suggestion}", "dim"))
        if len(items) > max_per_dim:
            print(colorize(f"      ... and {len(items) - max_per_dim} more", "dim"))
    print(colorize("\n  Use hash in commands: desloppify plan skip <hash>  |  desloppify show <hash>", "dim"))

    # Show reflect dashboard when observe done, reflect not done
    if "observe" in stages and "reflect" not in stages:
        _print_reflect_dashboard(si, plan)

    # Show current cluster progress
    _print_progress(plan, si.open_issues)


# ---------------------------------------------------------------------------
# Confirmation helpers
# ---------------------------------------------------------------------------

def _find_cluster_for(fid: str, clusters: dict) -> str | None:
    """Return the cluster name containing *fid*, or None."""
    for name, c in clusters.items():
        if fid in c.get("issue_ids", []):
            return name
    return None


def _count_log_activity_since(plan: dict, since: str) -> dict[str, int]:
    """Count execution log entries by action since *since* timestamp."""
    counts: dict[str, int] = defaultdict(int)
    for entry in plan.get("execution_log", []):
        if entry.get("timestamp", "") >= since:
            counts[entry.get("action", "unknown")] += 1
    return dict(counts)


def _show_plan_summary(plan: dict, state: dict) -> None:
    """Print a compact plan rendering: clusters + queue order + coverage."""
    clusters = plan.get("clusters", {})
    active = {
        n: c for n, c in clusters.items()
        if c.get("issue_ids") and not c.get("auto")
    }
    issues = state.get("issues", {})

    if active:
        print(colorize(f"\n  Clusters ({len(active)}):", "bold"))
        for name, cluster in active.items():
            count = len(cluster.get("issue_ids", []))
            steps = len(cluster.get("action_steps", []))
            desc = (cluster.get("description") or "")[:60]
            print(f"    {name}: {count} items, {steps} steps — {desc}")

    queue_order = [
        fid for fid in plan.get("queue_order", [])
        if not fid.startswith("triage::") and not fid.startswith("workflow::")
    ]
    if queue_order:
        show = min(15, len(queue_order))
        print(colorize(f"\n  Queue order (first {show} of {len(queue_order)}):", "bold"))
        for i, fid in enumerate(queue_order[:show]):
            f = issues.get(fid, {})
            summary = (f.get("summary") or fid)[:60]
            detector = f.get("detector", "?")
            cn = _find_cluster_for(fid, active)
            print(f"    {i+1}. [{detector}] {summary}{f' ({cn})' if cn else ''}")

    organized, total, _ = _triage_coverage(
        plan, open_review_ids=_open_review_ids_from_state(state),
    )
    pct = int(organized / total * 100) if total else 0
    print(colorize(f"\n  Coverage: {organized}/{total} in clusters ({pct}%)", "bold"))


# ---------------------------------------------------------------------------
# Confirmation stage handlers
# ---------------------------------------------------------------------------

_MIN_ATTESTATION_LEN = 80


def _validate_attestation(
    attestation: str,
    stage: str,
    *,
    dimensions: list[str] | None = None,
    cluster_names: list[str] | None = None,
) -> str | None:
    """Return error message if attestation doesn't reference required data, else None."""
    text = attestation.lower()

    if stage == "observe":
        if dimensions:
            found = [d for d in dimensions if d.lower().replace("_", " ") in text or d.lower() in text]
            if not found:
                dim_list = ", ".join(dimensions[:6])
                return f"Attestation must reference at least one dimension from the summary. Mention one of: {dim_list}"

    elif stage == "reflect":
        refs: list[str] = []
        if dimensions:
            refs.extend(d for d in dimensions if d.lower().replace("_", " ") in text or d.lower() in text)
        if cluster_names:
            refs.extend(n for n in cluster_names if n.lower() in text)
        if not refs and (dimensions or cluster_names):
            return (
                f"Attestation must reference at least one dimension or cluster name.\n"
                f"  Valid dimensions: {', '.join((dimensions or [])[:6])}\n"
                f"  Valid clusters: {', '.join((cluster_names or [])[:6]) if cluster_names else '(none yet)'}"
            )

    elif stage == "organize":
        if cluster_names:
            found = [n for n in cluster_names if n.lower() in text]
            if not found:
                names = ", ".join(cluster_names[:6])
                return f"Attestation must reference at least one cluster from the plan. Mention one of: {names}"

    return None


def _confirm_observe(args: argparse.Namespace, plan: dict, stages: dict, attestation: str | None) -> None:
    """Show observe summary and record confirmation if attestation is valid."""
    if "observe" not in stages:
        print(colorize("  Cannot confirm: observe stage not recorded.", "red"))
        print(colorize('  Run: desloppify plan triage --stage observe --report "..."', "dim"))
        return
    if stages["observe"].get("confirmed_at"):
        print(colorize("  Observe stage already confirmed.", "green"))
        return

    # Show summary
    runtime = command_runtime(args)
    si = collect_triage_input(plan, runtime.state)
    obs = stages["observe"]

    print(colorize("  Stage: OBSERVE — Analyse issues & spot contradictions", "bold"))
    print(colorize("  " + "─" * 54, "dim"))

    # Dimension breakdown
    by_dim, dim_names = _observe_dimension_breakdown(si)

    issue_count = obs.get("issue_count", len(si.open_issues))
    print(f"  Your analysis covered {issue_count} issues across {len(by_dim)} dimensions:")
    for dim in dim_names:
        print(f"    {dim}: {by_dim[dim]} issues")

    cited = obs.get("cited_ids", [])
    if cited:
        print(f"  You cited {len(cited)} issue IDs in your report.")

    if not attestation or len(attestation.strip()) < _MIN_ATTESTATION_LEN:
        if attestation:
            print(colorize(
                f"\n  Attestation too short ({len(attestation.strip())} chars, min {_MIN_ATTESTATION_LEN}).",
                "red",
            ))
        print(colorize("\n  If satisfied, confirm:", "dim"))
        print(colorize('    desloppify plan triage --confirm observe --attestation "I have thoroughly reviewed..."', "dim"))
        print(colorize("  If not, continue reviewing issues before reflecting.", "dim"))
        return

    # Validate attestation references actual data
    validation_err = _validate_attestation(attestation.strip(), "observe", dimensions=dim_names)
    if validation_err:
        print(colorize(f"\n  {validation_err}", "red"))
        return

    # Record confirmation
    stages["observe"]["confirmed_at"] = utc_now()
    stages["observe"]["confirmed_text"] = attestation.strip()
    _purge_triage_stage(plan, "observe")
    save_plan(plan)
    append_log_entry(plan, "triage_confirm_observe", actor="user",
                     detail={"attestation": attestation.strip()})
    save_plan(plan)
    print(colorize(f'  ✓ Observe confirmed: "{attestation.strip()}"', "green"))


def _confirm_reflect(args: argparse.Namespace, plan: dict, stages: dict, attestation: str | None) -> None:
    """Show reflect summary and record confirmation if attestation is valid."""
    if "reflect" not in stages:
        print(colorize("  Cannot confirm: reflect stage not recorded.", "red"))
        print(colorize('  Run: desloppify plan triage --stage reflect --report "..."', "dim"))
        return
    if stages["reflect"].get("confirmed_at"):
        print(colorize("  Reflect stage already confirmed.", "green"))
        return

    runtime = command_runtime(args)
    si = collect_triage_input(plan, runtime.state)
    ref = stages["reflect"]

    print(colorize("  Stage: REFLECT — Form strategy & present to user", "bold"))
    print(colorize("  " + "─" * 50, "dim"))

    # Recurring dimensions
    recurring = detect_recurring_patterns(si.open_issues, si.resolved_issues)
    if recurring:
        print(f"  Your strategy identified {len(recurring)} recurring dimension(s):")
        for dim, info in sorted(recurring.items()):
            resolved_count = len(info["resolved"])
            open_count = len(info["open"])
            label = "potential loop" if open_count >= resolved_count else "root cause unaddressed"
            print(f"    {dim}: {resolved_count} resolved, {open_count} still open — {label}")
    else:
        print("  No recurring patterns detected.")

    # Strategy briefing excerpt
    report = ref.get("report", "")
    if report:
        print()
        print(colorize("  ┌─ Your strategy briefing ───────────────────────┐", "cyan"))
        for line in report.strip().splitlines()[:8]:
            print(colorize(f"  │ {line}", "cyan"))
        if len(report.strip().splitlines()) > 8:
            print(colorize("  │ ...", "cyan"))
        print(colorize("  └" + "─" * 51 + "┘", "cyan"))

    # Collect data references for validation — include observe-stage dimensions
    _by_dim, observe_dims = _observe_dimension_breakdown(si)
    reflect_dims = sorted(set((list(recurring.keys()) if recurring else []) + observe_dims))
    reflect_clusters = [n for n in plan.get("clusters", {}) if not plan["clusters"][n].get("auto")]

    if not attestation or len(attestation.strip()) < _MIN_ATTESTATION_LEN:
        if attestation:
            print(colorize(
                f"\n  Attestation too short ({len(attestation.strip())} chars, min {_MIN_ATTESTATION_LEN}).",
                "red",
            ))
        print(colorize("\n  If satisfied, confirm:", "dim"))
        print(colorize('    desloppify plan triage --confirm reflect --attestation "My strategy accounts for..."', "dim"))
        print(colorize("  If not, refine your strategy before organizing.", "dim"))
        return

    # Validate attestation references actual data
    validation_err = _validate_attestation(
        attestation.strip(), "reflect",
        dimensions=reflect_dims, cluster_names=reflect_clusters,
    )
    if validation_err:
        print(colorize(f"\n  {validation_err}", "red"))
        return

    stages["reflect"]["confirmed_at"] = utc_now()
    stages["reflect"]["confirmed_text"] = attestation.strip()
    _purge_triage_stage(plan, "reflect")
    save_plan(plan)
    append_log_entry(plan, "triage_confirm_reflect", actor="user",
                     detail={"attestation": attestation.strip()})
    save_plan(plan)
    print(colorize(f'  ✓ Reflect confirmed: "{attestation.strip()}"', "green"))


def _confirm_organize(args: argparse.Namespace, plan: dict, stages: dict, attestation: str | None) -> None:
    """Show full plan summary and record confirmation if attestation is valid."""
    if "organize" not in stages:
        print(colorize("  Cannot confirm: organize stage not recorded.", "red"))
        print(colorize('  Run: desloppify plan triage --stage organize --report "..."', "dim"))
        return
    if stages["organize"].get("confirmed_at"):
        print(colorize("  Organize stage already confirmed.", "green"))
        return

    runtime = command_runtime(args)
    state = runtime.state

    print(colorize("  Stage: ORGANIZE — Defer contradictions, cluster, & prioritize", "bold"))
    print(colorize("  " + "─" * 63, "dim"))

    # Activity since reflect
    reflect_ts = stages.get("reflect", {}).get("timestamp", "")
    if reflect_ts:
        activity = _count_log_activity_since(plan, reflect_ts)
        if activity:
            print("  Since reflect, you have:")
            for action, count in sorted(activity.items()):
                print(f"    {action}: {count}")
        else:
            print("  No logged plan operations since reflect.")

    # Show full plan
    print(colorize("\n  Plan:", "bold"))
    _show_plan_summary(plan, state)

    organize_clusters = [n for n in plan.get("clusters", {}) if not plan["clusters"][n].get("auto")]

    if not attestation or len(attestation.strip()) < _MIN_ATTESTATION_LEN:
        if attestation:
            print(colorize(
                f"\n  Attestation too short ({len(attestation.strip())} chars, min {_MIN_ATTESTATION_LEN}).",
                "red",
            ))
        print(colorize("\n  If satisfied, confirm:", "dim"))
        print(colorize('    desloppify plan triage --confirm organize --attestation "This plan is correct..."', "dim"))
        print(colorize("  If not, adjust clusters, priorities, or queue order before completing.", "dim"))
        return

    # Validate attestation references actual data
    validation_err = _validate_attestation(
        attestation.strip(), "organize", cluster_names=organize_clusters,
    )
    if validation_err:
        print(colorize(f"\n  {validation_err}", "red"))
        return

    organized, total, _ = _triage_coverage(
        plan, open_review_ids=_open_review_ids_from_state(state),
    )
    stages["organize"]["confirmed_at"] = utc_now()
    stages["organize"]["confirmed_text"] = attestation.strip()
    _purge_triage_stage(plan, "organize")
    save_plan(plan)
    append_log_entry(plan, "triage_confirm_organize", actor="user",
                     detail={
                         "attestation": attestation.strip(),
                         "coverage": f"{organized}/{total}",
                     })
    save_plan(plan)
    print(colorize(f'  ✓ Organize confirmed: "{attestation.strip()}"', "green"))


def _cmd_confirm_stage(args: argparse.Namespace) -> None:
    """Router for ``--confirm observe/reflect/organize``."""
    confirm_stage = getattr(args, "confirm", None)
    attestation = getattr(args, "attestation", None)
    plan = load_plan()
    meta = plan.get("epic_triage_meta", {})
    stages = meta.get("triage_stages", {})

    if confirm_stage == "observe":
        _confirm_observe(args, plan, stages, attestation)
    elif confirm_stage == "reflect":
        _confirm_reflect(args, plan, stages, attestation)
    elif confirm_stage == "organize":
        _confirm_organize(args, plan, stages, attestation)


# ---------------------------------------------------------------------------
# Start (manual trigger)
# ---------------------------------------------------------------------------

def _cmd_triage_start(args: argparse.Namespace) -> None:
    """Manually inject triage stage IDs into the queue and clear prior stages."""
    plan = load_plan()

    if _has_triage_in_queue(plan):
        print(colorize("  Planning mode stages are already in the queue.", "yellow"))
        meta = plan.get("epic_triage_meta", {})
        stages = meta.get("triage_stages", {})
        if stages:
            print(colorize(f"  {len(stages)} stage(s) in progress — clearing to restart.", "yellow"))
            meta["triage_stages"] = {}
            _inject_triage_stages(plan)
            save_plan(plan)
            append_log_entry(plan, "triage_start", actor="user",
                             detail={"action": "restart", "cleared_stages": list(stages.keys())})
            save_plan(plan)
            print(colorize("  Stages cleared. Begin with observe:", "green"))
        else:
            print(colorize("  Begin with observe:", "green"))
        print(colorize(f"    {TRIAGE_CMD_OBSERVE}", "dim"))
        return

    # Inject all 4 stage IDs
    _inject_triage_stages(plan)
    meta = plan.setdefault("epic_triage_meta", {})
    meta["triage_stages"] = {}
    save_plan(plan)

    append_log_entry(plan, "triage_start", actor="user",
                     detail={"action": "start"})
    save_plan(plan)

    runtime = command_runtime(args)
    si = collect_triage_input(plan, runtime.state)
    print(colorize("  Planning mode started (4 stages queued).", "green"))
    print(f"  Open review issues: {len(si.open_issues)}")
    print(colorize("  Begin with observe:", "dim"))
    print(colorize(f"    {TRIAGE_CMD_OBSERVE}", "dim"))


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def cmd_plan_triage(args: argparse.Namespace) -> None:
    """Run epic triage: staged workflow OBSERVE → REFLECT → ORGANIZE → COMMIT."""
    runtime = command_runtime(args)
    state = runtime.state
    if not require_completed_scan(state):
        return

    # Route: --start
    if getattr(args, "start", False):
        _cmd_triage_start(args)
        return

    # Route: --confirm observe/reflect/organize
    if getattr(args, "confirm", None):
        _cmd_confirm_stage(args)
        return

    # Route: --complete
    if getattr(args, "complete", False):
        _cmd_triage_complete(args)
        return

    # Route: --confirm-existing
    if getattr(args, "confirm_existing", False):
        _cmd_confirm_existing(args)
        return

    # Route: --stage observe/reflect/organize
    stage = getattr(args, "stage", None)
    if stage == "observe":
        _cmd_stage_observe(args)
        return
    if stage == "reflect":
        _cmd_stage_reflect(args)
        return
    if stage == "organize":
        _cmd_stage_organize(args)
        return

    # Dry-run mode
    if getattr(args, "dry_run", False):
        plan = load_plan()
        si = collect_triage_input(plan, state)
        prompt = build_triage_prompt(si)
        print(colorize("  Epic triage \u2014 dry run", "bold"))
        print(colorize("  " + "\u2500" * 60, "dim"))
        print(f"  Open review issues: {len(si.open_issues)}")
        print(f"  Existing epics: {len(si.existing_epics)}")
        print(f"  New since last: {len(si.new_since_last)}")
        print(f"  Resolved since last: {len(si.resolved_since_last)}")
        print(colorize("\n  Prompt that would be sent to LLM:", "dim"))
        print()
        print(prompt)
        return

    # Default: dashboard
    _cmd_triage_dashboard(args)


cmd_stage_observe = _cmd_stage_observe

__all__ = ["cmd_plan_triage", "cmd_stage_observe"]
