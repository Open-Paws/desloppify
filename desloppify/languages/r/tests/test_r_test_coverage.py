"""Tests for R test coverage heuristics and mappings."""

from __future__ import annotations

from desloppify.languages.r.test_coverage import (
    ASSERT_PATTERNS,
    MOCK_PATTERNS,
    SNAPSHOT_PATTERNS,
    has_testable_logic,
    map_test_to_source,
    parse_test_import_specs,
    strip_comments,
    strip_test_markers,
)


class TestHasTestableLogic:
    def test_function_definition_is_testable(self):
        content = 'my_func <- function(x) { x + 1 }'
        assert has_testable_logic("R/my_func.R", content) is True

    def test_pure_script_is_not_testable(self):
        content = 'x <- 1\ny <- 2\nprint(x + y)\n'
        assert has_testable_logic("R/script.R", content) is False

    def test_rmd_files_are_not_testable(self):
        content = '```{r}\nmy_func <- function(x) x\n```\n'
        assert has_testable_logic("analysis.Rmd", content) is False


class TestMapTestToSource:
    def test_maps_testthat_test_to_r_source(self):
        production = {"R/transform.R", "R/utils.R"}
        result = map_test_to_source("tests/testthat/test-transform.R", production)
        assert result == "R/transform.R"

    def test_returns_none_for_non_testthat_file(self):
        production = {"R/transform.R"}
        result = map_test_to_source("R/transform.R", production)
        assert result is None

    def test_returns_none_if_source_missing(self):
        production = {"R/other.R"}
        result = map_test_to_source("tests/testthat/test-missing.R", production)
        assert result is None

    def test_handles_lowercase_r_extension(self):
        production = {"R/transform.r"}
        result = map_test_to_source("tests/testthat/test-transform.r", production)
        assert result == "R/transform.r"


class TestStripTestMarkers:
    def test_strips_test_prefix(self):
        assert strip_test_markers("test-transform.R") == "transform.R"

    def test_returns_none_for_non_test_file(self):
        assert strip_test_markers("transform.R") is None


class TestParseTestImportSpecs:
    def test_extracts_library_names(self):
        content = 'library(dplyr)\nlibrary(testthat)\nx <- 1'
        specs = parse_test_import_specs(content)
        assert "dplyr" in specs
        assert "testthat" in specs

    def test_extracts_require_names(self):
        content = 'require(data.table)\nrequire(ggplot2)'
        specs = parse_test_import_specs(content)
        assert "data.table" in specs
        assert "ggplot2" in specs

    def test_ignores_base_packages(self):
        content = 'library(base)\nlibrary(dplyr)'
        specs = parse_test_import_specs(content)
        assert "dplyr" in specs

    def test_empty_when_no_imports(self):
        specs = parse_test_import_specs("x <- 1")
        assert specs == []


class TestStripComments:
    def test_strips_inline_comments(self):
        assert strip_comments("x <- 1 # comment") == "x <- 1 "

    def test_preserves_hash_in_strings(self):
        result = strip_comments('x <- "# not a comment"')
        assert "# not a comment" in result

    def test_preserves_multiline_code(self):
        code = "x <- 1\n# comment\ny <- 2"
        result = strip_comments(code)
        assert "x <- 1" in result
        assert "y <- 2" in result
        assert "# comment" not in result


class TestAssertPatterns:
    def test_matches_expect_equal(self):
        for pat in ASSERT_PATTERNS:
            if pat.search("expect_equal(x, 1)"):
                return
        assert False, "No pattern matched expect_equal"

    def test_matches_expect_true(self):
        for pat in ASSERT_PATTERNS:
            if pat.search("expect_true(x > 0)"):
                return
        assert False, "No pattern matched expect_true"

    def test_matches_expect_error(self):
        for pat in ASSERT_PATTERNS:
            if pat.search("expect_error(readLines('bad'))"):
                return
        assert False, "No pattern matched expect_error"


class TestMockPatterns:
    def test_matches_local_mocked_bindings(self):
        assert any(
            pat.search("local_mocked_bindings(foo = bar)")
            for pat in MOCK_PATTERNS
        )

    def test_matches_with_mocked_bindings(self):
        assert any(
            pat.search("with_mocked_bindings(foo = bar, { })")
            for pat in MOCK_PATTERNS
        )

    def test_no_match_on_plain_function(self):
        assert not any(
            pat.search("my_function(x = 1)")
            for pat in MOCK_PATTERNS
        )


class TestSnapshotPatterns:
    def test_matches_expect_snapshot(self):
        assert any(
            pat.search("expect_snapshot(result)")
            for pat in SNAPSHOT_PATTERNS
        )

    def test_matches_expect_snapshot_value(self):
        assert any(
            pat.search("expect_snapshot_value(x)")
            for pat in SNAPSHOT_PATTERNS
        )

    def test_matches_expect_snapshot_file(self):
        assert any(
            pat.search("expect_snapshot_file('output.md')")
            for pat in SNAPSHOT_PATTERNS
        )

    def test_no_match_on_plain_function(self):
        assert not any(
            pat.search("expect_equal(x, 1)")
            for pat in SNAPSHOT_PATTERNS
        )
