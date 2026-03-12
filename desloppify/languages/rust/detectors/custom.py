"""Compatibility exports for legacy Rust detector imports."""

from .api import (
    detect_error_boundaries,
    detect_future_proofing,
    detect_import_hygiene,
    detect_public_api_conventions,
    detect_thread_safety_contracts,
    replace_same_crate_imports,
)
from .cargo_policy import (
    add_missing_features_to_manifest,
    detect_doctest_hygiene,
    detect_feature_hygiene,
    ensure_readme_doctest_harness,
    iter_missing_features,
    missing_readme_doctest_harnesses,
)
from .safety import (
    detect_async_locking,
    detect_drop_safety,
    detect_unsafe_api_usage,
)

__all__ = [
    "add_missing_features_to_manifest",
    "detect_async_locking",
    "detect_doctest_hygiene",
    "detect_drop_safety",
    "detect_error_boundaries",
    "detect_feature_hygiene",
    "detect_future_proofing",
    "detect_import_hygiene",
    "detect_public_api_conventions",
    "detect_thread_safety_contracts",
    "detect_unsafe_api_usage",
    "ensure_readme_doctest_harness",
    "iter_missing_features",
    "missing_readme_doctest_harnesses",
    "replace_same_crate_imports",
]
