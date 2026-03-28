"""Direct tests for split Python language helper module."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import desloppify.languages.python._helpers as python_helpers_mod


def test_py_extract_functions_aggregates_from_discovered_files(monkeypatch) -> None:
    monkeypatch.setattr(python_helpers_mod, "find_py_files", lambda _path: ["src/a.py", "src/b.py"])
    monkeypatch.setattr(
        python_helpers_mod,
        "extract_py_functions",
        lambda filepath: [SimpleNamespace(name=f"fn-{Path(filepath).stem}")],
    )

    functions = python_helpers_mod.py_extract_functions(Path("."))
    assert [fn.name for fn in functions] == ["fn-a", "fn-b"]


def test_scan_root_from_files_handles_common_missing_and_invalid_sets(tmp_path) -> None:
    assert python_helpers_mod.scan_root_from_files(["README.md", "docs/index.txt"]) is None

    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    root = python_helpers_mod.scan_root_from_files([
        str((tmp_path / "src" / "a.py").resolve()),
        str((tmp_path / "src" / "b.py").resolve()),
        str((tmp_path / "tests" / "test_a.py").resolve()),
    ])
    assert root == tmp_path

    # Mixed absolute + relative file paths make commonpath invalid.
    assert python_helpers_mod.scan_root_from_files(["src/a.py", "/tmp/project/src/b.py"]) is None
