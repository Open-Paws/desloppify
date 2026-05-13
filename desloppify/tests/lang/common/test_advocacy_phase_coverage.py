"""Regression: every language config must include the advocacy detector phases.

This was silently broken pre-fix: only javascript and go wired in advocacy
phases manually. All other 9 language configs skipped them, so `desloppify scan`
returned 0 advocacy findings on any non-JS/Go codebase — defeating the fork's
core differentiator.

The fix moved advocacy into shared_subjective_duplicates_tail() so it's
universal. This test guards that wiring.
"""

from __future__ import annotations

import importlib

import pytest

ADVOCACY_LABELS = {"Advocacy language", "Advocacy security", "Advocacy tools"}

# Languages with a dedicated LangConfig (vs generic_lang plugins).
_DEDICATED_LANGUAGES = [
    "python",
    "typescript",
    "csharp",
    "cxx",
    "dart",
    "gdscript",
    "go",
    "rust",
]


@pytest.mark.parametrize("lang_name", _DEDICATED_LANGUAGES)
def test_dedicated_lang_config_includes_advocacy_phases(lang_name: str) -> None:
    mod = importlib.import_module(f"desloppify.languages.{lang_name}")
    cfg = mod.Config()
    phase_labels = {p.label for p in cfg.phases}
    missing = ADVOCACY_LABELS - phase_labels
    assert not missing, (
        f"language '{lang_name}' is missing advocacy phases: {sorted(missing)}. "
        "All Open Paws-fork language configs must include the advocacy phases "
        "via shared_subjective_duplicates_tail()."
    )


def test_generic_lang_plugin_includes_advocacy_phases() -> None:
    """generic_lang (used by javascript + 18 other languages) also gets advocacy."""
    from desloppify.languages._framework.generic_support.core import generic_lang
    cfg = generic_lang(
        name="_test_advocacy_generic",
        extensions=[".x"],
        tools=[{"label": "t", "cmd": "echo", "fmt": "gnu", "id": "test_adv_det", "tier": 2}],
    )
    phase_labels = {p.label for p in cfg.phases}
    missing = ADVOCACY_LABELS - phase_labels
    assert not missing, (
        f"generic_lang is missing advocacy phases: {sorted(missing)}"
    )
