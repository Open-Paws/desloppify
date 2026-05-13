"""Helpers for per-language scan and status views."""

from __future__ import annotations

from pathlib import Path

from desloppify.base.discovery.paths import get_project_root
from desloppify.languages.framework import available_langs, get_lang
from desloppify.state_scoring import score_snapshot


def detect_present_languages(path: Path) -> list[str]:
    """Return registered languages that have source files under *path*."""
    detected: list[tuple[str, int]] = []
    for lang_name in available_langs():
        try:
            lang = get_lang(lang_name)
            finder = getattr(lang, "file_finder", None)
            count = len(finder(path)) if finder else 0
        except (OSError, ValueError, RuntimeError, AttributeError):
            continue
        if count > 0:
            detected.append((lang_name, count))
    return [name for name, _count in sorted(detected, key=lambda item: (-item[1], item[0]))]


def language_state_path(lang_name: str) -> Path:
    return get_project_root() / ".desloppify" / f"state-{lang_name}.json"


def language_score_row(lang_name: str, state: dict) -> dict[str, object]:
    scores = score_snapshot(state)
    stats = state.get("stats", {}) if isinstance(state.get("stats"), dict) else {}
    open_count = int(stats.get("open", 0) or 0)
    return {
        "language": lang_name,
        "overall_score": scores.overall,
        "objective_score": scores.objective,
        "strict_score": scores.strict,
        "verified_strict_score": scores.verified,
        "open": open_count,
        "scan_count": state.get("scan_count", 0),
        "last_scan": state.get("last_scan"),
        "state_file": str(language_state_path(lang_name)),
    }


def aggregate_language_scores(rows: list[dict[str, object]]) -> dict[str, object] | None:
    """Return an equal-weight average over scanned language states."""
    scanned = [row for row in rows if int(row.get("scan_count", 0) or 0) > 0]
    if not scanned:
        return None

    def avg(key: str) -> float:
        values = [float(row.get(key, 0.0) or 0.0) for row in scanned]
        return round(sum(values) / len(values), 1)

    return {
        "method": "equal_weight_per_scanned_language",
        "language_count": len(scanned),
        "overall_score": avg("overall_score"),
        "objective_score": avg("objective_score"),
        "strict_score": avg("strict_score"),
        "verified_strict_score": avg("verified_strict_score"),
        "open": sum(int(row.get("open", 0) or 0) for row in scanned),
    }


__all__ = [
    "aggregate_language_scores",
    "detect_present_languages",
    "language_score_row",
    "language_state_path",
]
