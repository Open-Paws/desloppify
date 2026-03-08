"""Shared subjective-dimension metadata used by scoring and review layers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import lru_cache

from desloppify.base.text_utils import is_numeric
from desloppify.languages import available_langs as _available_langs

logger = logging.getLogger(__name__)

DISPLAY_NAMES: dict[str, str] = {
    # Holistic dimensions
    "cross_module_architecture": "Cross-module arch",
    "initialization_coupling": "Init coupling",
    "convention_outlier": "Convention drift",
    "error_consistency": "Error consistency",
    "abstraction_fitness": "Abstraction fit",
    "dependency_health": "Dep health",
    "test_strategy": "Test strategy",
    "api_surface_coherence": "API coherence",
    "authorization_consistency": "Auth consistency",
    "ai_generated_debt": "AI generated debt",
    "incomplete_migration": "Stale migration",
    "package_organization": "Structure nav",
    "high_level_elegance": "High elegance",
    "mid_level_elegance": "Mid elegance",
    "low_level_elegance": "Low elegance",
    # Design coherence (concerns bridge)
    "design_coherence": "Design coherence",
    # Per-file review dimensions
    "naming_quality": "Naming quality",
    "logic_clarity": "Logic clarity",
    "type_safety": "Type safety",
    "contract_coherence": "Contracts",
}

_LEGACY_DISPLAY_NAMES: dict[str, str] = DISPLAY_NAMES

_LEGACY_SUBJECTIVE_WEIGHTS_BY_DISPLAY: dict[str, float] = {
    "high elegance": 22.0,
    "mid elegance": 22.0,
    "low elegance": 12.0,
    "contracts": 12.0,
    "type safety": 12.0,
    "abstraction fit": 8.0,
    "logic clarity": 6.0,
    "structure nav": 5.0,
    "error consistency": 3.0,
    "naming quality": 2.0,
    "ai generated debt": 1.0,
    "design coherence": 10.0,
}

_LEGACY_RESET_ON_SCAN_DIMENSIONS: frozenset[str] = frozenset(
    {
        "naming_quality",
        "error_consistency",
        "abstraction_fitness",
        "logic_clarity",
        "ai_generated_debt",
        "type_safety",
        "contract_coherence",
        "package_organization",
        "high_level_elegance",
        "mid_level_elegance",
        "low_level_elegance",
    }
)

_LEGACY_WEIGHT_BY_DIMENSION: dict[str, float] = {}
for _dimension_key, _display_name in _LEGACY_DISPLAY_NAMES.items():
    _weight = _LEGACY_SUBJECTIVE_WEIGHTS_BY_DISPLAY.get(
        " ".join(_display_name.strip().lower().split())
    )
    if _weight is not None:
        _LEGACY_WEIGHT_BY_DIMENSION[_dimension_key] = _weight


def _normalize_dimension_name(name: str) -> str:
    return "_".join(str(name).strip().lower().replace("-", "_").split())


def _title_display_name(dimension_key: str) -> str:
    return dimension_key.replace("_", " ").title()


def _normalize_lang_name(lang_name: str | None) -> str | None:
    if not isinstance(lang_name, str):
        return None
    cleaned = lang_name.strip().lower()
    return cleaned or None


def _extract_prompt_meta(entry: object) -> dict[str, object]:
    """Extract optional metadata fields from a prompt payload entry."""
    if not isinstance(entry, dict):
        return {}
    meta = entry.get("meta")
    if not isinstance(meta, dict):
        return {}

    out: dict[str, object] = {}
    display_name = meta.get("display_name")
    if isinstance(display_name, str) and display_name.strip():
        out["display_name"] = display_name.strip()

    weight = meta.get("weight")
    if is_numeric(weight):
        out["weight"] = max(0.0, float(weight))

    enabled = meta.get("enabled_by_default")
    if isinstance(enabled, bool):
        out["enabled_by_default"] = enabled

    reset_on_scan = meta.get("reset_on_scan")
    if isinstance(reset_on_scan, bool):
        out["reset_on_scan"] = reset_on_scan

    return out


def _merge_prompt_display_and_weights(
    payload: dict[str, object],
    *,
    prompt_meta: dict[str, object],
    override_existing: bool,
) -> None:
    if "display_name" in prompt_meta and (
        override_existing or "display_name" not in payload
    ):
        payload["display_name"] = prompt_meta["display_name"]
    if "weight" in prompt_meta and (override_existing or "weight" not in payload):
        payload["weight"] = prompt_meta["weight"]
    if "reset_on_scan" in prompt_meta and (
        override_existing or "reset_on_scan" not in payload
    ):
        payload["reset_on_scan"] = prompt_meta["reset_on_scan"]


def _merge_enabled_by_default_flag(
    payload: dict[str, object],
    *,
    prompt_meta: dict[str, object],
    override_existing: bool,
    default_enabled: bool,
) -> None:
    if default_enabled:
        payload["enabled_by_default"] = True
    if "enabled_by_default" not in prompt_meta:
        return
    prompt_enabled = bool(prompt_meta["enabled_by_default"])
    if override_existing:
        payload["enabled_by_default"] = prompt_enabled
        return
    payload["enabled_by_default"] = bool(
        payload.get("enabled_by_default", False) or prompt_enabled
    )


def _normalized_default_dimensions(dimensions: list[str]) -> set[str]:
    return {
        _normalize_dimension_name(dim)
        for dim in dimensions
        if isinstance(dim, str) and dim.strip()
    }


def _merge_dimension_meta(
    target: dict[str, dict[str, object]],
    *,
    dimensions: list[str],
    prompts: dict[str, dict[str, object]],
    override_existing: bool = False,
) -> None:
    defaults = _normalized_default_dimensions(dimensions)

    for raw_dim, entry in prompts.items():
        dim = _normalize_dimension_name(raw_dim)
        if not dim:
            continue

        payload = target.setdefault(dim, {})
        prompt_meta = _extract_prompt_meta(entry)
        _merge_prompt_display_and_weights(
            payload,
            prompt_meta=prompt_meta,
            override_existing=override_existing,
        )
        _merge_enabled_by_default_flag(
            payload,
            prompt_meta=prompt_meta,
            override_existing=override_existing,
            default_enabled=dim in defaults,
        )


def _default_available_languages() -> list[str]:
    try:
        return list(_available_langs())
    except (ImportError, ValueError, TypeError, RuntimeError):
        return []


def _default_load_dimensions_payload() -> tuple[
    list[str], dict[str, dict[str, object]], str
]:
    from desloppify.intelligence.review.dimensions.data import load_dimensions

    return load_dimensions()


def _default_load_dimensions_payload_for_lang(
    lang_name: str,
) -> tuple[list[str], dict[str, dict[str, object]], str]:
    from desloppify.intelligence.review.dimensions.data import (
        load_dimensions_for_lang,
    )

    return load_dimensions_for_lang(lang_name)


class _SubjectiveProviderState:
    def __init__(self) -> None:
        self.available_languages_provider: Callable[[], list[str]] = (
            _default_available_languages
        )
        self.load_dimensions_payload_provider: Callable[
            [], tuple[list[str], dict[str, dict[str, object]], str]
        ] = _default_load_dimensions_payload
        self.load_dimensions_payload_for_lang_provider: Callable[
            [str], tuple[list[str], dict[str, dict[str, object]], str]
        ] = _default_load_dimensions_payload_for_lang


_PROVIDER_STATE = _SubjectiveProviderState()


def _available_languages() -> list[str]:
    return _PROVIDER_STATE.available_languages_provider()


def _load_dimensions_payload() -> tuple[list[str], dict[str, dict[str, object]], str]:
    return _PROVIDER_STATE.load_dimensions_payload_provider()


def _load_dimensions_payload_for_lang(
    lang_name: str,
) -> tuple[list[str], dict[str, dict[str, object]], str]:
    return _PROVIDER_STATE.load_dimensions_payload_for_lang_provider(lang_name)


def _clear_subjective_dimension_caches() -> None:
    default_dimension_keys.cache_clear()
    default_dimension_keys_for_lang.cache_clear()
    load_subjective_dimension_metadata.cache_clear()
    load_subjective_dimension_metadata_for_lang.cache_clear()


def configure_subjective_dimension_providers(
    *,
    available_languages_provider: Callable[[], list[str]] | None = None,
    load_dimensions_payload_provider: Callable[
        [], tuple[list[str], dict[str, dict[str, object]], str]
    ]
    | None = None,
    load_dimensions_payload_for_lang_provider: Callable[
        [str], tuple[list[str], dict[str, dict[str, object]], str]
    ]
    | None = None,
) -> None:
    """Configure metadata providers for subjective-dimension lookups."""
    state = _PROVIDER_STATE

    changed = False
    if (
        available_languages_provider is not None
        and available_languages_provider is not state.available_languages_provider
    ):
        state.available_languages_provider = available_languages_provider
        changed = True
    if (
        load_dimensions_payload_provider is not None
        and load_dimensions_payload_provider
        is not state.load_dimensions_payload_provider
    ):
        state.load_dimensions_payload_provider = load_dimensions_payload_provider
        changed = True
    if (
        load_dimensions_payload_for_lang_provider is not None
        and load_dimensions_payload_for_lang_provider
        is not state.load_dimensions_payload_for_lang_provider
    ):
        state.load_dimensions_payload_for_lang_provider = (
            load_dimensions_payload_for_lang_provider
        )
        changed = True

    if changed:
        _clear_subjective_dimension_caches()


def reset_subjective_dimension_providers() -> None:
    """Reset metadata providers to built-in defaults."""
    configure_subjective_dimension_providers(
        available_languages_provider=_default_available_languages,
        load_dimensions_payload_provider=_default_load_dimensions_payload,
        load_dimensions_payload_for_lang_provider=_default_load_dimensions_payload_for_lang,
    )


def _normalize_dimension_list(values: list[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw in values:
        if not isinstance(raw, str):
            continue
        dim = _normalize_dimension_name(raw)
        if not dim or dim in normalized:
            continue
        normalized.append(dim)
    return tuple(normalized)


@lru_cache(maxsize=1)
def default_dimension_keys() -> tuple[str, ...]:
    """Return canonical default subjective dimension keys."""
    try:
        dims, _, _ = _load_dimensions_payload()
    except (ImportError, ValueError, RuntimeError) as exc:
        logger.debug("Failed to load default subjective dimensions: %s", exc)
        return tuple(_LEGACY_DISPLAY_NAMES.keys())
    return _normalize_dimension_list(dims)


@lru_cache(maxsize=16)
def default_dimension_keys_for_lang(lang_name: str | None) -> tuple[str, ...]:
    """Return default subjective dimension keys for a specific language."""
    normalized = _normalize_lang_name(lang_name)
    if normalized is None:
        return default_dimension_keys()
    try:
        dims, _, _ = _load_dimensions_payload_for_lang(normalized)
    except (ImportError, ValueError, RuntimeError) as exc:
        logger.debug(
            "Failed to load subjective dimensions for lang %s: %s",
            normalized,
            exc,
        )
        return default_dimension_keys()
    return _normalize_dimension_list(dims)


def _build_subjective_dimension_metadata(
    *,
    lang_name: str | None,
) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}

    try:
        shared_defaults, shared_prompts, _ = _load_dimensions_payload()
    except (ImportError, ValueError, RuntimeError) as exc:
        logger.debug("Failed to load shared subjective dimension payload: %s", exc)
        shared_defaults, shared_prompts = [], {}
    _merge_dimension_meta(out, dimensions=shared_defaults, prompts=shared_prompts)

    langs = (
        [lang_name]
        if isinstance(lang_name, str) and lang_name.strip()
        else _available_languages()
    )
    for name in langs:
        try:
            lang_defaults, lang_prompts, _ = _load_dimensions_payload_for_lang(name)
            _merge_dimension_meta(
                out,
                dimensions=lang_defaults,
                prompts=lang_prompts,
                override_existing=bool(lang_name),
            )
        except (ValueError, RuntimeError) as exc:
            logger.debug("Failed to load dimensions for lang %s: %s", name, exc)
            continue

    for dim, payload in out.items():
        payload.setdefault(
            "display_name",
            _LEGACY_DISPLAY_NAMES.get(dim, _title_display_name(dim)),
        )
        payload.setdefault("weight", _LEGACY_WEIGHT_BY_DIMENSION.get(dim, 1.0))
        payload.setdefault("enabled_by_default", False)
        if dim in _LEGACY_DISPLAY_NAMES:
            payload.setdefault("reset_on_scan", dim in _LEGACY_RESET_ON_SCAN_DIMENSIONS)
        else:
            payload.setdefault("reset_on_scan", True)

    # Preserve legacy dimensions even if a payload temporarily drops one.
    for dim, display in _LEGACY_DISPLAY_NAMES.items():
        payload = out.setdefault(dim, {})
        payload.setdefault("display_name", display)
        payload.setdefault("weight", _LEGACY_WEIGHT_BY_DIMENSION.get(dim, 1.0))
        payload.setdefault("enabled_by_default", True)
        payload.setdefault("reset_on_scan", dim in _LEGACY_RESET_ON_SCAN_DIMENSIONS)

    return out


@lru_cache(maxsize=1)
def load_subjective_dimension_metadata() -> dict[str, dict[str, object]]:
    """Return merged metadata across all known dimensions/languages."""
    return _build_subjective_dimension_metadata(lang_name=None)


@lru_cache(maxsize=16)
def load_subjective_dimension_metadata_for_lang(
    lang_name: str | None,
) -> dict[str, dict[str, object]]:
    """Return merged metadata for one language (with language overrides)."""
    normalized = _normalize_lang_name(lang_name)
    return _build_subjective_dimension_metadata(lang_name=normalized)


def _metadata_registry(lang_name: str | None) -> dict[str, dict[str, object]]:
    normalized = _normalize_lang_name(lang_name)
    if normalized is None:
        return load_subjective_dimension_metadata()
    return load_subjective_dimension_metadata_for_lang(normalized)


def get_dimension_metadata(
    dimension_name: str, *, lang_name: str | None = None
) -> dict[str, object]:
    """Return metadata for one dimension key (with sane defaults)."""
    dim = _normalize_dimension_name(dimension_name)
    all_meta = _metadata_registry(lang_name)
    payload = dict(all_meta.get(dim, {}))

    payload.setdefault("display_name", _title_display_name(dim))
    payload.setdefault("weight", 1.0)
    payload.setdefault("enabled_by_default", False)
    payload.setdefault("reset_on_scan", True)
    return payload


def dimension_display_name(dimension_name: str, *, lang_name: str | None = None) -> str:
    meta = get_dimension_metadata(dimension_name, lang_name=lang_name)
    return str(meta.get("display_name", _title_display_name(dimension_name)))


def dimension_weight(dimension_name: str, *, lang_name: str | None = None) -> float:
    meta = get_dimension_metadata(dimension_name, lang_name=lang_name)
    raw = meta.get("weight", 1.0)
    if is_numeric(raw):
        return max(0.0, float(raw))
    return 1.0


def default_display_names_map(*, lang_name: str | None = None) -> dict[str, str]:
    """Display-name map for default subjective dimensions."""
    out: dict[str, str] = {}
    for dim, payload in _metadata_registry(lang_name).items():
        if not bool(payload.get("enabled_by_default", False)):
            continue
        out[dim] = str(payload.get("display_name", _title_display_name(dim)))
    return out


def resettable_default_dimensions(*, lang_name: str | None = None) -> tuple[str, ...]:
    """Default subjective dimensions that should be reset by scan reset."""
    out = []
    for dim, payload in _metadata_registry(lang_name).items():
        if not bool(payload.get("enabled_by_default", False)):
            continue
        if not bool(payload.get("reset_on_scan", True)):
            continue
        out.append(dim)
    return tuple(sorted(set(out)))


__all__ = [
    "DISPLAY_NAMES",
    "configure_subjective_dimension_providers",
    "default_dimension_keys",
    "default_dimension_keys_for_lang",
    "default_display_names_map",
    "dimension_display_name",
    "dimension_weight",
    "get_dimension_metadata",
    "load_subjective_dimension_metadata",
    "load_subjective_dimension_metadata_for_lang",
    "reset_subjective_dimension_providers",
    "resettable_default_dimensions",
]
