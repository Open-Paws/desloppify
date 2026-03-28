"""Direct coverage for subjective-dimension helper modules."""

from __future__ import annotations

from desloppify.base import subjective_dimensions_constants as constants_mod
from desloppify.base import subjective_dimensions as metadata_mod
from desloppify.base import subjective_dimensions_merge as merge_mod
from desloppify.base import subjective_dimensions_providers as providers_mod
from desloppify.intelligence.review.dimensions import data as dimensions_data


def test_constants_exports_and_helpers_normalize_values() -> None:
    assert constants_mod.LEGACY_DISPLAY_NAMES is constants_mod.DISPLAY_NAMES
    assert constants_mod.LEGACY_WEIGHT_BY_DIMENSION["high_level_elegance"] == 22.0
    assert constants_mod.LEGACY_WEIGHT_BY_DIMENSION["design_coherence"] == 10.0
    assert (
        "cross_module_architecture" not in constants_mod.LEGACY_WEIGHT_BY_DIMENSION
    )

    assert constants_mod.normalize_dimension_name("  Foo-Bar  Baz ") == "foo_bar_baz"
    assert constants_mod.title_display_name("high_level_elegance") == (
        "High Level Elegance"
    )
    assert constants_mod.normalize_lang_name(None) is None
    assert constants_mod.normalize_lang_name("   ") is None
    assert constants_mod.normalize_lang_name(" PyTHon ") == "python"


def test_extract_prompt_meta_filters_invalid_and_normalizes_values() -> None:
    assert merge_mod.extract_prompt_meta(None) == {}
    assert merge_mod.extract_prompt_meta({"meta": []}) == {}

    meta = merge_mod.extract_prompt_meta(
        {
                "meta": {
                    "display_name": "  Better Name  ",
                    "weight": -2.5,
                    "enabled_by_default": True,
                    "reset_on_scan": False,
                }
            }
        )

    assert meta == {
        "display_name": "Better Name",
        "weight": 0.0,
        "enabled_by_default": True,
        "reset_on_scan": False,
    }


def test_merge_prompt_meta_helpers_respect_override_rules() -> None:
    payload: dict[str, object] = {"display_name": "Old", "weight": 9.0}
    prompt_meta: dict[str, object] = {
        "display_name": "New",
        "weight": 1.5,
        "enabled_by_default": True,
        "reset_on_scan": False,
    }

    merge_mod.merge_prompt_display_and_weights(
        payload,
        prompt_meta=prompt_meta,
        override_existing=False,
    )
    assert payload["display_name"] == "Old"
    assert payload["weight"] == 9.0
    assert payload["reset_on_scan"] is False

    merge_mod.merge_enabled_by_default_flag(
        payload,
        prompt_meta=prompt_meta,
        override_existing=False,
        default_enabled=False,
    )
    assert payload["enabled_by_default"] is True

    merge_mod.merge_enabled_by_default_flag(
        payload,
        prompt_meta={"enabled_by_default": False},
        override_existing=True,
        default_enabled=True,
    )
    assert payload["enabled_by_default"] is False


def test_merge_dimension_meta_normalizes_and_merges_defaults() -> None:
    target: dict[str, dict[str, object]] = {"existing_dim": {"display_name": "Keep Me"}}
    prompts = {
        "existing dim": {"meta": {"display_name": "Overwrite", "weight": 5}},
        "new-dim": {
            "meta": {
                "display_name": "New Dim",
                "weight": 2,
                "enabled_by_default": True,
                "reset_on_scan": False,
            }
        },
    }

    merge_mod.merge_dimension_meta(
        target,
        dimensions=[" existing-dim ", "new dim", ""],
        prompts=prompts,
        override_existing=False,
    )

    assert target["existing_dim"]["display_name"] == "Keep Me"
    assert target["existing_dim"]["enabled_by_default"] is True
    assert target["new_dim"] == {
        "display_name": "New Dim",
        "weight": 2.0,
        "enabled_by_default": True,
        "reset_on_scan": False,
    }
    assert merge_mod.normalized_default_dimensions([" A ", "a", "", "B"]) == {"a", "b"}

    merge_mod.merge_dimension_meta(
        target,
        dimensions=["existing_dim"],
        prompts={"existing_dim": {"meta": {"display_name": "Overwrite", "weight": 5}}},
        override_existing=True,
    )
    assert target["existing_dim"]["display_name"] == "Overwrite"
    assert target["existing_dim"]["weight"] == 5.0


def test_providers_default_available_languages_handles_errors(monkeypatch) -> None:
    monkeypatch.setattr(providers_mod, "_available_langs", lambda: ("py", "ts"))
    assert providers_mod.default_available_languages() == ["py", "ts"]

    def _boom() -> list[str]:
        raise RuntimeError("failed")

    monkeypatch.setattr(providers_mod, "_available_langs", _boom)
    assert providers_mod.default_available_languages() == []


def test_providers_default_payload_loaders_use_dimensions_data(monkeypatch) -> None:
    expected_shared = (
        ["naming_quality"],
        {"naming_quality": {"meta": {"display_name": "Naming"}}},
        "shared",
    )
    expected_lang = (
        ["logic_clarity"],
        {"logic_clarity": {"meta": {"display_name": "Logic"}}},
        "python",
    )

    monkeypatch.setattr(dimensions_data, "load_dimensions", lambda: expected_shared)
    monkeypatch.setattr(
        dimensions_data,
        "load_dimensions_for_lang",
        lambda lang: expected_lang if lang == "python" else expected_shared,
    )

    assert providers_mod.default_load_dimensions_payload() == expected_shared
    assert providers_mod.default_load_dimensions_payload_for_lang("python") == (
        expected_lang
    )


def test_provider_state_and_wrappers_delegate_to_configured_callables(
    monkeypatch,
) -> None:
    state = providers_mod.SubjectiveProviderState()
    assert state.available_languages_provider is providers_mod.default_available_languages
    assert (
        state.load_dimensions_payload_provider
        is providers_mod.default_load_dimensions_payload
    )
    assert (
        state.load_dimensions_payload_for_lang_provider
        is providers_mod.default_load_dimensions_payload_for_lang
    )

    monkeypatch.setattr(
        providers_mod.PROVIDER_STATE,
        "available_languages_provider",
        lambda: ["stub"],
    )
    monkeypatch.setattr(
        providers_mod.PROVIDER_STATE,
        "load_dimensions_payload_provider",
        lambda: (["a"], {}, "stub"),
    )
    monkeypatch.setattr(
        providers_mod.PROVIDER_STATE,
        "load_dimensions_payload_for_lang_provider",
        lambda lang: ([lang], {}, "stub-lang"),
    )

    assert providers_mod.available_languages() == ["stub"]
    assert providers_mod.load_dimensions_payload() == (["a"], {}, "stub")
    assert providers_mod.load_dimensions_payload_for_lang("py") == (
        ["py"],
        {},
        "stub-lang",
    )


def test_configure_and_reset_providers_updates_provider_state() -> None:
    metadata_mod.reset_subjective_dimension_providers()
    try:
        metadata_mod.configure_subjective_dimension_providers(
            available_languages_provider=lambda: ["xlang"],
            load_dimensions_payload_provider=lambda: (["dim_x"], {}, "x"),
            load_dimensions_payload_for_lang_provider=lambda lang: ([lang], {}, "xlang"),
        )
        assert providers_mod.available_languages() == ["xlang"]
        assert providers_mod.load_dimensions_payload() == (["dim_x"], {}, "x")
        assert providers_mod.load_dimensions_payload_for_lang("py") == (
            ["py"],
            {},
            "xlang",
        )
    finally:
        metadata_mod.reset_subjective_dimension_providers()
