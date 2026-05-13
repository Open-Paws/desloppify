"""Tests for Dart extraction."""

from __future__ import annotations

from desloppify.languages.dart.extractors import extract_dart_functions


def test_extract_dart_function_ignores_comment_braces(tmp_path):
    source = tmp_path / "lib" / "app.dart"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        """
bool validate(Input input) {
  /* unbalanced } }} braces */
  return input.isValid();
}
"""
    )

    functions = extract_dart_functions(str(source))

    assert [fn.name for fn in functions] == ["validate"]
    assert "input.isValid()" in functions[0].body
