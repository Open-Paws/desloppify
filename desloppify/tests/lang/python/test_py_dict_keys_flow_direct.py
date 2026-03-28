"""Direct coverage tests for Python dict key flow detector entrypoint."""

from __future__ import annotations

from pathlib import Path

import desloppify.languages.python.detectors.dict_keys.flow as flow_mod


class _FakeVisitor:
    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self._issues: list[dict[str, object]] = []

    def visit(self, tree) -> None:
        self._issues.append({"file": self.filepath, "nodes": len(getattr(tree, "body", []))})


def test_detect_dict_key_flow_handles_read_and_parse_failures(tmp_path: Path, monkeypatch) -> None:
    good = tmp_path / "good.py"
    good.write_text("x = {'a': 1}\n")
    bad_parse = tmp_path / "bad_parse.py"
    bad_parse.write_text("def broken(:\n")

    monkeypatch.setattr(flow_mod, "_load_dict_key_visitor", lambda: _FakeVisitor)
    monkeypatch.setattr(
        flow_mod,
        "find_py_files",
        lambda _path: ["good.py", "bad_parse.py", "missing.py"],
    )
    monkeypatch.setattr(flow_mod, "get_project_root", lambda: tmp_path)

    issues, checked = flow_mod.detect_dict_key_flow(tmp_path)
    assert checked == 3
    assert len(issues) == 1
    assert issues[0]["file"] == "good.py"


def test_detect_dict_key_flow_supports_absolute_file_paths(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "abs.py"
    source_path.write_text("value = {'k': 1}\n")

    monkeypatch.setattr(flow_mod, "_load_dict_key_visitor", lambda: _FakeVisitor)
    monkeypatch.setattr(flow_mod, "find_py_files", lambda _path: [str(source_path)])
    monkeypatch.setattr(flow_mod, "get_project_root", lambda: tmp_path)

    issues, checked = flow_mod.detect_dict_key_flow(tmp_path)
    assert checked == 1
    assert len(issues) == 1
    assert issues[0]["file"] == str(source_path)
