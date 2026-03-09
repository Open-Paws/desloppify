"""Layout-oriented triage dashboard rendering helpers."""

from __future__ import annotations

from collections import defaultdict

from desloppify.app.commands.helpers.display import short_issue_id
from desloppify.engine._plan.triage_playbook import (
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
)
from desloppify.base.output.terminal import colorize

from .helpers import find_cluster_for, manual_clusters_with_issues, open_review_ids_from_state, triage_coverage
from .stage_helpers import unenriched_clusters


def print_dashboard_header(si: object, stages: dict, meta: dict, plan: dict) -> None:
    """Print the header section: title, open issues count, stage progress, overall status."""
    from . import display as display_mod  # noqa: PLC0415

    print(colorize("  Epic triage — manual", "bold"))
    print(colorize("  " + "─" * 60, "dim"))
    print(f"  Open review issues: {len(si.open_issues)}")
    print(colorize("  Goal: identify contradictions, resolve them, then group the coherent", "cyan"))
    print(colorize("  remainder into clusters by root cause with action steps and priorities.", "cyan"))
    if si.existing_epics:
        print(f"  Existing epics: {len(si.existing_epics)}")
    if si.new_since_last:
        print(colorize(f"  New since last triage: {len(si.new_since_last)}", "yellow"))
        for fid in sorted(si.new_since_last):
            issue = si.open_issues.get(fid, {})
            dim = ""
            detail = issue.get("detail")
            if isinstance(detail, dict):
                dim = detail.get("dimension", "")
            dim_tag = f" ({dim})" if dim else ""
            print(colorize(f"    * [{short_issue_id(fid)}] {issue.get('summary', '')}{dim_tag}", "yellow"))
    if si.resolved_since_last:
        print(f"  Resolved since last triage: {len(si.resolved_since_last)}")

    print()
    display_mod.print_stage_progress(stages, plan)
    if meta.get("stage_refresh_required"):
        print(
            colorize(
                "  Note: review issues changed since stage progress started; "
                "refresh stage reports before completion.",
                "yellow",
            )
        )


def print_action_guidance(stages: dict, meta: dict, si: object, plan: dict) -> None:
    """Print the 'What to do' action guidance section based on current stage."""
    print()
    has_only_additions = bool(si.new_since_last) and not si.resolved_since_last
    if "observe" not in stages and has_only_additions and meta.get("strategy_summary"):
        print(colorize("  Two paths available:", "yellow"))
        print()
        print(colorize("  To accept current queue (new items at end):", "cyan"))
        print('    desloppify plan triage --confirm-existing --note "..." --strategy "same" --confirmed "I have reviewed..."')
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
        gaps = unenriched_clusters(plan)
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
            print(colorize(f"    Fix: {TRIAGE_CMD_CLUSTER_ENRICH_COMPACT}", "dim"))
            print(colorize(f"    Then: {TRIAGE_CMD_ORGANIZE}", "dim"))
        else:
            print(colorize("  All clusters enriched! Record the organize stage:", "green"))
            print(f"    {TRIAGE_CMD_ORGANIZE}")

        if meta.get("strategy_summary"):
            print()
            print(colorize("  Or fast-track (if existing plan is still valid):", "dim"))
            print(f"    {TRIAGE_CMD_CONFIRM_EXISTING}")
    elif "enrich" not in stages:
        shallow = unenriched_clusters(plan)
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


def print_prior_stage_reports(stages: dict) -> None:
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


def print_issues_by_dimension(open_issues: dict) -> None:
    """Print issues grouped by dimension with suggestions to surface contradictions."""
    by_dim: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for fid, issue in open_issues.items():
        detail = issue.get("detail", {}) if isinstance(issue.get("detail"), dict) else {}
        dim = detail.get("dimension", "unknown")
        by_dim[dim].append((fid, issue))

    print(colorize("\n  Review issues by dimension:", "cyan"))
    print(colorize("  (Look for contradictions: issues in the same dimension that", "dim"))
    print(colorize("  recommend opposite changes. These must be resolved before clustering.)", "dim"))
    max_per_dim = 5
    for dim in sorted(by_dim, key=lambda d: (-len(by_dim[d]), d)):
        items = by_dim[dim]
        print(colorize(f"\n    {dim} ({len(items)}):", "bold"))
        for fid, issue in items[:max_per_dim]:
            summary = issue.get("summary", "")
            short = short_issue_id(fid)
            detail = issue.get("detail", {}) if isinstance(issue.get("detail"), dict) else {}
            suggestion = (detail.get("suggestion") or "")[:120]
            print(f"      [{short}] {summary}")
            if suggestion:
                print(colorize(f"        → {suggestion}", "dim"))
        if len(items) > max_per_dim:
            print(colorize(f"      ... and {len(items) - max_per_dim} more", "dim"))
    print(colorize("\n  Use hash in commands: desloppify plan skip <hash>  |  desloppify show <hash>", "dim"))


def show_plan_summary(plan: dict, state: dict) -> None:
    """Print a compact plan rendering: clusters + queue order + coverage."""
    clusters = plan.get("clusters", {})
    active = {name: cluster for name, cluster in clusters.items() if cluster.get("issue_ids") and not cluster.get("auto")}
    issues = state.get("issues", {})

    if active:
        print(colorize(f"\n  Clusters ({len(active)}):", "bold"))
        for name, cluster in active.items():
            count = len(cluster.get("issue_ids", []))
            steps = len(cluster.get("action_steps", []))
            desc = (cluster.get("description") or "")[:60]
            print(f"    {name}: {count} items, {steps} steps — {desc}")

    queue_order = [
        fid
        for fid in plan.get("queue_order", [])
        if not fid.startswith("triage::") and not fid.startswith("workflow::")
    ]
    if queue_order:
        show = min(15, len(queue_order))
        print(colorize(f"\n  Queue order (first {show} of {len(queue_order)}):", "bold"))
        for i, fid in enumerate(queue_order[:show]):
            issue = issues.get(fid, {})
            summary = (issue.get("summary") or fid)[:60]
            detector = issue.get("detector", "?")
            cluster_name = find_cluster_for(fid, active)
            print(f"    {i + 1}. [{detector}] {summary}{f' ({cluster_name})' if cluster_name else ''}")

    organized, total, _ = triage_coverage(plan, open_review_ids=open_review_ids_from_state(state))
    pct = int(organized / total * 100) if total else 0
    print(colorize(f"\n  Coverage: {organized}/{total} in clusters ({pct}%)", "bold"))


__all__ = [
    "print_action_guidance",
    "print_dashboard_header",
    "print_issues_by_dimension",
    "print_prior_stage_reports",
    "show_plan_summary",
]
