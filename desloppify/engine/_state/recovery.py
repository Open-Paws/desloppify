"""State reconstruction helpers for missing scan state with a surviving plan."""

from __future__ import annotations

from typing import Any

from desloppify.engine._plan.skip_policy import skip_kind_state_status
from desloppify.engine._state.issue_semantics import ensure_work_item_semantics
from desloppify.engine._state.schema import ensure_state_defaults, scan_source, utc_now


def _readable_token(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").strip() or "unknown"


def _recovered_review_summary(issue_id: str) -> str:
    parts = issue_id.split("::")
    if issue_id.startswith("review::.::holistic::") and len(parts) >= 5:
        dimension = _readable_token(parts[3])
        identifier = _readable_token(" ".join(parts[4:]))
        return f"Recovered holistic review item for {dimension}: {identifier}"
    if issue_id.startswith("review::") and len(parts) >= 3:
        file_path = parts[1] or "."
        identifier = _readable_token(" ".join(parts[2:]))
        return f"Recovered review item for {file_path}: {identifier}"
    if issue_id.startswith("concerns::") and len(parts) >= 3:
        file_path = parts[1] or "."
        identifier = _readable_token(" ".join(parts[2:]))
        return f"Recovered concern for {file_path}: {identifier}"
    return "Recovered review item from saved plan"


def _recovered_review_detail(issue_id: str) -> dict:
    parts = issue_id.split("::")
    dimension = parts[3] if issue_id.startswith("review::.::holistic::") and len(parts) > 3 else "unknown"
    return {
        "dimension": dimension or "unknown",
        "recovered_from_plan": True,
        "evidence": [
            "Recovered from saved plan metadata after scan state was unavailable.",
            "Original review evidence was not present in the saved plan.",
        ],
        "suggestion": (
            "Re-run or re-import the review for this item before treating it as a "
            "code defect."
        ),
    }


def _recovered_generic_summary(issue_id: str) -> str:
    parts = issue_id.split("::")
    if len(parts) >= 3:
        detector, file_path = parts[0], parts[1] or "."
        identifier = _readable_token(" ".join(parts[2:]))
        return f"Recovered {detector} item for {file_path}: {identifier}"
    return f"Recovered plan item: {issue_id}"


def _recovered_item_from_id(issue_id: str) -> dict[str, Any]:
    if issue_id.startswith(("review::", "concerns::")):
        detector = "concerns" if issue_id.startswith("concerns::") else "review"
        parts = issue_id.split("::")
        return {
            "id": issue_id,
            "status": "open",
            "detector": detector,
            "file": parts[1] if len(parts) > 1 else "",
            "summary": _recovered_review_summary(issue_id),
            "confidence": "medium",
            "tier": 2,
            "detail": _recovered_review_detail(issue_id),
        }
    parts = issue_id.split("::")
    return {
        "id": issue_id,
        "status": "open",
        "detector": parts[0] if parts else "unknown",
        "file": parts[1] if len(parts) > 1 else "",
        "summary": _recovered_generic_summary(issue_id),
        "confidence": "medium",
        "tier": 3,
        "detail": {
            "recovered_from_plan": True,
            "evidence": [
                "Recovered from saved plan metadata after scan state was unavailable.",
                "Original detector detail was not present in the saved plan.",
            ],
            "suggestion": "Run a fresh scan to refresh this recovered item.",
        },
    }


def _append_review_id(
    ordered: list[str],
    seen: set[str],
    issue_id: object,
) -> None:
    if not isinstance(issue_id, str):
        return
    normalized = issue_id.strip()
    if not normalized:
        return
    if not (
        normalized.startswith("review::")
        or normalized.startswith("concerns::")
    ):
        return
    if normalized in seen:
        return
    seen.add(normalized)
    ordered.append(normalized)


def saved_plan_review_ids(
    plan: dict | None,
    *,
    include_clusters: bool = True,
) -> list[str]:
    """Return review IDs recoverable from a saved plan.

    When ``include_clusters`` is true, include IDs retained only in cluster
    membership or ``action_steps[*].issue_refs``. This preserves the broader
    compatibility contract used by manual recovery helpers.
    """
    if not isinstance(plan, dict):
        return []

    ordered: list[str] = []
    seen: set[str] = set()

    for issue_id in plan.get("queue_order", []):
        _append_review_id(ordered, seen, issue_id)

    if not include_clusters:
        return ordered

    clusters = plan.get("clusters", {})
    if not isinstance(clusters, dict):
        return ordered

    for cluster in clusters.values():
        if not isinstance(cluster, dict):
            continue
        for issue_id in cluster.get("issue_ids", []):
            _append_review_id(ordered, seen, issue_id)
        for step in cluster.get("action_steps", []):
            if not isinstance(step, dict):
                continue
            for issue_id in step.get("issue_refs", []):
                _append_review_id(ordered, seen, issue_id)

    return ordered


def saved_plan_skipped_entries(plan: dict | None) -> dict[str, dict]:
    """Return recoverable skipped-plan entries keyed by issue ID."""
    if not isinstance(plan, dict):
        return {}
    skipped = plan.get("skipped")
    if not isinstance(skipped, dict):
        return {}
    entries: dict[str, dict] = {}
    for issue_id, raw in skipped.items():
        if not isinstance(issue_id, str) or not issue_id:
            continue
        entries[issue_id] = dict(raw) if isinstance(raw, dict) else {"kind": "temporary"}
    return entries


def saved_plan_open_review_ids(plan: dict | None) -> list[str]:
    """Return review IDs still represented in the current queue."""
    return saved_plan_review_ids(plan, include_clusters=False)


def has_saved_plan_without_scan(state: dict, plan: dict | None) -> bool:
    """Whether a saved plan can be resumed without a current scan state."""
    if scan_source(state) == "scan":
        return False
    if not isinstance(plan, dict):
        return False
    meta = plan.get("epic_triage_meta")
    triage_meta = meta if isinstance(meta, dict) else {}
    return bool(
        plan.get("queue_order")
        or plan.get("clusters")
        or triage_meta.get("triage_stages")
        or triage_meta.get("strategy_summary")
    )


def _hydrate_saved_issue_ids(
    state: dict,
    issue_ids: list[str],
) -> dict:
    recovered = dict(state)
    issues = (state.get("work_items") or state.get("issues", {}))
    recovered_issues = dict(issues) if isinstance(issues, dict) else {}

    for issue_id in issue_ids:
        if issue_id in recovered_issues:
            continue
        recovered_issues[issue_id] = _recovered_item_from_id(issue_id)
        ensure_work_item_semantics(recovered_issues[issue_id])

    recovered["work_items"] = recovered_issues
    recovered["issues"] = recovered_issues
    recovered["scan_metadata"] = {
        "source": "plan_reconstruction",
        "plan_queue_available": bool(issue_ids),
        "reconstructed_issue_count": len(issue_ids),
    }
    ensure_state_defaults(recovered)
    return recovered


def reconcile_saved_plan_skips(state: dict, plan: dict | None) -> tuple[dict, int]:
    """Restore state statuses for issue IDs preserved only in plan.skipped."""
    skipped = saved_plan_skipped_entries(plan)
    if not skipped:
        return state, 0

    recovered = dict(state)
    issues = state.get("work_items") or state.get("issues", {})
    recovered_issues = dict(issues) if isinstance(issues, dict) else {}
    changed = 0
    now = utc_now()

    for issue_id, entry in skipped.items():
        kind = str(entry.get("kind") or "temporary")
        target_status = skip_kind_state_status(kind)
        if not target_status:
            continue
        issue = recovered_issues.get(issue_id)
        if not isinstance(issue, dict):
            issue = _recovered_item_from_id(issue_id)
            recovered_issues[issue_id] = issue
        previous_status = issue.get("status")
        if previous_status != target_status:
            issue["status"] = target_status
            changed += 1
        note = entry.get("note") or entry.get("reason")
        if note:
            issue["note"] = str(note)
        if target_status in {"wontfix", "false_positive"}:
            issue["resolved_at"] = issue.get("resolved_at") or now
            issue["resolution_attestation"] = {
                "kind": "plan_skip_recovery",
                "skip_kind": kind,
                "attestation": entry.get("attestation"),
            }
        detail = issue.setdefault("detail", {})
        if isinstance(detail, dict):
            detail["recovered_skip_kind"] = kind
            detail["recovered_from_plan"] = True
        ensure_work_item_semantics(issue)

    recovered["work_items"] = recovered_issues
    recovered["issues"] = recovered_issues
    ensure_state_defaults(recovered)
    return recovered, changed


def recover_state_from_saved_plan(state: dict, plan: dict | None) -> dict:
    """Hydrate all review IDs recoverable from a saved plan."""
    if not has_saved_plan_without_scan(state, plan):
        return state
    return _hydrate_saved_issue_ids(state, saved_plan_review_ids(plan))


def reconstruct_state_from_saved_plan(state: dict, plan: dict | None) -> dict:
    """Hydrate only the review IDs still present in the live queue."""
    if not has_saved_plan_without_scan(state, plan):
        return state
    return _hydrate_saved_issue_ids(state, saved_plan_open_review_ids(plan))


__all__ = [
    "has_saved_plan_without_scan",
    "reconcile_saved_plan_skips",
    "reconstruct_state_from_saved_plan",
    "recover_state_from_saved_plan",
    "saved_plan_open_review_ids",
    "saved_plan_review_ids",
    "saved_plan_skipped_entries",
]
