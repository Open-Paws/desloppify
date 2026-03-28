"""Unit tests for the CI Roslyn stub script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_roslyn_stub():
    module_path = Path(".github/scripts/roslyn_stub.py")
    spec = importlib.util.spec_from_file_location("test_roslyn_stub_module", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_requires_scan_path(capsys, monkeypatch):
    stub = _load_roslyn_stub()
    monkeypatch.setattr(sys, "argv", ["roslyn_stub.py"])
    assert stub.main() == 2
    err = capsys.readouterr().err
    assert "Usage: roslyn_stub.py <scan_path>" in err


def test_main_emits_roslyn_like_payload(capsys, monkeypatch, tmp_path):
    stub = _load_roslyn_stub()
    monkeypatch.setattr(
        stub,
        "build_dep_graph",
        lambda _path: {"A.cs": {"imports": {"B.cs", "C.cs"}}},
    )
    monkeypatch.setattr(sys, "argv", ["roslyn_stub.py", str(tmp_path)])

    assert stub.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["files"] == [{"file": "A.cs", "imports": ["B.cs", "C.cs"]}]
