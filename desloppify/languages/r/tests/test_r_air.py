"""Regression tests for R air formatter integration and plugin registration."""

from __future__ import annotations

import json
from pathlib import Path

from desloppify.languages import get_lang
from desloppify.languages._framework.generic_parts.parsers import parse_air


class TestParseAir:
    def test_would_reformat_single_file(self):
        output = "Would reformat: R/transform.R\n"
        entries = parse_air(output, Path("/project"))
        assert len(entries) == 1
        assert entries[0]["file"] == "R/transform.R"
        assert entries[0]["line"] == 0
        assert "air" in entries[0]["message"]

    def test_would_reformat_multiple_files(self):
        output = (
            "Would reformat: R/transform.R\n"
            "Would reformat: R/utils.R\n"
            "Would reformat: R/plot.R\n"
        )
        entries = parse_air(output, Path("/project"))
        assert len(entries) == 3

    def test_no_reformat_needed(self):
        entries = parse_air("", Path("/project"))
        assert entries == []

    def test_ignores_non_reformat_lines(self):
        output = "1 file would be reformatted\nSome other output\n"
        entries = parse_air(output, Path("/project"))
        assert entries == []


class TestRDimensionsOverride:
    def test_override_file_exists_and_is_valid_json(self):
        import desloppify.languages.r

        r_dir = Path(desloppify.languages.r.__file__).resolve().parent
        override_path = r_dir / "review_data" / "dimensions.override.json"
        assert override_path.is_file()
        data = json.loads(override_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "dimension_prompts" in data
        assert "system_prompt_append" in data

    def test_override_has_r_specific_dimensions(self):
        import desloppify.languages.r

        r_dir = Path(desloppify.languages.r.__file__).resolve().parent
        override_path = r_dir / "review_data" / "dimensions.override.json"
        data = json.loads(override_path.read_text(encoding="utf-8"))
        dims = data.get("dimension_prompts", {})
        assert "abstraction_fitness" in dims
        assert "test_strategy" in dims


class TestRLangPluginRegistration:
    def test_config_name(self):
        cfg = get_lang("r")
        assert cfg.name == "r"

    def test_config_extensions(self):
        cfg = get_lang("r")
        assert ".R" in cfg.extensions
        assert ".r" in cfg.extensions

    def test_detect_markers(self):
        cfg = get_lang("r")
        assert "DESCRIPTION" in cfg.detect_markers
        assert ".Rproj" in cfg.detect_markers

    def test_has_air_format_phase(self):
        cfg = get_lang("r")
        labels = {p.label for p in cfg.phases}
        assert "air" in labels

    def test_air_format_detect_command(self):
        cfg = get_lang("r")
        assert "air_format" in cfg.detect_commands

    def test_external_test_dirs(self):
        cfg = get_lang("r")
        assert "tests/testthat" in cfg.external_test_dirs

    def test_test_file_extensions(self):
        cfg = get_lang("r")
        assert ".R" in cfg.test_file_extensions
        assert ".r" in cfg.test_file_extensions
