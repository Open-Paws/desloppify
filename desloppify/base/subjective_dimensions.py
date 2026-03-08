"""Public subjective-dimension metadata API.

This thin module preserves the long-standing import path while the full
implementation lives in ``subjective_dimensions_core``.
"""

from __future__ import annotations

from desloppify.base.subjective_dimensions_core import (
    DISPLAY_NAMES,
    configure_subjective_dimension_providers,
    default_dimension_keys,
    default_dimension_keys_for_lang,
    default_display_names_map,
    dimension_display_name,
    dimension_weight,
    get_dimension_metadata,
    load_subjective_dimension_metadata,
    load_subjective_dimension_metadata_for_lang,
    reset_subjective_dimension_providers,
    resettable_default_dimensions,
)

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
