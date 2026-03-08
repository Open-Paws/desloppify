"""Direct tests for legacy subjective metadata helpers."""

from __future__ import annotations

import desloppify.intelligence.review.dimensions.metadata_legacy as legacy_mod
from desloppify.engine._scoring.subjective.core import DISPLAY_NAMES


def test_legacy_display_names_aliases_scoring_display_names() -> None:
    assert legacy_mod.LEGACY_DISPLAY_NAMES is DISPLAY_NAMES
    assert legacy_mod.LEGACY_DISPLAY_NAMES["high_level_elegance"] == "High elegance"


def test_normalize_display_name_for_weight_lookup_collapses_spacing_and_case() -> None:
    normalized = legacy_mod._normalize_display_name_for_weight_lookup("  High   Elegance  ")
    assert normalized == "high elegance"


def test_build_weight_by_dimension_matches_exported_weight_map() -> None:
    rebuilt = legacy_mod._build_weight_by_dimension()
    assert rebuilt == legacy_mod.LEGACY_WEIGHT_BY_DIMENSION
    assert rebuilt["high_level_elegance"] == 22.0
    assert rebuilt["type_safety"] == 12.0
    assert "package_organization" in legacy_mod.LEGACY_RESET_ON_SCAN_DIMENSIONS
