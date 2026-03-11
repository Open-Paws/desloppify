"""Stage-gate and coverage helpers for triage command handlers."""

from __future__ import annotations

from desloppify.base.output.terminal import colorize
from desloppify.engine.plan_triage import TRIAGE_IDS

from ..helpers import active_triage_issue_ids, cluster_issue_ids


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


def unenriched_clusters(plan: dict) -> list[tuple[str, list[str]]]:
    """Return clusters with issues that are missing required enrichment.

    Requirements:
    - Every cluster needs a description and at least one action_step.
    - Small clusters (< 5 issues) need at least 1 action step per issue,
      so each item has a concrete plan. Large clusters (>= 5) just need
      steps overall (cluster-level plan is sufficient).
    """
    gaps: list[tuple[str, list[str]]] = []
    for name, cluster in plan.get("clusters", {}).items():
        issue_ids = cluster_issue_ids(cluster)
        if not issue_ids:
            continue
        if cluster.get("auto"):
            continue
        missing: list[str] = []
        if not cluster.get("description"):
            missing.append("description")
        steps = cluster.get("action_steps") or []
        issue_count = len(issue_ids)
        if not steps:
            missing.append("action_steps")
        elif issue_count < 5 and len(steps) < issue_count:
            missing.append(
                f"action_steps (have {len(steps)}, need >= {issue_count} for small cluster)"
            )
        if missing:
            gaps.append((name, missing))
    return gaps


def unclustered_review_issues(plan: dict, state: dict | None = None) -> list[str]:
    """Return review issue IDs that aren't in any manual cluster.

    When *state* is provided, uses open review/concerns issues from state
    (the canonical source). Falls back to scanning queue_order for backwards
    compatibility.
    """
    clusters = plan.get("clusters", {})
    clustered_ids: set[str] = set()
    for cluster in clusters.values():
        if not cluster.get("auto"):
            clustered_ids.update(cluster_issue_ids(cluster))
    skipped_ids = {
        fid for fid in (plan.get("skipped", {}) or {}).keys() if isinstance(fid, str)
    }

    if state is not None:
        review_ids = [
            fid for fid, finding in state.get("issues", {}).items()
            if finding.get("status") == "open"
            and finding.get("detector") in ("review", "concerns")
        ]
        frozen_ids = (plan.get("epic_triage_meta", {}) or {}).get("active_triage_issue_ids")
        if isinstance(frozen_ids, list) and frozen_ids:
            frozen_id_set = active_triage_issue_ids(plan, state)
            review_ids = [fid for fid in review_ids if fid in frozen_id_set]
            missing_frozen = [fid for fid in frozen_ids if isinstance(fid, str) and fid not in set(review_ids)]
            review_ids.extend(missing_frozen)
    else:
        review_ids = [
            fid for fid in plan.get("queue_order", [])
            if not fid.startswith("triage::") and not fid.startswith("workflow::")
            and (fid.startswith("review::") or fid.startswith("concerns::"))
        ]

    return [
        fid for fid in review_ids
        if fid not in clustered_ids and fid not in skipped_ids
    ]
