"""State schema/types, constants, and validation helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, NotRequired, Required, TypedDict

from desloppify.core.text_api import PROJECT_ROOT
from desloppify.core.enums import canonical_issue_status, issue_status_tokens
from desloppify.engine._state.schema_scores import (
    get_objective_score,
    get_overall_score,
    get_strict_score,
    get_verified_strict_score,
    json_default,
)
from desloppify.languages._framework.base.types import ScanCoverageRecord

__all__ = [
    "ConcernDismissal",
    "IssueStatus",
    "Issue",
    "TierStats",
    "StateStats",
    "DimensionScore",
    "ScanHistoryEntry",
    "SubjectiveAssessment",
    "SubjectiveIntegrity",
    "StateModel",
    "ScanDiff",
    "STATE_DIR",
    "STATE_FILE",
    "CURRENT_VERSION",
    "utc_now",
    "empty_state",
    "ensure_state_defaults",
    "validate_state_invariants",
    "json_default",
    "get_overall_score",
    "get_objective_score",
    "get_strict_score",
    "get_verified_strict_score",
    "migrate_state_keys",
]

IssueStatus = Literal["open", "fixed", "auto_resolved", "wontfix", "false_positive"]
_ALLOWED_ISSUE_STATUSES: set[str] = {
    *issue_status_tokens(),
}


class Issue(TypedDict):
    """The central data structure: a normalized issue from any detector."""

    id: str
    detector: str
    file: str
    tier: int
    confidence: str
    summary: str
    detail: dict[str, Any]
    status: IssueStatus
    note: str | None
    first_seen: str
    last_seen: str
    resolved_at: str | None
    reopen_count: int
    suppressed: NotRequired[bool]
    suppressed_at: NotRequired[str | None]
    suppression_pattern: NotRequired[str | None]
    resolution_attestation: NotRequired[dict[str, str | bool | None]]
    lang: NotRequired[str]
    zone: NotRequired[str]


class TierStats(TypedDict, total=False):
    open: int
    fixed: int
    auto_resolved: int
    wontfix: int
    false_positive: int


class StateStats(TypedDict, total=False):
    total: int
    open: int
    fixed: int
    auto_resolved: int
    wontfix: int
    false_positive: int
    by_tier: dict[str, TierStats]


class DimensionScore(TypedDict, total=False):
    score: float
    strict: float
    checks: int
    failing: int
    tier: int
    detectors: dict[str, Any]


class ScanHistoryEntry(TypedDict, total=False):
    timestamp: str
    lang: str | None
    strict_score: float | None
    verified_strict_score: float | None
    objective_score: float | None
    overall_score: float | None
    open: int
    diff_new: int
    diff_resolved: int
    ignored: int
    raw_issues: int
    suppressed_pct: float
    ignore_patterns: int
    subjective_integrity: dict[str, Any] | None
    dimension_scores: dict[str, dict[str, float]] | None
    score_confidence: dict[str, Any] | None


class SubjectiveIntegrity(TypedDict, total=False):
    """Anti-gaming metadata for subjective assessment scores."""

    status: str  # "disabled" | "pass" | "warn" | "penalized"
    target_score: float | None
    matched_count: int
    matched_dimensions: list[str]
    reset_dimensions: list[str]


class SubjectiveAssessment(TypedDict, total=False):
    """A single subjective dimension assessment payload."""

    score: float
    integrity_penalty: str | None
    provisional_override: bool
    provisional_until_scan: int
    needs_review_refresh: bool
    refresh_reason: str | None
    stale_since: str | None


class ConcernDismissal(TypedDict, total=False):
    """Record of a dismissed concern from review output."""

    dismissed_at: str
    reason: str | None
    dimension: str


class StateModel(TypedDict, total=False):
    version: Required[int]
    created: Required[str]
    last_scan: Required[str | None]
    scan_count: Required[int]
    overall_score: Required[float]
    objective_score: Required[float]
    strict_score: Required[float]
    verified_strict_score: Required[float]
    stats: Required[StateStats]
    issues: Required[dict[str, Issue]]
    scan_coverage: dict[str, ScanCoverageRecord]
    score_confidence: dict[str, Any]
    scan_history: list[ScanHistoryEntry]
    subjective_integrity: Required[SubjectiveIntegrity]
    subjective_assessments: Required[dict[str, SubjectiveAssessment]]
    concern_dismissals: dict[str, ConcernDismissal]


class ScanDiff(TypedDict):
    new: int
    auto_resolved: int
    reopened: int
    total_current: int
    suspect_detectors: list[str]
    chronic_reopeners: list[dict]
    skipped_other_lang: int
    resolved_out_of_scope: int
    ignored: int
    ignore_patterns: int
    raw_issues: int
    suppressed_pct: float
    skipped: NotRequired[int]
    skipped_details: NotRequired[list[dict]]


STATE_DIR = PROJECT_ROOT / ".desloppify"
STATE_FILE = STATE_DIR / "state.json"
CURRENT_VERSION = 1


def utc_now() -> str:
    """Return current UTC timestamp with second-level precision."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def empty_state() -> StateModel:
    """Return a new empty state payload."""
    return {
        "version": CURRENT_VERSION,
        "created": utc_now(),
        "last_scan": None,
        "scan_count": 0,
        "overall_score": 0,
        "objective_score": 0,
        "strict_score": 0,
        "verified_strict_score": 0,
        "stats": {},
        "issues": {},
        "scan_coverage": {},
        "score_confidence": {},
        "subjective_integrity": {},
        "subjective_assessments": {},
    }


def _as_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else 0


def migrate_state_keys(state: dict) -> None:
    """Migrate legacy key names in-place.

    - ``"findings"`` → ``"issues"``
    - ``dimension_scores[dim]["issues"]`` → ``"failing"``
    """
    # Legacy "findings" key → "issues"
    if "findings" in state and "issues" not in state:
        state["issues"] = state.pop("findings")
    elif "findings" in state:
        # Both present — prefer "issues", drop legacy key
        state.pop("findings", None)

    # Legacy dimension_scores "issues" → "failing"
    for ds in state.get("dimension_scores", {}).values():
        if isinstance(ds, dict) and "issues" in ds and "failing" not in ds:
            ds["failing"] = ds.pop("issues")
        elif isinstance(ds, dict) and "issues" in ds:
            ds.pop("issues", None)

    # Also migrate inside scan_history entries
    for entry in state.get("scan_history", []):
        if not isinstance(entry, dict):
            continue
        # Legacy "raw_findings" → "raw_issues"
        if "raw_findings" in entry and "raw_issues" not in entry:
            entry["raw_issues"] = entry.pop("raw_findings")
        elif "raw_findings" in entry:
            entry.pop("raw_findings", None)
        dim_scores = entry.get("dimension_scores")
        if isinstance(dim_scores, dict):
            for ds in dim_scores.values():
                if isinstance(ds, dict) and "issues" in ds and "failing" not in ds:
                    ds["failing"] = ds.pop("issues")
                elif isinstance(ds, dict) and "issues" in ds:
                    ds.pop("issues", None)


def ensure_state_defaults(state: StateModel | dict) -> None:
    """Normalize loose/legacy state payloads to a valid base shape in-place."""
    migrate_state_keys(state)

    for key, value in empty_state().items():
        state.setdefault(key, value)

    if not isinstance(state.get("issues"), dict):
        state["issues"] = {}
    if not isinstance(state.get("stats"), dict):
        state["stats"] = {}
    if not isinstance(state.get("scan_history"), list):
        state["scan_history"] = []
    if not isinstance(state.get("scan_coverage"), dict):
        state["scan_coverage"] = {}
    if not isinstance(state.get("score_confidence"), dict):
        state["score_confidence"] = {}
    if not isinstance(state.get("subjective_integrity"), dict):
        state["subjective_integrity"] = {}

    all_issues = state["issues"]
    to_remove: list[str] = []
    for issue_id, issue in all_issues.items():
        if not isinstance(issue, dict):
            to_remove.append(issue_id)
            continue

        issue.setdefault("id", issue_id)
        issue.setdefault("detector", "unknown")
        issue.setdefault("file", "")
        issue.setdefault("tier", 3)
        issue.setdefault("confidence", "low")
        issue.setdefault("summary", "")
        issue.setdefault("detail", {})
        issue.setdefault("status", "open")
        issue["status"] = canonical_issue_status(
            issue.get("status"),
            default="open",
        )
        issue.setdefault("note", None)
        issue.setdefault("first_seen", state.get("created") or utc_now())
        issue.setdefault("last_seen", issue["first_seen"])
        issue.setdefault("resolved_at", None)
        issue["reopen_count"] = _as_non_negative_int(
            issue.get("reopen_count", 0), default=0
        )
        issue.setdefault("suppressed", False)
        issue.setdefault("suppressed_at", None)
        issue.setdefault("suppression_pattern", None)

    for issue_id in to_remove:
        all_issues.pop(issue_id, None)

    for entry in state["scan_history"]:
        if not isinstance(entry, dict):
            continue
        integrity = entry.get("subjective_integrity")
        if integrity is not None and not isinstance(integrity, dict):
            entry["subjective_integrity"] = None

    state["scan_count"] = _as_non_negative_int(state.get("scan_count", 0), default=0)
    return None


def validate_state_invariants(state: StateModel) -> None:
    """Raise ValueError when core state invariants are violated."""
    if not isinstance(state.get("issues"), dict):
        raise ValueError("state.issues must be a dict")
    if not isinstance(state.get("stats"), dict):
        raise ValueError("state.stats must be a dict")

    all_issues = state["issues"]
    for issue_id, issue in all_issues.items():
        if not isinstance(issue, dict):
            raise ValueError(f"issue {issue_id!r} must be a dict")
        if issue.get("id") != issue_id:
            raise ValueError(f"issue id mismatch for {issue_id!r}")
        if issue.get("status") not in _ALLOWED_ISSUE_STATUSES:
            raise ValueError(
                f"issue {issue_id!r} has invalid status {issue.get('status')!r}"
            )

        tier = issue.get("tier")
        if not isinstance(tier, int) or tier < 1 or tier > 4:
            raise ValueError(f"issue {issue_id!r} has invalid tier {tier!r}")

        reopen_count = issue.get("reopen_count")
        if not isinstance(reopen_count, int) or reopen_count < 0:
            raise ValueError(
                f"issue {issue_id!r} has invalid reopen_count {reopen_count!r}"
            )


