"""Canonical detector registry — single source of truth.

All detector metadata lives here. Other modules derive their views
(display order, CLI names, narrative tools, scoring validation) from this registry
instead of maintaining their own lists.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Set
from dataclasses import dataclass

from desloppify.base.registry_catalog_entries import DETECTORS as _CATALOG_DETECTORS
from desloppify.base.registry_catalog_models import DISPLAY_ORDER, DetectorMeta

_BASE_DETECTORS: dict[str, DetectorMeta] = dict(_CATALOG_DETECTORS)
_BASE_DISPLAY_ORDER: list[str] = list(DISPLAY_ORDER)
_BASE_JUDGMENT_DETECTORS: frozenset[str] = frozenset(
    name for name, meta in _BASE_DETECTORS.items() if meta.needs_judgment
)


@dataclass
class _RegistryRuntime:
    detectors: dict[str, DetectorMeta]
    display_order: list[str]
    callbacks: list[Callable[[], None]]
    judgment_detectors: frozenset[str]


_RUNTIME = _RegistryRuntime(
    detectors=dict(_CATALOG_DETECTORS),
    display_order=list(DISPLAY_ORDER),
    callbacks=[],
    judgment_detectors=frozenset(
        name for name, meta in _CATALOG_DETECTORS.items() if meta.needs_judgment
    ),
)

# Module-level handles into the mutable runtime registry.
DETECTORS = _RUNTIME.detectors
_DISPLAY_ORDER = _RUNTIME.display_order
_on_register_callbacks = _RUNTIME.callbacks


class _JudgmentDetectorsView(Set[str]):
    """Live read-only set view over runtime judgment detector names."""

    def __contains__(self, item: object) -> bool:
        return isinstance(item, str) and item in _RUNTIME.judgment_detectors

    def __iter__(self) -> Iterator[str]:
        return iter(_RUNTIME.judgment_detectors)

    def __len__(self) -> int:
        return len(_RUNTIME.judgment_detectors)


JUDGMENT_DETECTORS: Set[str] = _JudgmentDetectorsView()


def on_detector_registered(callback: Callable[[], None]) -> None:
    """Register a callback invoked after register_detector(). No-arg."""
    _RUNTIME.callbacks.append(callback)


def register_detector(meta: DetectorMeta) -> None:
    """Register a detector at runtime (used by generic plugins)."""
    _RUNTIME.detectors[meta.name] = meta
    if meta.name not in _RUNTIME.display_order:
        _RUNTIME.display_order.append(meta.name)
    _RUNTIME.judgment_detectors = frozenset(
        name for name, current_meta in _RUNTIME.detectors.items()
        if current_meta.needs_judgment
    )
    for callback in tuple(_RUNTIME.callbacks):
        callback()


def reset_registered_detectors() -> None:
    """Reset runtime-added detector registrations to built-in defaults."""
    _RUNTIME.detectors.clear()
    _RUNTIME.detectors.update(_BASE_DETECTORS)
    _RUNTIME.display_order.clear()
    _RUNTIME.display_order.extend(_BASE_DISPLAY_ORDER)
    _RUNTIME.judgment_detectors = _BASE_JUDGMENT_DETECTORS
    for callback in tuple(_RUNTIME.callbacks):
        callback()


def detector_names() -> list[str]:
    """All registered detector names, sorted."""
    return sorted(_RUNTIME.detectors.keys())


def display_order() -> list[str]:
    """Canonical display order for terminal output."""
    return list(_RUNTIME.display_order)


_ACTION_PRIORITY = {"auto_fix": 0, "reorganize": 1, "refactor": 2, "manual_fix": 3}
_ACTION_LABELS = {
    "auto_fix": "autofix",
    "reorganize": "move",
    "refactor": "refactor",
    "manual_fix": "manual",
}


def dimension_action_type(dim_name: str) -> str:
    """Return a compact action type label for a dimension based on its detectors."""
    best = "manual"
    best_priority = 99
    for detector_meta in _RUNTIME.detectors.values():
        if detector_meta.dimension == dim_name:
            priority = _ACTION_PRIORITY.get(detector_meta.action_type, 99)
            if priority < best_priority:
                best_priority = priority
                best = detector_meta.action_type
    return _ACTION_LABELS.get(best, "manual")


def detector_tools() -> dict[str, dict]:
    """Build detector tool metadata keyed by detector name."""
    result = {}
    for detector_name, detector_meta in _RUNTIME.detectors.items():
        entry: dict = {
            "fixers": list(detector_meta.fixers),
            "action_type": detector_meta.action_type,
        }
        if detector_meta.tool:
            entry["tool"] = detector_meta.tool
        if detector_meta.guidance:
            entry["guidance"] = detector_meta.guidance
        result[detector_name] = entry
    return result


__all__ = [
    "DETECTORS",
    "DISPLAY_ORDER",
    "DetectorMeta",
    "JUDGMENT_DETECTORS",
    "_DISPLAY_ORDER",
    "_on_register_callbacks",
    "detector_names",
    "detector_tools",
    "dimension_action_type",
    "display_order",
    "on_detector_registered",
    "register_detector",
    "reset_registered_detectors",
]
