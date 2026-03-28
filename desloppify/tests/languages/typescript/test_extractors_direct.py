"""Direct tests for TypeScript extractor entrypoint wrappers."""

from __future__ import annotations

from pathlib import Path

import desloppify.languages.typescript.extractors as extractors_mod


def test_function_wrapper_entrypoints_delegate_to_functions_module(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        extractors_mod.functions_mod,
        "extract_ts_functions",
        lambda filepath: calls.append(("extract_ts_functions", filepath)) or ["fn"],
    )
    monkeypatch.setattr(
        extractors_mod.functions_mod,
        "normalize_ts_body",
        lambda body: calls.append(("normalize_ts_body", body)) or "normalized",
    )
    monkeypatch.setattr(
        extractors_mod.functions_mod,
        "_extract_ts_params",
        lambda sig: calls.append(("_extract_ts_params", sig)) or ["a", "b"],
    )
    monkeypatch.setattr(
        extractors_mod.functions_mod,
        "_parse_param_names",
        lambda params: calls.append(("_parse_param_names", params)) or ["x"],
    )

    assert extractors_mod.extract_ts_functions("file.ts") == ["fn"]
    assert extractors_mod.normalize_ts_body("body") == "normalized"
    assert extractors_mod._extract_ts_params("(a, b)") == ["a", "b"]
    assert extractors_mod._parse_param_names("x: string") == ["x"]
    assert calls == [
        ("extract_ts_functions", "file.ts"),
        ("normalize_ts_body", "body"),
        ("_extract_ts_params", "(a, b)"),
        ("_parse_param_names", "x: string"),
    ]


def test_component_wrapper_entrypoints_delegate_to_components_module(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        extractors_mod.components_mod,
        "extract_ts_components",
        lambda path: calls.append(("extract_ts_components", path)) or ["component"],
    )
    monkeypatch.setattr(
        extractors_mod.components_mod,
        "extract_props",
        lambda payload: calls.append(("extract_props", payload)) or ["prop"],
    )
    monkeypatch.setattr(
        extractors_mod.components_mod,
        "tsx_passthrough_pattern",
        lambda name: calls.append(("tsx_passthrough_pattern", name)) or "pattern",
    )
    monkeypatch.setattr(
        extractors_mod.components_mod,
        "detect_passthrough_components",
        lambda path: calls.append(("detect_passthrough_components", path)) or [{"name": "A"}],
    )

    path = Path("widget.tsx")
    assert extractors_mod.extract_ts_components(path) == ["component"]
    assert extractors_mod.extract_props("{ a, b }") == ["prop"]
    assert extractors_mod.tsx_passthrough_pattern("Comp") == "pattern"
    assert extractors_mod.detect_passthrough_components(path) == [{"name": "A"}]
    assert calls == [
        ("extract_ts_components", path),
        ("extract_props", "{ a, b }"),
        ("tsx_passthrough_pattern", "Comp"),
        ("detect_passthrough_components", path),
    ]
