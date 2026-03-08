"""Health score aggregation helpers."""

from __future__ import annotations

from typing import TypedDict

from desloppify.base.text_utils import is_numeric
from desloppify.engine._scoring.policy.core import (
    MECHANICAL_DIMENSION_WEIGHTS,
    MECHANICAL_WEIGHT_FRACTION,
    MIN_SAMPLE,
    SUBJECTIVE_DIMENSION_WEIGHTS,
    SUBJECTIVE_WEIGHT_FRACTION,
)


class HealthBreakdownEntry(TypedDict):
    """Per-dimension contribution row used in score transparency output."""

    name: str
    pool: str
    score: float
    checks: float
    sample_factor: float
    configured_weight: float
    effective_weight: float
    pool_share: float
    overall_per_point: float
    overall_contribution: float
    overall_drag: float


class HealthBreakdown(TypedDict):
    """Typed shape returned by ``compute_health_breakdown``."""

    overall_score: float
    mechanical_fraction: float
    subjective_fraction: float
    mechanical_avg: float
    subjective_avg: float | None
    entries: list[HealthBreakdownEntry]


def _normalize_dimension_name(name: str) -> str:
    return " ".join(str(name).strip().lower().split())


def _mechanical_dimension_weight(name: str) -> float:
    return float(
        MECHANICAL_DIMENSION_WEIGHTS.get(
            _normalize_dimension_name(name),
            1.0,
        )
    )


def _subjective_dimension_weight(name: str, data: dict) -> float:
    subjective_meta = (
        data.get("detectors", {}).get("subjective_assessment", {})
        if isinstance(data, dict)
        else {}
    )
    configured = (
        subjective_meta.get("configured_weight")
        if isinstance(subjective_meta, dict)
        else None
    )
    if is_numeric(configured):
        return max(0.0, float(configured))

    return float(
        SUBJECTIVE_DIMENSION_WEIGHTS.get(
            _normalize_dimension_name(name),
            1.0,
        )
    )


def compute_health_breakdown(
    dimension_scores: dict,
    *,
    score_key: str = "score",
) -> HealthBreakdown:
    """Return pool averages and weighted contribution breakdown for score transparency."""
    if not dimension_scores:
        return {
            "overall_score": 100.0,
            "mechanical_fraction": 1.0,
            "subjective_fraction": 0.0,
            "mechanical_avg": 100.0,
            "subjective_avg": None,
            "entries": [],
        }

    mech_sum = 0.0
    mech_weight = 0.0
    subj_sum = 0.0
    subj_weight = 0.0
    mechanical_rows: list[dict[str, float | str]] = []
    subjective_rows: list[dict[str, float | str]] = []

    for name, data in dimension_scores.items():
        score = float(data.get(score_key, data.get("score", 0.0)))
        is_subjective = "subjective_assessment" in data.get("detectors", {})
        if is_subjective:
            configured = max(0.0, _subjective_dimension_weight(name, data))
            effective = configured
            subj_sum += score * effective
            subj_weight += effective
            subjective_rows.append(
                {
                    "name": str(name),
                    "score": score,
                    "configured_weight": configured,
                    "effective_weight": effective,
                }
            )
            continue

        checks = float(data.get("checks", 0) or 0)
        sample_factor = min(1.0, checks / MIN_SAMPLE) if checks > 0 else 0.0
        configured = max(0.0, _mechanical_dimension_weight(name))
        effective = configured * sample_factor
        mech_sum += score * effective
        mech_weight += effective
        mechanical_rows.append(
            {
                "name": str(name),
                "score": score,
                "checks": checks,
                "sample_factor": sample_factor,
                "configured_weight": configured,
                "effective_weight": effective,
            }
        )

    mech_avg = (mech_sum / mech_weight) if mech_weight > 0 else 100.0
    subj_avg = (subj_sum / subj_weight) if subj_weight > 0 else None

    if subj_avg is None:
        mechanical_fraction = 1.0
        subjective_fraction = 0.0
        overall_score = round(mech_avg, 1)
    elif mech_weight == 0:
        mechanical_fraction = 0.0
        subjective_fraction = 1.0
        overall_score = round(subj_avg, 1)
    else:
        mechanical_fraction = MECHANICAL_WEIGHT_FRACTION
        subjective_fraction = SUBJECTIVE_WEIGHT_FRACTION
        overall_score = round(
            mech_avg * mechanical_fraction + subj_avg * subjective_fraction,
            1,
        )

    entries: list[HealthBreakdownEntry] = []
    for row in mechanical_rows:
        pool_share = (
            float(row["effective_weight"]) / mech_weight if mech_weight > 0 else 0.0
        )
        per_point = mechanical_fraction * pool_share
        score = float(row["score"])
        entries.append(
            {
                "name": str(row["name"]),
                "pool": "mechanical",
                "score": score,
                "checks": float(row["checks"]),
                "sample_factor": float(row["sample_factor"]),
                "configured_weight": float(row["configured_weight"]),
                "effective_weight": float(row["effective_weight"]),
                "pool_share": pool_share,
                "overall_per_point": per_point,
                "overall_contribution": per_point * score,
                "overall_drag": per_point * (100.0 - score),
            }
        )

    for row in subjective_rows:
        pool_share = (
            float(row["effective_weight"]) / subj_weight if subj_weight > 0 else 0.0
        )
        per_point = subjective_fraction * pool_share
        score = float(row["score"])
        entries.append(
            {
                "name": str(row["name"]),
                "pool": "subjective",
                "score": score,
                "checks": 0.0,
                "sample_factor": 1.0,
                "configured_weight": float(row["configured_weight"]),
                "effective_weight": float(row["effective_weight"]),
                "pool_share": pool_share,
                "overall_per_point": per_point,
                "overall_contribution": per_point * score,
                "overall_drag": per_point * (100.0 - score),
            }
        )

    return {
        "overall_score": overall_score,
        "mechanical_fraction": mechanical_fraction,
        "subjective_fraction": subjective_fraction,
        "mechanical_avg": mech_avg,
        "subjective_avg": subj_avg,
        "entries": entries,
    }


def compute_health_score(
    dimension_scores: dict,
    *,
    score_key: str = "score",
) -> float:
    """Budget-weighted blend of mechanical and subjective dimension scores."""
    return float(
        compute_health_breakdown(dimension_scores, score_key=score_key)[
            "overall_score"
        ]
    )


__all__ = ["compute_health_breakdown", "compute_health_score"]
