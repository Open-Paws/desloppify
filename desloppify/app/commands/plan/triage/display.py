"""Display and dashboard rendering for plan triage."""

from __future__ import annotations

import argparse
from collections import defaultdict

from desloppify.app.commands.helpers.display import short_issue_id
from desloppify.engine._plan.triage_playbook import (
    TRIAGE_CMD_CLUSTER_ENRICH_COMPACT,
    TRIAGE_STAGE_DEPENDENCIES,
    TRIAGE_STAGE_LABELS,
)
from desloppify.base.output.terminal import colorize
from desloppify.base.output.user_message import print_user_message

from .display_layout import print_action_guidance as _print_action_guidance_impl
from .display_layout import print_dashboard_header as _print_dashboard_header_impl
from .display_layout import print_issues_by_dimension as _print_issues_by_dimension_impl
from .display_layout import print_prior_stage_reports as _print_prior_stage_reports_impl
from .display_layout import show_plan_summary as _show_plan_summary_impl
from .helpers import (
    find_cluster_for,
    manual_clusters_with_issues,
    open_review_ids_from_state,
    print_cascade_clear_feedback,
    triage_coverage,
)
from .services import TriageServices, default_triage_services
from .stage_helpers import unenriched_clusters


def print_stage_progress(stages: dict, plan: dict | None = None) -> None:
    """Print the stage progress indicator."""
    print(colorize("  Stages:", "dim"))
    for stage_name, label in TRIAGE_STAGE_LABELS:
        if stage_name in stages:
            if stages[stage_name].get("confirmed_at"):
                print(colorize(f"    ✓ {label} (confirmed)", "green"))
            else:
                print(colorize(f"    ✓ {label} (needs confirm)", "yellow"))
        elif TRIAGE_STAGE_DEPENDENCIES[stage_name].issubset(stages):
            print(colorize(f"    → {label} (current)", "yellow"))
        else:
            print(colorize(f"    ○ {label}", "dim"))

    if plan and "reflect" in stages and "organize" not in stages:
        gaps = unenriched_clusters(plan)
        manual = manual_clusters_with_issues(plan)
        if not manual:
            print(colorize("\n    No manual clusters yet. Create clusters and enrich them.", "yellow"))
        elif gaps:
            print(colorize(f"\n    {len(gaps)} cluster(s) need enrichment:", "yellow"))
            for name, missing in gaps:
                print(colorize(f"      {name}: missing {', '.join(missing)}", "yellow"))
            print(colorize(f"      Fix: {TRIAGE_CMD_CLUSTER_ENRICH_COMPACT}", "dim"))
        else:
            print(colorize(f"\n    All {len(manual)} manual cluster(s) enriched.", "green"))


def print_progress(plan: dict, open_issues: dict) -> None:
    """Show cluster state and unclustered issues."""
    clusters = plan.get("clusters", {})
    active_clusters = {name: c for name, c in clusters.items() if c.get("issue_ids")}
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
            elif not auto:
                tags.append("no steps")
            tag_str = f" [{', '.join(tags)}]"
            desc_str = f" — {desc}" if desc else ""
            print(f"    {name}: {count} items{tag_str}{desc_str}")

    all_clustered: set[str] = set()
    for cluster in clusters.values():
        all_clustered.update(cluster.get("issue_ids", []))
    unclustered = [fid for fid in open_issues if fid not in all_clustered]
    if unclustered:
        print(colorize(f"\n  {len(unclustered)} issues not yet in a cluster:", "yellow"))
        for fid in unclustered[:10]:
            issue = open_issues[fid]
            dim = (issue.get("detail", {}) or {}).get("dimension", "") if isinstance(issue.get("detail"), dict) else ""
            short = short_issue_id(fid)
            print(f"    [{short}] [{dim}] {issue.get('summary', '')}")
        if len(unclustered) > 10:
            print(colorize(f"    ... and {len(unclustered) - 10} more", "dim"))
    elif open_issues:
        organized, total, _ = triage_coverage(plan, open_review_ids=set(open_issues.keys()))
        print(colorize(f"\n  All {organized}/{total} issues are in clusters.", "green"))


def print_reflect_result(
    *,
    issue_count: int,
    recurring_dims: list[str],
    recurring: dict,
    report: str,
    is_reuse: bool,
    cleared: list,
    stages: dict,
) -> None:
    """Print reflect stage output including briefing box and next steps."""
    print(colorize(f"  Reflect stage recorded: {issue_count} issues, {len(recurring_dims)} recurring dimension(s).", "green"))
    if is_reuse:
        print(colorize("  Reflect data preserved (no changes).", "dim"))
        if cleared:
            print_cascade_clear_feedback(cleared, stages)
    else:
        print(colorize("  Now confirm your strategy.", "yellow"))
        print(colorize("    desloppify plan triage --confirm reflect", "dim"))
    if recurring_dims:
        for dim in recurring_dims:
            info = recurring[dim]
            print(colorize(f"    {dim}: {len(info['resolved'])} resolved, {len(info['open'])} still open", "dim"))

    print()
    print(colorize("  ┌─ Strategic briefing (share with user before organizing) ─┐", "cyan"))
    for line in report.strip().splitlines():
        print(colorize(f"  │ {line}", "cyan"))
    print(colorize("  └" + "─" * 57 + "┘", "cyan"))
    print_user_message(
        "Reflect recorded. Before confirming — check the"
        " subagent's report. Is it a strategy or just observe"
        " restated? It should include a concrete cluster"
        " blueprint: which clusters, which issues, what to skip"
        " (with per-issue reasons). Confirm when the blueprint"
        " is specific enough for organize to execute mechanically."
    )


def print_organize_result(
    *,
    manual_clusters: list[str],
    plan: dict,
    report: str,
    is_reuse: bool,
    cleared: list,
    stages: dict,
) -> None:
    """Print organize stage output including cluster summary and next steps."""
    print(colorize(f"  Organize stage recorded: {len(manual_clusters)} enriched cluster(s).", "green"))
    if is_reuse:
        print(colorize("  Organize data preserved (no changes).", "dim"))
        if cleared:
            print_cascade_clear_feedback(cleared, stages)
    else:
        print(colorize("  Now confirm the plan.", "yellow"))
        print(colorize("    desloppify plan triage --confirm organize", "dim"))
    for name in manual_clusters:
        cluster = plan.get("clusters", {}).get(name, {})
        steps = cluster.get("action_steps", [])
        desc = cluster.get("description", "")
        desc_str = f" — {desc}" if desc else ""
        print(colorize(f"    {name}: {len(cluster.get('issue_ids', []))} issues, {len(steps)} steps{desc_str}", "dim"))

    print()
    print(colorize("  ┌─ Prioritized organization (share with user) ────────────┐", "cyan"))
    for line in report.strip().splitlines():
        print(colorize(f"  │ {line}", "cyan"))
    print(colorize("  └" + "─" * 57 + "┘", "cyan"))
    print_user_message(
        "Organize recorded. Before confirming — does the"
        " organize output match the reflect blueprint? Clusters"
        " by file area (same PR), not by theme? Step count <"
        " issue count (consolidated)? Cluster names describe"
        " locations, not problem types? This should read like"
        " a set of PR plans."
    )


def print_reflect_dashboard(
    si: object,
    plan: dict,
    *,
    services: TriageServices | None = None,
) -> None:
    """Show completed clusters, resolved issues, and recurring patterns."""
    resolved_services = services or default_triage_services()
    completed = getattr(si, "completed_clusters", [])
    resolved = getattr(si, "resolved_issues", {})
    open_issues = getattr(si, "open_issues", {})

    if completed:
        print(colorize("\n  Previously completed clusters:", "cyan"))
        for cluster in completed[:10]:
            name = cluster.get("name", "?")
            count = len(cluster.get("issue_ids", []))
            thesis = cluster.get("thesis", "")
            print(f"    {name}: {count} issues")
            if thesis:
                print(colorize(f"      {thesis}", "dim"))
            for step in cluster.get("action_steps", [])[:3]:
                print(colorize(f"      - {step}", "dim"))
        if len(completed) > 10:
            print(colorize(f"    ... and {len(completed) - 10} more", "dim"))

    if resolved:
        print(colorize(f"\n  Resolved issues since last triage: {len(resolved)}", "cyan"))
        for fid, issue in sorted(resolved.items())[:10]:
            status = issue.get("status", "")
            summary = issue.get("summary", "")
            detail = issue.get("detail", {}) if isinstance(issue.get("detail"), dict) else {}
            dim = detail.get("dimension", "")
            print(f"    [{status}] [{dim}] {summary}")
            print(colorize(f"      {fid}", "dim"))
        if len(resolved) > 10:
            print(colorize(f"    ... and {len(resolved) - 10} more", "dim"))

    recurring = resolved_services.detect_recurring_patterns(open_issues, resolved)
    if recurring:
        print(colorize("\n  Recurring patterns detected:", "yellow"))
        for dim, info in sorted(recurring.items()):
            resolved_count = len(info["resolved"])
            open_count = len(info["open"])
            label = "potential loop" if open_count >= resolved_count else "root cause unaddressed"
            print(colorize(f"    {dim}: {resolved_count} resolved, {open_count} still open — {label}", "yellow"))
    elif not completed and not resolved:
        print(colorize("\n  First triage — no prior work to compare against.", "dim"))
        print(colorize("  Focus your reflect report on your strategy:", "yellow"))
        print(colorize("  - How will you resolve contradictions you identified in observe?", "dim"))
        print(colorize("  - Which issues will you cluster together vs defer?", "dim"))
        print(colorize("  - What's the overall arc of work and why?", "dim"))


def _print_dashboard_header(si: object, stages: dict, meta: dict, plan: dict) -> None:
    _print_dashboard_header_impl(si, stages, meta, plan)


def _print_action_guidance(stages: dict, meta: dict, si: object, plan: dict) -> None:
    _print_action_guidance_impl(stages, meta, si, plan)


def _print_prior_stage_reports(stages: dict) -> None:
    _print_prior_stage_reports_impl(stages)


def _print_issues_by_dimension(open_issues: dict) -> None:
    _print_issues_by_dimension_impl(open_issues)


def cmd_triage_dashboard(
    args: argparse.Namespace,
    *,
    services: TriageServices | None = None,
) -> None:
    """Default view: show issues, stage progress, and next command."""
    resolved_services = services or default_triage_services()
    runtime = resolved_services.command_runtime(args)
    state = runtime.state
    plan = resolved_services.load_plan()
    si = resolved_services.collect_triage_input(plan, state)
    meta = plan.get("epic_triage_meta", {})
    stages = meta.get("triage_stages", {})

    _print_dashboard_header(si, stages, meta, plan)
    _print_action_guidance(stages, meta, si, plan)
    _print_prior_stage_reports(stages)
    _print_issues_by_dimension(si.open_issues)

    if "observe" in stages and "reflect" not in stages:
        print_reflect_dashboard(si, plan, services=resolved_services)

    print_progress(plan, si.open_issues)


def show_plan_summary(plan: dict, state: dict) -> None:
    _show_plan_summary_impl(plan, state)


__all__ = [
    "cmd_triage_dashboard",
    "print_organize_result",
    "print_progress",
    "print_reflect_dashboard",
    "print_reflect_result",
    "print_stage_progress",
    "show_plan_summary",
]
