"""Section render helpers for markdown planning output."""

from __future__ import annotations

from collections import defaultdict


def summary_lines(stats: dict) -> list[str]:
    open_count = stats.get("open", 0)
    total_issues = sum(
        stats.get(key, 0) for key in ("open", "fixed", "wontfix", "auto_resolved")
    )
    addressed = total_issues - open_count
    pct = round(addressed / total_issues * 100) if total_issues else 100
    return [
        f"- **{open_count} open** / {total_issues} total ({pct}% addressed)",
        "",
    ]


def addressed_section(issues: dict) -> list[str]:
    addressed = [issue for issue in issues.values() if issue["status"] != "open"]
    if not addressed:
        return []

    lines: list[str] = ["---", "## Addressed", ""]
    by_status: dict[str, int] = defaultdict(int)
    for issue in addressed:
        by_status[issue["status"]] += 1
    for status, count in sorted(by_status.items()):
        lines.append(f"- **{status}**: {count}")

    wontfix = [
        issue
        for issue in addressed
        if issue["status"] == "wontfix" and issue.get("note")
    ]
    if wontfix:
        lines.extend(["", "### Wontfix (with explanations)", ""])
        for issue in wontfix[:30]:
            lines.append(f"- `{issue['id']}` — {issue['note']}")
    lines.append("")
    return lines


def render_plan_item(item: dict, override: dict) -> list[str]:
    """Render a single plan item as markdown lines."""
    confidence = item.get("confidence", "medium")
    summary = item.get("summary", "")
    item_id = item.get("id", "")

    lines = [f"- [ ] [{confidence}] {summary}"]
    description = override.get("description")
    if description:
        lines.append(f"      → {description}")
    lines.append(f"      `{item_id}`")
    note = override.get("note")
    if note:
        lines.append(f"      Note: {note}")
    return lines


def plan_user_ordered_section(
    items: list[dict],
    plan: dict,
) -> list[str]:
    """Render the user-ordered queue section, grouped by cluster."""
    queue_order: list[str] = plan.get("queue_order", [])
    skipped_ids: set[str] = set(plan.get("skipped", {}).keys())
    overrides: dict = plan.get("overrides", {})
    clusters: dict = plan.get("clusters", {})

    ordered_ids = set(queue_order) - skipped_ids
    if not ordered_ids:
        return []

    by_id = {item.get("id"): item for item in items}
    lines: list[str] = [
        "---",
        f"## User-Ordered Queue ({len(ordered_ids)} items)",
        "",
    ]

    emitted: set[str] = set()
    for cluster_name, cluster in clusters.items():
        member_ids = [
            issue_id
            for issue_id in cluster.get("issue_ids", [])
            if issue_id in ordered_ids and issue_id in by_id
        ]
        if not member_ids:
            continue
        desc = cluster.get("description") or ""
        lines.append(f"### Cluster: {cluster_name}")
        if desc:
            lines.append(f"> {desc}")
        lines.append("")
        for issue_id in member_ids:
            item = by_id.get(issue_id)
            if item:
                lines.extend(render_plan_item(item, overrides.get(issue_id, {})))
                emitted.add(issue_id)
        lines.append("")

    unclustered = [
        issue_id
        for issue_id in queue_order
        if issue_id in ordered_ids and issue_id not in emitted and issue_id in by_id
    ]
    if unclustered:
        if any(cluster.get("issue_ids") for cluster in clusters.values()):
            lines.append("### (unclustered ordered items)")
            lines.append("")
        for issue_id in unclustered:
            item = by_id.get(issue_id)
            if item:
                lines.extend(render_plan_item(item, overrides.get(issue_id, {})))
        lines.append("")
    return lines


def plan_skipped_section(items: list[dict], plan: dict) -> list[str]:
    """Render the skipped items section, grouped by kind."""
    skipped = plan.get("skipped", {})
    if not skipped:
        return []

    by_id = {item.get("id"): item for item in items}
    overrides = plan.get("overrides", {})

    by_kind: dict[str, list[str]] = {"temporary": [], "permanent": [], "false_positive": []}
    for issue_id, entry in skipped.items():
        kind = entry.get("kind", "temporary")
        by_kind.setdefault(kind, []).append(issue_id)

    kind_labels = {
        "temporary": "Skipped Temporarily",
        "permanent": "Wontfix (permanent)",
        "false_positive": "False Positives",
    }

    lines: list[str] = [
        "---",
        f"## Skipped ({len(skipped)} items)",
        "",
    ]

    for kind in ("temporary", "permanent", "false_positive"):
        ids = by_kind.get(kind, [])
        if not ids:
            continue
        lines.append(f"### {kind_labels[kind]} ({len(ids)})")
        lines.append("")
        for issue_id in ids:
            entry = skipped.get(issue_id, {})
            item = by_id.get(issue_id)
            if item:
                lines.extend(render_plan_item(item, overrides.get(issue_id, {})))
            else:
                lines.append(f"- ~~{issue_id}~~ (not in current queue)")
            reason = entry.get("reason")
            if reason:
                lines.append(f"      Reason: {reason}")
            note = entry.get("note")
            if note and not overrides.get(issue_id, {}).get("note"):
                lines.append(f"      Note: {note}")
            review_after = entry.get("review_after")
            if review_after:
                skipped_at = entry.get("skipped_at_scan", 0)
                lines.append(f"      Review after: scan {skipped_at + review_after}")
        lines.append("")
    return lines


def plan_superseded_section(plan: dict) -> list[str]:
    """Render the superseded items section."""
    superseded = plan.get("superseded", {})
    if not superseded:
        return []

    lines: list[str] = [
        "---",
        f"## Superseded ({len(superseded)} items — may need remap)",
        "",
    ]
    for issue_id, entry in superseded.items():
        summary = entry.get("original_summary", "")
        summary_str = f" — {summary}" if summary else ""
        lines.append(f"- ~~{issue_id}~~{summary_str}")
        candidates = entry.get("candidates", [])
        if candidates:
            lines.append(f"  Candidates: {', '.join(candidates[:3])}")
        note = entry.get("note")
        if note:
            lines.append(f"  Note: {note}")
    lines.append("")
    return lines

