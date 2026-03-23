"""Sparkline helpers for terminal score progression."""

from __future__ import annotations

from typing import Any

BLOCKS = "▁▂▃▄▅▆▇█"
_FLAT_BLOCK = BLOCKS[3]


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _resample(values: list[float], width: int) -> list[float]:
    if width <= 0 or not values:
        return []
    if len(values) <= width or width == 1:
        return values[:width]

    last_index = len(values) - 1
    scale = last_index / (width - 1)
    result: list[float] = []
    for idx in range(width):
        position = idx * scale
        left = int(position)
        right = min(left + 1, last_index)
        fraction = position - left
        interpolated = values[left] + (values[right] - values[left]) * fraction
        result.append(interpolated)
    return result


def _smooth(values: list[float], window: int = 3) -> list[float]:
    """Simple moving average to reduce noise."""
    if len(values) <= window:
        return values
    result: list[float] = []
    half = window // 2
    for i in range(len(values)):
        start = max(0, i - half)
        end = min(len(values), i + half + 1)
        result.append(sum(values[start:end]) / (end - start))
    return result


def render_sparkline(scores: list[float], width: int = 20) -> str:
    """Render a compact strict-score trend line."""
    if len(scores) < 3 or width <= 0:
        return ""

    values = _smooth(_resample([float(score) for score in scores], width))
    if len(values) < 3:
        return ""

    low = min(values)
    high = max(values)
    span = high - low
    if span < 0.01:
        return _FLAT_BLOCK * len(values)

    max_level = len(BLOCKS) - 1
    chars: list[str] = []
    for value in values:
        normalized = (value - low) / span
        level = min(max_level, int(round(normalized * max_level)))
        chars.append(BLOCKS[level])
    return "".join(chars)


def extract_strict_trend(events: list[dict[str, Any]]) -> list[float]:
    """Extract valid strict-score checkpoints from progression events."""
    trend: list[float] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event_type") != "plan_checkpoint":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        scores = payload.get("scores")
        if not isinstance(scores, dict):
            continue
        strict_score = _to_float(scores.get("strict"))
        if strict_score is None:
            continue
        trend.append(strict_score)
    return trend

__all__ = ["extract_strict_trend", "render_sparkline"]
