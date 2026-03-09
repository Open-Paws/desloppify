"""Progress rendering helpers for triage command handlers."""

from __future__ import annotations

from desloppify.app.commands.helpers.display import short_issue_id
from desloppify.app.commands.plan.triage.helpers import manual_clusters_with_issues
from desloppify.app.commands.plan.triage.stage_helpers import (
    triage_coverage,
    unenriched_clusters,
)
from desloppify.engine._plan.triage_playbook import (
    TRIAGE_CMD_CLUSTER_ENRICH_COMPACT,
    TRIAGE_STAGE_DEPENDENCIES,
    TRIAGE_STAGE_LABELS,
)
from desloppify.base.output.terminal import colorize


def _print_stage_progress(stages: dict, plan: dict | None = None) -> None:
    """Print the 4-stage progress indicator."""
    print(colorize("  Stages:", "dim"))
    for stage_name, label in TRIAGE_STAGE_LABELS:
        if stage_name in stages:
            print(colorize(f"    \u2713 {label}", "green"))
        elif TRIAGE_STAGE_DEPENDENCIES[stage_name].issubset(stages):
            print(colorize(f"    \u2192 {label} (current)", "yellow"))
        else:
            print(colorize(f"    \u25cb {label}", "dim"))

    if plan and "reflect" in stages and "organize" not in stages:
        gaps = unenriched_clusters(plan)
        manual = manual_clusters_with_issues(plan)
        if not manual:
            print(
                colorize(
                    "\n    No manual clusters yet. Create clusters and enrich them.",
                    "yellow",
                )
            )
        elif gaps:
            print(colorize(f"\n    {len(gaps)} cluster(s) need enrichment:", "yellow"))
            for name, missing in gaps:
                print(colorize(f"      {name}: missing {', '.join(missing)}", "yellow"))
            print(
                colorize(
                    f"      Fix: {TRIAGE_CMD_CLUSTER_ENRICH_COMPACT}",
                    "dim",
                )
            )
        else:
            print(colorize(f"\n    All {len(manual)} manual cluster(s) enriched.", "green"))


def _print_progress(plan: dict, open_issues: dict) -> None:
    """Show cluster state and unclustered issues."""
    clusters = plan.get("clusters", {})
    _print_active_clusters(clusters)
    unclustered = _collect_unclustered_issues(clusters, open_issues)
    _print_unclustered_issues(plan, open_issues, unclustered)


def _print_active_clusters(clusters: dict[str, dict]) -> None:
    """Print current clusters that contain issues."""
    active_clusters = {name: cluster for name, cluster in clusters.items() if cluster.get("issue_ids")}
    if not active_clusters:
        return
    print(colorize("\n  Current clusters:", "cyan"))
    for name, cluster in active_clusters.items():
        count = len(cluster.get("issue_ids", []))
        desc = cluster.get("description") or ""
        tag_str = _cluster_tag_summary(cluster)
        desc_str = f" \u2014 {desc}" if desc else ""
        print(f"    {name}: {count} items{tag_str}{desc_str}")


def _cluster_tag_summary(cluster: dict) -> str:
    """Build compact tag summary for one cluster row."""
    steps = cluster.get("action_steps", [])
    auto = cluster.get("auto", False)
    tags: list[str] = []
    tags.append("auto" if auto else "manual")
    tags.append("desc" if cluster.get("description") else "no desc")
    if steps:
        tags.append(f"{len(steps)} steps")
    elif not auto:
        tags.append("no steps")
    return f" [{', '.join(tags)}]"


def _collect_unclustered_issues(clusters: dict[str, dict], open_issues: dict) -> list[str]:
    """Return issue IDs that are not attached to any cluster."""
    all_clustered: set[str] = set()
    for cluster in clusters.values():
        all_clustered.update(cluster.get("issue_ids", []))
    return [issue_id for issue_id in open_issues if issue_id not in all_clustered]


def _print_unclustered_issues(
    plan: dict,
    open_issues: dict,
    unclustered: list[str],
) -> None:
    """Print unclustered issues summary or all-clustered confirmation."""
    if unclustered:
        print(colorize(f"\n  {len(unclustered)} issues not yet in a cluster:", "yellow"))
        for issue_id in unclustered[:10]:
            issue = open_issues[issue_id]
            dim = (
                (issue.get("detail", {}) or {}).get("dimension", "")
                if isinstance(issue.get("detail"), dict)
                else ""
            )
            short = short_issue_id(issue_id)
            print(f"    [{short}] [{dim}] {issue.get('summary', '')}")
        if len(unclustered) > 10:
            print(colorize(f"    ... and {len(unclustered) - 10} more", "dim"))
        return
    if open_issues:
        organized, total, _ = triage_coverage(plan)
        print(colorize(f"\n  All {organized}/{total} issues are in clusters.", "green"))
