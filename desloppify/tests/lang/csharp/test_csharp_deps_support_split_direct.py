"""Direct tests for split C# dependency metadata/render helper modules."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import desloppify.languages.csharp._helpers as csharp_helpers_mod
import desloppify.languages.csharp.detectors.deps_support_metadata as metadata_mod
import desloppify.languages.csharp.detectors.deps_support_render as render_mod


def test_extract_all_csharp_functions_aggregates_per_file(monkeypatch) -> None:
    monkeypatch.setattr(csharp_helpers_mod, "find_csharp_files", lambda _path: ["src/A.cs", "src/B.cs"])
    monkeypatch.setattr(
        csharp_helpers_mod,
        "extract_csharp_functions",
        lambda filepath: [SimpleNamespace(name=f"fn-{Path(filepath).stem}")],
    )

    functions = csharp_helpers_mod.extract_all_csharp_functions(Path("."))

    assert [fn.name for fn in functions] == ["fn-A", "fn-B"]


def test_metadata_entrypoint_and_parsing_helpers(monkeypatch, tmp_path) -> None:
    content = "\n".join(
        [
            "global using System;",
            "using Alias = Demo.Core;",
            "using static Demo.Tools.MathHelpers;",
            "namespace Demo.App;",
            "public class Program { static void Main(string[] args) {} }",
        ]
    )
    source = (tmp_path / "Program.cs").resolve()
    source.write_text(content, encoding="utf-8")

    namespace, usings, is_entry = metadata_mod.parse_file_metadata(str(source))
    assert namespace == "Demo.App"
    assert "System" in usings
    assert "Demo.Core" in usings
    assert "Demo.Tools.MathHelpers" in usings
    assert is_entry is True

    assert metadata_mod.is_entrypoint_file(source, content) is True

    helper = (tmp_path / "Helper.cs").resolve()
    helper.write_text("namespace Demo.App; public class Helper {}", encoding="utf-8")
    assert metadata_mod.is_entrypoint_file(helper, helper.read_text(encoding="utf-8")) is False

    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self: (_ for _ in ()).throw(UnicodeDecodeError("utf-8", b"x", 0, 1, "bad")),
    )
    assert metadata_mod.parse_file_metadata(str(source)) == (None, set(), False)


def test_expand_namespace_matches_handles_parent_child_namespaces() -> None:
    namespace_to_files = {
        "Demo": {"Demo/Root.cs"},
        "Demo.App": {"Demo/App/Program.cs"},
        "Demo.App.Feature": {"Demo/App/Feature/F.cs"},
    }
    matches = metadata_mod.expand_namespace_matches("Demo.App", namespace_to_files)
    assert matches == {"Demo/Root.cs", "Demo/App/Program.cs", "Demo/App/Feature/F.cs"}


def test_render_graph_helpers_cover_json_and_text_paths(monkeypatch, tmp_path) -> None:
    source = str((tmp_path / "A.cs").resolve())
    target = str((tmp_path / "B.cs").resolve())

    monkeypatch.setattr(render_mod, "resolve_path", lambda path: f"/resolved/{path}")
    assert render_mod.safe_resolve_graph_path("src/A.cs") == "/resolved/src/A.cs"

    monkeypatch.setattr(render_mod, "resolve_path", lambda _path: (_ for _ in ()).throw(OSError("boom")))
    assert render_mod.safe_resolve_graph_path("src/A.cs") == "src/A.cs"

    graph = render_mod.build_graph_from_edge_map(
        {
            source: {source, target},
            target: set(),
        }
    )
    assert target in graph[source]["imports"]
    assert source in graph[target]["importers"]
    assert source not in graph[source]["imports"]

    printed: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))
    monkeypatch.setattr(render_mod, "colorize", lambda text, _style: text)
    monkeypatch.setattr(render_mod, "print_table", lambda *args, **kwargs: printed.append("TABLE"))

    render_mod.render_deps_for_graph(
        SimpleNamespace(file=source, json=True, top=5),
        graph=graph,
    )
    payload = json.loads(printed[-1])
    assert payload["file"]
    assert payload["fan_out"] == 1

    printed.clear()
    render_mod.render_deps_for_graph(
        SimpleNamespace(file=None, json=False, top=5),
        graph=graph,
    )
    assert any("C# dependency graph" in line for line in printed)
    assert "TABLE" in printed


def test_render_cycles_for_graph_handles_json_and_clean_paths(monkeypatch, tmp_path) -> None:
    source = str((tmp_path / "A.cs").resolve())
    target = str((tmp_path / "B.cs").resolve())
    graph = {
        source: {"imports": {target}, "importers": set(), "import_count": 1, "importer_count": 0},
        target: {"imports": {source}, "importers": {source}, "import_count": 1, "importer_count": 1},
    }

    printed: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))
    monkeypatch.setattr(render_mod, "colorize", lambda text, _style: text)

    monkeypatch.setattr(render_mod, "detect_cycles", lambda _graph: ([{"length": 2, "files": [source, target]}], 2))
    render_mod.render_cycles_for_graph(SimpleNamespace(json=True, top=5), graph=graph)
    payload = json.loads(printed[-1])
    assert payload["count"] == 1
    assert payload["cycles"][0]["length"] == 2

    printed.clear()
    monkeypatch.setattr(render_mod, "detect_cycles", lambda _graph: ([], 0))
    render_mod.render_cycles_for_graph(SimpleNamespace(json=False, top=5), graph=graph)
    assert any("No import cycles found" in line for line in printed)
