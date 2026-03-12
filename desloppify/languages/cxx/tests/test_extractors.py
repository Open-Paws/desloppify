from __future__ import annotations

from desloppify.languages.cxx.extractors import extract_all_cxx_functions


def test_extract_cxx_functions_and_classes(tmp_path):
    source = tmp_path / "widget.cpp"
    source.write_text("class Widget { void run(); }; void helper() {}\n")

    functions = extract_all_cxx_functions([str(source)])

    assert any(f.name == "helper" for f in functions)
