from __future__ import annotations

import desloppify.languages.cxx.test_coverage as cxx_cov


def test_strip_test_markers_for_cxx():
    assert cxx_cov.strip_test_markers("widget_test.cpp") == "widget.cpp"
    assert cxx_cov.strip_test_markers("test_widget.cpp") == "widget.cpp"
    assert cxx_cov.strip_test_markers("widget.cpp") is None


def test_parse_test_import_specs_extracts_includes():
    content = '#include "widget.hpp"\n#include <gtest/gtest.h>\n'
    assert cxx_cov.parse_test_import_specs(content) == ["widget.hpp", "gtest/gtest.h"]


def test_has_testable_logic_accepts_function_definitions_without_regex_crash():
    assert cxx_cov.has_testable_logic("widget.cpp", "int widget() { return 1; }\n") is True
    assert cxx_cov.has_testable_logic("widget_test.cpp", "int widget() { return 1; }\n") is False


def test_has_testable_logic_excludes_test_prefix_files():
    assert cxx_cov.has_testable_logic("test_widget.cpp", "int widget() { return 1; }\n") is False


def test_map_test_to_source_and_resolve_import_spec(tmp_path):
    source = tmp_path / "src" / "widget.cpp"
    header = tmp_path / "src" / "widget.hpp"
    test_file = tmp_path / "tests" / "widget_test.cpp"

    source.parent.mkdir(parents=True)
    test_file.parent.mkdir(parents=True)
    source.write_text("int widget() { return 1; }\n")
    header.write_text("int widget();\n")
    test_file.write_text('#include "../src/widget.hpp"\n')

    production = {str(source.resolve()), str(header.resolve())}

    assert cxx_cov.map_test_to_source(str(test_file), production) == str(source.resolve())
    assert (
        cxx_cov.resolve_import_spec("../src/widget.hpp", str(test_file), production)
        == str(header.resolve())
    )
