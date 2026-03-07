"""Display and dashboard rendering for plan triage."""

from __future__ import annotations

import argparse
from collections import defaultdict

from desloppify.app.commands.helpers.display import short_issue_id
from desloppify.app.commands.plan.triage_playbook import (
    TRIAGE_CMD_CLUSTER_ADD,
    TRIAGE_CMD_CLUSTER_CREATE,
    TRIAGE_CMD_CLUSTER_ENRICH_COMPACT,
    TRIAGE_CMD_CLUSTER_STEPS,
    TRIAGE_CMD_COMPLETE_VERBOSE,
    TRIAGE_CMD_CONFIRM_EXISTING,
    TRIAGE_CMD_ENRICH,
    TRIAGE_CMD_OBSERVE,
    TRIAGE_CMD_ORGANIZE,
    TRIAGE_CMD_REFLECT,
    TRIAGE_STAGE_DEPENDENCIES,
    TRIAGE_STAGE_LABELS,
)
from desloppify.base.output.terminal import colorize
from desloppify.base.output.user_message import print_user_message

from .helpers import (
    find_cluster_for,
    manual_clusters_with_issues,
    open_review_ids_from_state,
    print_cascade_clear_feedback,
    triage_coverage,
)
from .services import TriageServices, default_triage_services
from .stage_helpers import _unenriched_clusters


def print_stage_progress(stages: dict, plan: dict | None = None) -> None:
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
        manual = manual_clusters_with_issues(plan)
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

def print_progress(plan: dict, open_issues: dict) -> None:
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
    """Print the reflect stage output including briefing box and next steps."""
    print(colorize(
        f"  Reflect stage recorded: {issue_count} issues, "
        f"{len(recurring_dims)} recurring dimension(s).",
        "green",
    ))
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
            print(colorize(
                f"    {dim}: {len(info['resolved'])} resolved, {len(info['open'])} still open",
                "dim",
            ))

    print()
    print(colorize("  \u250c\u2500 Strategic briefing (share with user before organizing) \u2500\u2510", "cyan"))
    for line in report.strip().splitlines():
        print(colorize(f"  \u2502 {line}", "cyan"))
    print(colorize("  \u2514" + "\u2500" * 57 + "\u2518", "cyan"))
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
    """Print the organize stage output including cluster summary and next steps."""
    print(colorize(
        f"  Organize stage recorded: {len(manual_clusters)} enriched cluster(s).",
        "green",
    ))
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
        desc_str = f" \u2014 {desc}" if desc else ""
        print(colorize(f"    {name}: {len(cluster.get('issue_ids', []))} issues, {len(steps)} steps{desc_str}", "dim"))

    print()
    print(colorize("  \u250c\u2500 Prioritized organization (share with user) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510", "cyan"))
    for line in report.strip().splitlines():
        print(colorize(f"  \u2502 {line}", "cyan"))
    print(colorize("  \u2514" + "\u2500" * 57 + "\u2518", "cyan"))
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

    recurring = resolved_services.detect_recurring_patterns(open_issues, resolved)
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

def _print_dashboard_header(si: object, stages: dict, meta: dict, plan: dict) -> None:
    """Print the header section: title, open issues count, stage progress, overall status."""
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
    print_stage_progress(stages, plan)
    if meta.get("stage_refresh_required"):
        print(
            colorize(
                "  Note: review issues changed since stage progress started; "
                "refresh stage reports before completion.",
                "yellow",
            )
        )


def _print_action_guidance(stages: dict, meta: dict, si: object, plan: dict) -> None:
    """Print the 'What to do' action guidance section based on current stage."""
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
        manual = manual_clusters_with_issues(plan)

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
    elif "enrich" not in stages:
        shallow = _unenriched_clusters(plan)
        if shallow:
            print(colorize("  Next step: enrich steps with detail and issue_refs.", "yellow"))
            print(colorize('    desloppify plan cluster update <name> --update-step N --detail "sub-details"', "dim"))
        else:
            print(colorize("  Steps look enriched. Record the enrich stage:", "green"))
        print(f"    {TRIAGE_CMD_ENRICH}")
        print(colorize("  You can still reorganize: add/remove clusters, reorder items.", "dim"))
    else:
        print(colorize("  Ready to complete:", "green"))
        print(f"    {TRIAGE_CMD_COMPLETE_VERBOSE}")
        print(colorize('    (use --strategy "same" to keep existing strategy)', "dim"))


def _print_prior_stage_reports(stages: dict) -> None:
    """Print prior stage reports (observe/reflect) as context for current action."""
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


def _print_issues_by_dimension(open_issues: dict) -> None:
    """Print issues grouped by dimension with suggestions to surface contradictions."""
    by_dim: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for fid, f in open_issues.items():
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

    # Show reflect dashboard when observe done, reflect not done
    if "observe" in stages and "reflect" not in stages:
        print_reflect_dashboard(si, plan, services=resolved_services)

    # Show current cluster progress
    print_progress(plan, si.open_issues)

def show_plan_summary(plan: dict, state: dict) -> None:
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
            cn = find_cluster_for(fid, active)
            print(f"    {i+1}. [{detector}] {summary}{f' ({cn})' if cn else ''}")

    organized, total, _ = triage_coverage(
        plan, open_review_ids=open_review_ids_from_state(state),
    )
    pct = int(organized / total * 100) if total else 0
    print(colorize(f"\n  Coverage: {organized}/{total} in clusters ({pct}%)", "bold"))

__all__ = [
    "cmd_triage_dashboard",
    "print_organize_result",
    "print_progress",
    "print_reflect_dashboard",
    "print_reflect_result",
    "print_stage_progress",
    "show_plan_summary",
]
