"""Visualization output/context behavior tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from desloppify.app.commands.viz import cmd_tree, cmd_viz
from desloppify.app.commands.helpers.command_runtime import CommandRuntime
from desloppify.app.output._viz_cmd_context import load_cmd_context
from desloppify.app.output.visualize import (
    D3_CDN_URL,
    generate_visualization,
)
from desloppify.base.exception_sets import CommandError
from desloppify.base.output.contract import OutputResult


class TestConstants:
    def test_d3_cdn_url_is_https(self):
        assert D3_CDN_URL.startswith("https://")
        assert "d3" in D3_CDN_URL


# ===========================================================================
# load_cmd_context
# ===========================================================================


class TestLoadCmdContext:
    def test_uses_preloaded_state_when_available(self, monkeypatch):
        sentinel_state = {"issues": {"x": 1}}

        monkeypatch.setattr(
            "desloppify.app.output._viz_cmd_context.resolve_lang", lambda _a: None
        )
        calls = []
        monkeypatch.setattr(
            "desloppify.app.output._viz_cmd_context.load_state",
            lambda _sp: calls.append(_sp) or {},
        )

        args = SimpleNamespace(
            path=".",
            state=None,
            lang=None,
            runtime=CommandRuntime(
                config={},
                state=sentinel_state,
                state_path=Path("/tmp/state-python.json"),
            ),
        )
        _, _, state = load_cmd_context(args)

        assert state is sentinel_state
        assert calls == []

    def test_falls_back_to_state_path_from_cli_main(self, monkeypatch):
        sentinel_path = Path("/tmp/state-typescript.json")
        monkeypatch.setattr(
            "desloppify.app.output._viz_cmd_context.resolve_lang", lambda _a: None
        )
        calls = []
        monkeypatch.setattr(
            "desloppify.app.output._viz_cmd_context.load_state",
            lambda sp: calls.append(sp) or {"ok": True},
        )

        args = SimpleNamespace(
            path=".",
            state=None,
            lang=None,
            runtime=CommandRuntime(
                config={},
                state=None,  # force fallback load via state_path
                state_path=sentinel_path,
            ),
        )
        _, _, state = load_cmd_context(args)

        assert state == {"ok": True}
        assert calls == [sentinel_path]


class TestVizWriteBehavior:
    def test_dep_graph_failure_is_best_effort(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "desloppify.app.output.visualize._collect_file_data",
            lambda _path, _lang=None: [],
        )

        class _Lang:
            file_finder = None

            @staticmethod
            def build_dep_graph(_path):
                raise RuntimeError("dep graph parse failed")

        monkeypatch.setattr(
            "desloppify.app.output.visualize_data._resolve_visualization_lang",
            lambda _path, _lang=None: _Lang(),
        )

        html, output_result = generate_visualization(
            tmp_path, state={}, output=None, lang=None
        )
        assert isinstance(html, str)
        assert output_result.ok is True
        assert output_result.status == "not_requested"

    def test_generate_visualization_reports_write_failure(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "desloppify.app.output.visualize._collect_file_data",
            lambda _path, _lang=None: [],
        )
        monkeypatch.setattr(
            "desloppify.app.output.visualize._build_dep_graph_for_path",
            lambda _path, _lang=None: {},
        )
        monkeypatch.setattr(
            "desloppify.app.output.visualize.safe_write_text",
            lambda _path, _text: (_ for _ in ()).throw(OSError("disk full")),
        )

        _html, output_result = generate_visualization(
            tmp_path,
            state={},
            output=tmp_path / "treemap.html",
            lang=None,
        )
        assert output_result.ok is False
        assert output_result.status == "error"

    def test_generate_visualization_reports_template_read_failure(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(
            "desloppify.app.output.visualize._collect_file_data",
            lambda _path, _lang=None: [],
        )
        monkeypatch.setattr(
            "desloppify.app.output.visualize._build_dep_graph_for_path",
            lambda _path, _lang=None: {},
        )
        monkeypatch.setattr(
            "desloppify.app.output.visualize._get_html_template",
            lambda: (_ for _ in ()).throw(OSError("missing template")),
        )

        html, output_result = generate_visualization(
            tmp_path,
            state={},
            output=None,
            lang=None,
        )
        assert html == ""
        assert output_result.ok is False
        assert output_result.status == "error"
        assert output_result.error_kind == "visualization_generation_error"

    def test_cmd_viz_raises_command_error_when_write_fails(
        self,
        monkeypatch,
        capsys,
        tmp_path,
    ):
        monkeypatch.setattr(
            "desloppify.app.commands.viz.load_cmd_context",
            lambda _args: (tmp_path, None, {}),
        )
        monkeypatch.setattr(
            "desloppify.app.commands.viz.generate_visualization",
            lambda *_args, **_kwargs: (
                "<html></html>",
                OutputResult(
                    ok=False,
                    status="error",
                    message="disk full",
                    error_kind="visualization_write_error",
                ),
            ),
        )
        monkeypatch.setattr(
            "desloppify.app.commands.viz.colorize",
            lambda text, _style: text,
        )

        args = SimpleNamespace(path=".", output=str(tmp_path / "treemap.html"))
        with pytest.raises(CommandError) as exc:
            cmd_viz(args)
        assert "Visualization generation failed" in exc.value.message
        out = capsys.readouterr().out
        assert "Treemap written to" not in out

    def test_cmd_tree_raises_command_error_when_generation_fails(
        self,
        monkeypatch,
        tmp_path,
    ):
        monkeypatch.setattr(
            "desloppify.app.commands.viz.load_cmd_context",
            lambda _args: (tmp_path, None, {}),
        )
        monkeypatch.setattr(
            "desloppify.app.commands.viz.generate_tree_text",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk error")),
        )

        args = SimpleNamespace(path=".", depth=2, focus=None, min_loc=0, sort="loc", detail=False)
        with pytest.raises(CommandError) as exc:
            cmd_tree(args)
        assert "Tree generation failed" in exc.value.message
