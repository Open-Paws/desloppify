"""Stage-gate and coverage helpers for triage command handlers."""

from __future__ import annotations

from desloppify.core.output import colorize
from desloppify.engine.plan import TRIAGE_IDS


def _require_triage_pending(plan: dict, *, action: str) -> bool:
    """Require at least one triage stage ID to be present in queue for an action."""
    order = set(plan.get("queue_order", []))
    if order & TRIAGE_IDS:
        return True
    print(colorize(f"  No triage stage in the queue — nothing to {action}.", "yellow"))
    return False


def _validate_stage_report(
    report: str | None,
    *,
    stage: str,
    min_chars: int,
    missing_guidance: list[str] | None = None,
    short_guidance: list[str] | None = None,
) -> str | None:
    """Validate staged report presence/length and print consistent guidance."""
    if not report:
        print(colorize(f"  --report is required for --stage {stage}.", "red"))
        for line in missing_guidance or []:
            print(colorize(f"  {line}", "dim"))
        return None
    cleaned = report.strip()
    if len(cleaned) < min_chars:
        print(
            colorize(
                f"  Report too short: {len(cleaned)} chars (minimum {min_chars}).",
                "red",
            )
        )
        for line in short_guidance or []:
            print(colorize(f"  {line}", "dim"))
        return None
    return cleaned


def _triage_coverage(plan: dict) -> tuple[int, int, dict]:
    """Return (organized, total, clusters) for triage progress."""
    clusters = plan.get("clusters", {})
    all_cluster_ids: set[str] = set()
    for cluster in clusters.values():
        all_cluster_ids.update(cluster.get("issue_ids", []))
    queue_ids = [issue_id for issue_id in plan.get("queue_order", []) if issue_id not in TRIAGE_IDS]
    organized = sum(1 for issue_id in queue_ids if issue_id in all_cluster_ids)
    return organized, len(queue_ids), clusters


def _unenriched_clusters(plan: dict) -> list[tuple[str, list[str]]]:
    """Return clusters with issues that are missing required enrichment."""
    gaps: list[tuple[str, list[str]]] = []
    for name, cluster in plan.get("clusters", {}).items():
        if not cluster.get("issue_ids"):
            continue
        if cluster.get("auto"):
            continue
        missing: list[str] = []
        if not cluster.get("description"):
            missing.append("description")
        if not cluster.get("action_steps"):
            missing.append("action_steps")
        if missing:
            gaps.append((name, missing))
    return gaps


def _manual_clusters_with_issues(plan: dict) -> list[str]:
    """Return names of non-auto clusters that have issues."""
    return [
        name
        for name, cluster in plan.get("clusters", {}).items()
        if cluster.get("issue_ids") and not cluster.get("auto")
    ]
