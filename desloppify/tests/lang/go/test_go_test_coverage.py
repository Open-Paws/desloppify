"""Tests for Go-specific coverage import mapping helpers."""

from __future__ import annotations

from desloppify.languages.go import test_coverage as go_cov


def test_resolve_import_spec_matches_relative_package_file():
    production = {"pkg/internal/util.go", "pkg/internal/mapper.go"}
    resolved = go_cov.resolve_import_spec("pkg/internal/util", "pkg/app/app_test.go", production)
    assert resolved == "pkg/internal/util.go"


def test_resolve_import_spec_matches_module_prefixed_path_by_suffix():
    production = {"pkg/service/handler.go"}
    resolved = go_cov.resolve_import_spec(
        "github.com/acme/project/pkg/service/handler",
        "pkg/service/handler_test.go",
        production,
    )
    assert resolved == "pkg/service/handler.go"


def test_resolve_import_spec_skips_special_imports():
    production = {"pkg/service/handler.go"}
    assert go_cov.resolve_import_spec("unsafe", "pkg/service/handler_test.go", production) is None
