"""State mutation helpers for triage stage records."""

from __future__ import annotations

from desloppify.state import utc_now

from .helpers import cascade_clear_later_confirmations


def _resolve_reusable_report(
    report: str | None,
    existing_stage: dict | None,
) -> tuple[str | None, bool]:
    if report:
        return report, False
    if existing_stage and existing_stage.get("report"):
        return existing_stage["report"], True
    return None, False


def _record_observe_stage(
    stages: dict,
    *,
    report: str,
    issue_count: int,
    cited_ids: list[str],
    existing_stage: dict | None,
    is_reuse: bool,
) -> list[str]:
    stages["observe"] = {
        "stage": "observe",
        "report": report,
        "cited_ids": cited_ids,
        "timestamp": utc_now(),
        "issue_count": issue_count,
    }
    if is_reuse and existing_stage and existing_stage.get("confirmed_at"):
        stages["observe"]["confirmed_at"] = existing_stage["confirmed_at"]
        stages["observe"]["confirmed_text"] = existing_stage.get("confirmed_text", "")
    cleared = cascade_clear_later_confirmations(stages, "observe")
    if not is_reuse:
        stages["observe"].pop("confirmed_at", None)
        stages["observe"].pop("confirmed_text", None)
    return cleared


def _record_organize_stage(
    stages: dict,
    *,
    report: str,
    issue_count: int,
    existing_stage: dict | None,
    is_reuse: bool,
) -> list[str]:
    stages["organize"] = {
        "stage": "organize",
        "report": report,
        "cited_ids": [],
        "timestamp": utc_now(),
        "issue_count": issue_count,
    }
    if is_reuse and existing_stage and existing_stage.get("confirmed_at"):
        stages["organize"]["confirmed_at"] = existing_stage["confirmed_at"]
        stages["organize"]["confirmed_text"] = existing_stage.get("confirmed_text", "")
    return cascade_clear_later_confirmations(stages, "organize")


def _record_enrich_stage(
    stages: dict,
    *,
    report: str,
    shallow_count: int,
    existing_stage: dict | None,
    is_reuse: bool,
) -> list[str]:
    stages["enrich"] = {
        "stage": "enrich",
        "report": report,
        "timestamp": utc_now(),
        "shallow_count": shallow_count,
    }
    if is_reuse and existing_stage and existing_stage.get("confirmed_at"):
        stages["enrich"]["confirmed_at"] = existing_stage["confirmed_at"]
        stages["enrich"]["confirmed_text"] = existing_stage.get("confirmed_text", "")
    return cascade_clear_later_confirmations(stages, "enrich")


def _record_confirm_existing_completion(
    *,
    stages: dict,
    note: str,
    issue_count: int,
    confirmed_text: str,
) -> None:
    stages["organize"] = {
        "stage": "organize",
        "report": f"[confirmed-existing] {note}",
        "cited_ids": [],
        "timestamp": utc_now(),
        "issue_count": issue_count,
        "confirmed_at": utc_now(),
        "confirmed_text": confirmed_text,
    }


__all__ = [
    "_record_confirm_existing_completion",
    "_record_enrich_stage",
    "_record_observe_stage",
    "_record_organize_stage",
    "_resolve_reusable_report",
]
