"""Progression log — append-only lifecycle event log for CEO agent narrative.

Records boundary events (marker flips, phase transitions, scan completions)
to ``.desloppify/progression.jsonl``.  Each line is a self-contained JSON
object with a discriminated ``event_type`` + ``payload``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from desloppify.engine._plan.constants import is_synthetic_id
from desloppify.engine._state.schema import get_state_dir, utc_now

logger = logging.getLogger(__name__)

PROGRESSION_VERSION = 1
_MAX_LINES = 2000
_LOCK_TIMEOUT = 2.0


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def progression_path() -> Path:
    """Return the canonical progression log path."""
    return get_state_dir() / "progression.jsonl"


def load_progression(path: Path | None = None) -> list[dict[str, Any]]:
    """Read all events from the progression log.

    Corrupt lines are skipped with a warning — the file is never erased.
    """
    target = path or progression_path()
    if not target.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        with open(target, encoding="utf-8") as fh:
            for lineno, raw_line in enumerate(fh, 1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    logger.warning(
                        "progression.jsonl line %d corrupt — skipped", lineno
                    )
    except OSError as exc:
        logger.warning("Could not read progression log: %s", exc)
    return events


def last_plan_checkpoint_timestamp(path: Path | None = None) -> str | None:
    """Return the most recent plan-checkpoint timestamp from the progression log."""
    for event in reversed(load_progression(path)):
        if event.get("event_type") != "plan_checkpoint":
            continue
        timestamp = event.get("timestamp")
        if isinstance(timestamp, str):
            return timestamp
    return None


def append_progression_event(
    event: dict[str, Any],
    *,
    path: Path | None = None,
) -> None:
    """Append a single event to the progression log with advisory file lock."""
    target = path or progression_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, separators=(",", ":"), default=str) + "\n"

    lock_fd: int | None = None
    lock_path = target.with_suffix(".jsonl.lock")
    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        _acquire_lock(lock_fd)
    except Exception:
        if lock_fd is not None:
            _safe_close(lock_fd)
            lock_fd = None
        logger.warning(
            "Could not acquire progression lock for %s — appending without lock",
            event.get("event_type", "unknown"),
        )

    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError as exc:
        logger.warning("Failed to append progression event: %s", exc)
    finally:
        if lock_fd is not None:
            _release_lock(lock_fd)
            _safe_close(lock_fd)

    # Periodic trim
    scan_count = event.get("scan_count")
    if isinstance(scan_count, int) and scan_count > 0 and scan_count % 50 == 0:
        _trim_if_needed(target)


def _trim_if_needed(path: Path, max_lines: int = _MAX_LINES) -> None:
    """Keep the last *max_lines* when the file grows too large."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
        if len(lines) <= max_lines:
            return
        trimmed = lines[-max_lines:]
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(trimmed)
    except OSError as exc:
        logger.warning("Progression trim failed: %s", exc)


# ---------------------------------------------------------------------------
# Lock helpers (advisory, best-effort)
# ---------------------------------------------------------------------------

_LOCK_RETRY_ERRNOS = frozenset({
    getattr(__import__("errno"), "EACCES", 13),
    getattr(__import__("errno"), "EAGAIN", 11),
    getattr(__import__("errno"), "EDEADLK", 35),
})


def _acquire_lock(lock_fd: int) -> None:
    deadline = time.monotonic() + _LOCK_TIMEOUT
    while True:
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(lock_fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if exc.errno not in _LOCK_RETRY_ERRNOS:
                raise
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Could not acquire progression lock within {_LOCK_TIMEOUT}s"
                ) from None
            time.sleep(0.05)


def _release_lock(lock_fd: int) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(lock_fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
    except OSError:
        pass


def _safe_close(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Snapshot helpers (pure)
# ---------------------------------------------------------------------------

def _scores_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    """Extract ProgressionScores from state."""
    from desloppify.state_score_snapshot import score_snapshot

    snap = score_snapshot(state)
    return {
        "overall": snap.overall,
        "objective": snap.objective,
        "strict": snap.strict,
        "verified_strict": snap.verified,
    }


def _dimensions_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    """Extract dimension scores from state."""
    dim_scores = state.get("dimension_scores")
    if not isinstance(dim_scores, dict):
        return {}
    result: dict[str, Any] = {}
    for key, value in dim_scores.items():
        if not isinstance(value, dict):
            continue
        entry: dict[str, Any] = {}
        if "score" in value:
            entry["score"] = value["score"]
        if "strict" in value:
            entry["strict"] = value["strict"]
        if entry:
            result[key] = entry
    return result


def _execution_log_ids_since(
    plan: dict[str, Any],
    since: str | None,
) -> tuple[list[str], list[str]]:
    """Extract resolved and skipped issue IDs from execution log since *since*."""
    resolved: list[str] = []
    skipped: list[str] = []
    for entry in plan.get("execution_log", []):
        ts = entry.get("timestamp", "")
        if since and ts < since:
            continue
        action = entry.get("action", "")
        ids = entry.get("issue_ids", [])
        if action in ("resolve", "done") and ids:
            resolved.extend(ids)
        elif action == "skip" and ids:
            skipped.extend(ids)
    return resolved, skipped




def _extract_review_payload_detail(
    import_payload: dict[str, Any] | None,
) -> tuple[dict[str, str], list[dict[str, str]], dict[str, str]]:
    """Extract dimension notes summary, issue summaries, and provenance from import payload.

    Returns (dimension_notes_summary, review_issue_summaries, provenance).
    """
    dim_notes: dict[str, str] = {}
    issue_summaries: list[dict[str, str]] = []
    prov: dict[str, str] = {}
    if not isinstance(import_payload, dict):
        return dim_notes, issue_summaries, prov

    raw_notes = import_payload.get("dimension_notes")
    if isinstance(raw_notes, dict):
        for dim_key, note_data in raw_notes.items():
            if not isinstance(note_data, dict):
                continue
            evidence = note_data.get("evidence")
            if isinstance(evidence, list) and evidence:
                dim_notes[dim_key] = str(evidence[0])[:200]

    raw_issues = import_payload.get("issues")
    if isinstance(raw_issues, list):
        for issue in raw_issues[:50]:
            if isinstance(issue, dict):
                issue_summaries.append({
                    "dimension": str(issue.get("dimension", "")),
                    "summary": str(issue.get("summary", ""))[:200],
                    "confidence": str(issue.get("confidence", "")),
                })

    raw_prov = import_payload.get("provenance")
    if isinstance(raw_prov, dict):
        for prov_key in ("kind", "runner", "packet_sha256"):
            val = raw_prov.get(prov_key)
            if isinstance(val, str) and val:
                prov[prov_key] = val

    return dim_notes, issue_summaries, prov


def _open_issue_count(state: dict[str, Any]) -> int:
    issues = state.get("work_items") or state.get("issues", {})
    if not isinstance(issues, dict):
        return 0
    return sum(
        1 for issue in issues.values()
        if isinstance(issue, dict) and issue.get("status") == "open"
    )


def _queue_summary(plan: dict[str, Any] | None) -> dict[str, int]:
    if not isinstance(plan, dict):
        return {}
    order = plan.get("queue_order")
    skipped = plan.get("skipped")
    if not isinstance(order, list):
        return {}
    skipped_ids = set(skipped.keys()) if isinstance(skipped, dict) else set()
    summary: dict[str, int] = {}
    for item in order:
        if not isinstance(item, str) or item in skipped_ids:
            continue
        bucket = "objective"
        if is_synthetic_id(item):
            bucket = item.split("::", 1)[0] or "synthetic"
        summary[bucket] = summary.get(bucket, 0) + 1
    return summary


# ---------------------------------------------------------------------------
# Envelope builder
# ---------------------------------------------------------------------------

def _make_envelope(
    event_type: str,
    state: dict[str, Any] | None,
    plan: dict[str, Any] | None,
    *,
    source_command: str,
    phase_before: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build a full progression event envelope."""
    from desloppify.engine._plan.refresh_lifecycle import current_lifecycle_phase

    phase_after = current_lifecycle_phase(plan) if isinstance(plan, dict) else None
    scan_count = (
        int(state.get("scan_count", 0) or 0) if isinstance(state, dict) else None
    )
    envelope: dict[str, Any] = {
        "schema_version": PROGRESSION_VERSION,
        "event_type": event_type,
        "timestamp": utc_now(),
        "source_command": source_command,
        "phase_before": phase_before,
        "phase_after": phase_after,
        "payload": payload,
    }
    if scan_count is not None:
        envelope["scan_count"] = scan_count
    return envelope


# ---------------------------------------------------------------------------
# Event builders (one per event type)
# ---------------------------------------------------------------------------

def build_scan_preflight_event(
    plan: dict[str, Any] | None,
    *,
    result: str,
    reason: str,
    queue_count: int,
    phase_before: str | None,
) -> dict[str, Any]:
    return _make_envelope(
        "scan_preflight",
        None,
        plan,
        source_command="scan",
        phase_before=phase_before,
        payload={
            "result": result,
            "reason": reason,
            "queue_item_count": queue_count,
        },
    )


def build_scan_complete_event(
    state: dict[str, Any],
    plan: dict[str, Any] | None,
    diff: dict[str, Any],
    *,
    lang: str | None,
    phase_before: str | None,
    execution_summary: dict[str, int] | None,
    prev_dimension_scores: dict[str, Any] | None = None,
    resolved_ids: list[str] | None = None,
    skipped_ids: list[str] | None = None,
) -> dict[str, Any]:
    from desloppify.engine._state.scoring import suppression_metrics

    supp = suppression_metrics(state)
    payload: dict[str, Any] = {
        "dimension_scores": _dimensions_snapshot(state),
        "scan_diff": {
            "new": diff.get("new", 0),
            "auto_resolved": diff.get("auto_resolved", 0),
            "reopened": diff.get("reopened", 0),
            "total_current": diff.get("total_current", 0),
        },
        "open_count": _open_issue_count(state),
        "suppressed_pct": supp.get("last_suppressed_pct", 0.0),
        "lang": lang,
        "execution_summary": execution_summary or {},
    }
    if prev_dimension_scores:
        payload["prev_dimension_scores"] = prev_dimension_scores
    # Include dimension-level deltas for quick progression reads
    if prev_dimension_scores:
        current_dims = payload["dimension_scores"]
        deltas: dict[str, float] = {}
        for dim_key, cur in current_dims.items():
            prev_dim = prev_dimension_scores.get(dim_key, {})
            cur_strict = cur.get("strict")
            prev_strict = prev_dim.get("strict")
            if cur_strict is not None and prev_strict is not None:
                deltas[dim_key] = round(cur_strict - prev_strict, 2)
        if deltas:
            payload["dimension_deltas"] = deltas
    if resolved_ids:
        payload["resolved_ids"] = resolved_ids
    if skipped_ids:
        payload["skipped_ids"] = skipped_ids
    return _make_envelope(
        "scan_complete",
        state,
        plan,
        source_command="scan",
        phase_before=phase_before,
        payload=payload,
    )


def build_postflight_scan_event(
    plan: dict[str, Any] | None,
    *,
    scan_count_marker: int,
    phase_before: str | None,
) -> dict[str, Any]:
    return _make_envelope(
        "postflight_scan_completed",
        None,
        plan,
        source_command="scan",
        phase_before=phase_before,
        payload={"scan_count_marker": scan_count_marker},
    )


def build_review_complete_event(
    state: dict[str, Any],
    plan: dict[str, Any] | None,
    *,
    assessment_mode: str,
    covered_count: int,
    new_ids_count: int,
    phase_before: str | None,
    covered_dimensions: list[str] | None = None,
    new_review_ids: list[str] | None = None,
    dimension_notes_summary: dict[str, str] | None = None,
    review_issue_summaries: list[dict[str, str]] | None = None,
    import_file: str | None = None,
    provenance: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dimension_scores": _dimensions_snapshot(state),
        "open_count": _open_issue_count(state),
        "assessment_mode": assessment_mode,
        "covered_dimension_count": covered_count,
        "covered_dimensions": covered_dimensions or [],
        "new_review_ids_count": new_ids_count,
        "new_review_ids": new_review_ids or [],
        "dimension_notes_summary": dimension_notes_summary or {},
        "review_issue_summaries": review_issue_summaries or [],
    }
    if import_file:
        payload["import_file"] = import_file
    if provenance:
        payload["provenance"] = provenance
    return _make_envelope(
        "subjective_review_completed",
        state,
        plan,
        source_command="review",
        phase_before=phase_before,
        payload=payload,
    )


def build_triage_complete_event(
    plan: dict[str, Any],
    state: dict[str, Any],
    *,
    completion_mode: str,
    strategy_summary: str,
    organized: int,
    total: int,
    clusters: dict[str, Any],
    phase_before: str | None,
) -> dict[str, Any]:
    # Extract verdict counts from dispositions
    dispositions = (
        plan.get("epic_triage_meta", {}).get("issue_dispositions", {})
    )
    verdict_counts: dict[str, int] = {}
    if isinstance(dispositions, dict):
        for disp in dispositions.values():
            verdict = disp.get("verdict") if isinstance(disp, dict) else None
            if isinstance(verdict, str):
                verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

    skip_count = len(plan.get("skipped", {}))

    # Capture cluster summaries for CEO agent context
    cluster_summaries: list[dict[str, Any]] = []
    for name, cluster in clusters.items():
        if not isinstance(cluster, dict):
            continue
        issue_ids = cluster.get("issue_ids", [])
        if not issue_ids:
            continue
        cluster_summaries.append({
            "name": name,
            "thesis": str(cluster.get("thesis") or cluster.get("description") or "")[:200],
            "issue_count": len(issue_ids),
        })

    return _make_envelope(
        "triage_complete",
        state,
        plan,
        source_command="plan triage",
        phase_before=phase_before,
        payload={
            "completion_mode": completion_mode,
            "strategy_summary": strategy_summary,
            "cluster_count": len(clusters),
            "cluster_summaries": cluster_summaries,
            "organized_count": organized,
            "total_review_count": total,
            "verdict_counts": verdict_counts,
            "skip_count": skip_count,
        },
    )


def build_entered_planning_event(
    state: dict[str, Any] | None,
    plan: dict[str, Any] | None,
    *,
    trigger_action: str,
    issue_ids: list[str] | None,
    phase_before: str | None,
    source_command: str = "resolve",
) -> dict[str, Any]:
    return _make_envelope(
        "entered_planning_mode",
        state,
        plan,
        source_command=source_command,
        phase_before=phase_before,
        payload={
            "trigger_action": trigger_action,
            "issue_ids": issue_ids,
        },
    )


def build_execution_drain_event(
    state: dict[str, Any],
    plan: dict[str, Any] | None,
    *,
    trigger_action: str,
    issue_ids: list[str],
    cluster_name: str | None,
    phase_before: str | None,
    source_command: str = "resolve",
) -> dict[str, Any]:
    return _make_envelope(
        "execution_drain",
        state,
        plan,
        source_command=source_command,
        phase_before=phase_before,
        payload={
            "open_count": _open_issue_count(state),
            "trigger_action": trigger_action,
            "issue_ids": issue_ids,
            "cluster_name": cluster_name,
        },
    )


def build_plan_checkpoint_event(
    state: dict[str, Any],
    plan: dict[str, Any],
    *,
    phase_before: str | None,
    trigger: str,
    source_command: str,
    plan_start_scores_snapshot: dict[str, Any] | None = None,
    prev_plan_start_scores_snapshot: dict[str, Any] | None = None,
    resolved_since_last: list[str] | None = None,
    skipped_since_last: list[str] | None = None,
    execution_summary: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build the canonical score checkpoint event.

    *plan_start_scores_snapshot* and *prev_plan_start_scores_snapshot* are
    captured by ``ReconcileResult`` at the moment communicate-score fires,
    before post-reconcile clearing can wipe them.  When provided they take
    precedence over the (possibly already cleared) plan dict values.
    """
    payload = {
        "scores": _scores_snapshot(state),
        "dimension_scores": _dimensions_snapshot(state),
        "plan_start_scores": (
            dict(plan_start_scores_snapshot)
            if isinstance(plan_start_scores_snapshot, dict)
            else dict(plan.get("plan_start_scores", {}) or {})
        ),
        "previous_plan_start_scores": (
            dict(prev_plan_start_scores_snapshot)
            if isinstance(prev_plan_start_scores_snapshot, dict)
            else dict(plan.get("previous_plan_start_scores", {}) or {})
        ),
        "open_count": _open_issue_count(state),
        "queue_summary": _queue_summary(plan),
        "trigger": trigger,
        "execution_summary": execution_summary or {},
    }
    if resolved_since_last:
        payload["resolved_since_last"] = resolved_since_last
    if skipped_since_last:
        payload["skipped_since_last"] = skipped_since_last
    return _make_envelope(
        "plan_checkpoint",
        state,
        plan,
        source_command=source_command,
        phase_before=phase_before,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Conditional helpers for hook sites
# ---------------------------------------------------------------------------

_PLANNING_PHASES = frozenset({
    "plan",
})


def maybe_append_entered_planning(
    state: dict[str, Any] | None,
    plan: dict[str, Any] | None,
    *,
    source_command: str,
    trigger_action: str,
    issue_ids: list[str] | None,
    phase_before: str | None,
) -> None:
    """Append ``entered_planning_mode`` if the phase just changed to a planning phase."""
    from desloppify.engine._plan.refresh_lifecycle import current_lifecycle_phase

    if not isinstance(plan, dict):
        return
    phase_after = current_lifecycle_phase(plan)
    if phase_after in _PLANNING_PHASES and phase_after != phase_before:
        try:
            append_progression_event(
                build_entered_planning_event(
                    state,
                    plan,
                    trigger_action=trigger_action,
                    issue_ids=issue_ids,
                    phase_before=phase_before,
                    source_command=source_command,
                )
            )
        except Exception:
            logger.warning("Failed to append entered_planning_mode event", exc_info=True)


def maybe_append_execution_drain(
    state: dict[str, Any],
    plan: dict[str, Any] | None,
    *,
    trigger_action: str,
    issue_ids: list[str],
    cluster_name: str | None = None,
    phase_before: str | None,
    source_command: str = "resolve",
) -> None:
    """Append ``execution_drain`` if the lifecycle phase changed."""
    from desloppify.engine._plan.refresh_lifecycle import current_lifecycle_phase

    if not isinstance(plan, dict):
        return
    phase_after = current_lifecycle_phase(plan)
    if phase_after != phase_before:
        try:
            append_progression_event(
                build_execution_drain_event(
                    state,
                    plan,
                    trigger_action=trigger_action,
                    issue_ids=issue_ids,
                    cluster_name=cluster_name,
                    phase_before=phase_before,
                    source_command=source_command,
                )
            )
        except Exception:
            logger.warning("Failed to append execution_drain event", exc_info=True)


__all__ = [
    "PROGRESSION_VERSION",
    "append_progression_event",
    "build_entered_planning_event",
    "build_execution_drain_event",
    "build_plan_checkpoint_event",
    "build_postflight_scan_event",
    "build_review_complete_event",
    "build_scan_complete_event",
    "build_scan_preflight_event",
    "build_triage_complete_event",
    "last_plan_checkpoint_timestamp",
    "load_progression",
    "maybe_append_entered_planning",
    "maybe_append_execution_drain",
    "progression_path",
    "_queue_summary",
    "_execution_log_ids_since",
    "_extract_review_payload_detail",
]
