"""Stage persistence helpers for triage command handlers."""

from __future__ import annotations

from desloppify.engine.planning.triage import review_issue_snapshot_hash
from desloppify.state import utc_now
from desloppify.engine.plan import save_plan


def refresh_stage_snapshot(plan: dict, state: dict) -> None:
    """Mark stage progress as aligned with the current review-issue snapshot."""
    meta = plan.setdefault("epic_triage_meta", {})
    meta["stage_snapshot_hash"] = review_issue_snapshot_hash(state)
    meta["stage_refresh_required"] = False


def record_triage_stage(
    plan: dict,
    state: dict,
    *,
    stage: str,
    report: str,
    cited_ids: list[str],
    issue_count: int,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    """Persist one stage payload, refresh snapshot metadata, and save the plan."""
    meta = plan.setdefault("epic_triage_meta", {})
    stages = meta.setdefault("triage_stages", {})
    payload: dict[str, object] = {
        "stage": stage,
        "report": report,
        "cited_ids": list(cited_ids),
        "timestamp": utc_now(),
        "issue_count": issue_count,
    }
    if extra:
        payload.update(extra)
    stages[stage] = payload
    refresh_stage_snapshot(plan, state)
    save_plan(plan)
    return payload
