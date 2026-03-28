"""Tests for generic move command helpers."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import desloppify.app.commands.move.cmd as move_mod
from desloppify.app.commands.move.cmd import _cmd_move_dir
from desloppify.app.commands.move.language import (
    detect_lang_from_dir,
    detect_lang_from_ext,
    load_lang_move_module,
    resolve_lang_for_file_move,
    resolve_move_verify_hint,
)
from desloppify.app.commands.move.planning import dedup_replacements, resolve_dest
from desloppify.base.exception_sets import CommandError
from desloppify.base.discovery.file_paths import resolve_path
from desloppify.base.discovery.file_paths import safe_write_text as safe_write

# ---------------------------------------------------------------------------
# Module imports
# ---------------------------------------------------------------------------


class TestMoveModuleSanity:
    """Verify move modules import cleanly."""

    def test_move_module_imports(self):
        assert callable(move_mod.cmd_move)


# ---------------------------------------------------------------------------
# dedup_replacements
# ---------------------------------------------------------------------------


class TestDedup:
    """dedup_replacements removes duplicate replacement tuples while preserving order."""

    def test_empty_list(self):
        assert dedup_replacements([]) == []

    def test_no_duplicates(self):
        pairs = [("a", "b"), ("c", "d")]
        assert dedup_replacements(pairs) == pairs

    def test_removes_duplicates(self):
        pairs = [("a", "b"), ("c", "d"), ("a", "b"), ("e", "f"), ("c", "d")]
        assert dedup_replacements(pairs) == [("a", "b"), ("c", "d"), ("e", "f")]

    def test_preserves_order(self):
        pairs = [("z", "y"), ("a", "b"), ("z", "y")]
        assert dedup_replacements(pairs) == [("z", "y"), ("a", "b")]

    def test_different_values_not_deduped(self):
        pairs = [("a", "b"), ("a", "c")]
        assert dedup_replacements(pairs) == [("a", "b"), ("a", "c")]


# ---------------------------------------------------------------------------
# detect_lang_from_ext
# ---------------------------------------------------------------------------


class TestDetectLangFromExt:
    """detect_lang_from_ext maps file extensions to language names."""

    def test_typescript_ts(self):
        assert detect_lang_from_ext("foo.ts") == "typescript"

    def test_typescript_tsx(self):
        assert detect_lang_from_ext("foo.tsx") == "typescript"

    def test_python_py(self):
        assert detect_lang_from_ext("foo.py") == "python"

    def test_csharp_cs(self):
        assert detect_lang_from_ext("foo.cs") == "csharp"

    def test_unknown_ext(self):
        assert detect_lang_from_ext("foo.xyz") is None

    def test_no_ext(self):
        assert detect_lang_from_ext("Makefile") is None

    def test_full_path(self):
        assert detect_lang_from_ext("/src/components/Button.tsx") == "typescript"

    def test_skips_registered_plugin_when_metadata_load_fails(self, monkeypatch):
        import desloppify.app.commands.move.language as move_lang_mod

        move_lang_mod._ext_to_lang_map.cache_clear()
        monkeypatch.setattr(
            move_lang_mod.lang_mod,
            "available_langs",
            lambda: ["broken_lang"],
        )
        monkeypatch.setattr(
            move_lang_mod,
            "load_lang_config_metadata",
            lambda _name: None,
        )

        assert detect_lang_from_ext("foo.py") is None
        move_lang_mod._ext_to_lang_map.cache_clear()


# ---------------------------------------------------------------------------
# detect_lang_from_dir
# ---------------------------------------------------------------------------


class TestDetectLangFromDir:
    """detect_lang_from_dir inspects directory contents."""

    def test_python_dir(self, tmp_path):
        (tmp_path / "foo.py").write_text("")
        assert detect_lang_from_dir(str(tmp_path)) == "python"

    def test_typescript_dir(self, tmp_path):
        (tmp_path / "bar.ts").write_text("")
        assert detect_lang_from_dir(str(tmp_path)) == "typescript"

    def test_csharp_dir(self, tmp_path):
        (tmp_path / "Service.cs").write_text("")
        assert detect_lang_from_dir(str(tmp_path)) == "csharp"

    def test_empty_dir(self, tmp_path):
        assert detect_lang_from_dir(str(tmp_path)) is None

    def test_no_source_files(self, tmp_path):
        (tmp_path / "readme.txt").write_text("")
        (tmp_path / "config.toml").write_text("")
        assert detect_lang_from_dir(str(tmp_path)) is None

    def test_nested_files(self, tmp_path):
        sub = tmp_path / "src" / "components"
        sub.mkdir(parents=True)
        (sub / "App.tsx").write_text("")
        assert detect_lang_from_dir(str(tmp_path)) == "typescript"


# ---------------------------------------------------------------------------
# resolve_move_verify_hint
# ---------------------------------------------------------------------------


class TestResolveMoveVerifyHint:
    """resolve_move_verify_hint supports modern move module APIs."""

    def test_prefers_get_verify_hint(self):
        move_mod_api = SimpleNamespace(
            get_verify_hint=lambda: "desloppify detect deps",
            VERIFY_HINT="legacy hint",
        )
        assert resolve_move_verify_hint(move_mod_api) == "desloppify detect deps"

    def test_does_not_use_legacy_constant(self):
        move_mod_api = SimpleNamespace(VERIFY_HINT="npx tsc --noEmit")
        assert resolve_move_verify_hint(move_mod_api) == ""

    def test_returns_empty_when_no_hint_available(self):
        move_mod_api = SimpleNamespace(get_verify_hint=lambda: None)
        assert resolve_move_verify_hint(move_mod_api) == ""


# ---------------------------------------------------------------------------
# resolve_dest
# ---------------------------------------------------------------------------


class TestResolveDest:
    """resolve_dest resolves destination paths."""

    def test_file_to_file(self, tmp_path):
        source = "src/foo.ts"
        dest = str(tmp_path / "bar.ts")
        result = resolve_dest(source, dest, resolve_path)
        assert result.endswith("bar.ts")

    def test_file_to_dir_keeps_filename(self, tmp_path):
        target_dir = tmp_path / "newdir"
        target_dir.mkdir()
        source = "src/foo.ts"
        result = resolve_dest(source, str(target_dir), resolve_path)
        assert result.endswith("foo.ts")
        assert "newdir" in result

    def test_file_to_trailing_slash(self, tmp_path):
        source = "src/foo.ts"
        result = resolve_dest(source, str(tmp_path) + "/", resolve_path)
        assert result.endswith("foo.ts")


# ---------------------------------------------------------------------------
# Language resolution precedence
# ---------------------------------------------------------------------------


class TestResolveLangPrecedence:
    """Explicit --lang should override auto-detection heuristics."""

    def test_explicit_lang_overrides_extension_detection(self, monkeypatch):
        class FakeArgs:
            lang = "python"
            path = "."

        monkeypatch.setattr(
            "desloppify.app.commands.move.language.resolve_lang",
            lambda _args: type("L", (), {"name": "python"})(),
        )
        result = resolve_lang_for_file_move("/tmp/example.ts", FakeArgs())
        assert result == "python"

    def test_directory_move_prefers_explicit_lang(self, tmp_path, monkeypatch):
        source_dir = tmp_path / "pkg"
        source_dir.mkdir()
        (source_dir / "mod.py").write_text("import os\n")
        dest_dir = tmp_path / "pkg_new"

        captured = []

        class FakeLang:
            extensions = [".py"]
            default_src = "."

            @staticmethod
            def build_dep_graph(_path):
                return {}

        class FakeMoveMod:
            @staticmethod
            def find_replacements(_source, _dest, _graph):
                return {}

            @staticmethod
            def find_self_replacements(_source, _dest, _graph):
                return []

        monkeypatch.setattr(
            "desloppify.app.commands.move.directory.detect_lang_from_dir",
            lambda _p: "typescript",
        )
        monkeypatch.setattr(
            "desloppify.app.commands.move.directory.resolve_lang",
            lambda _args: type("L", (), {"name": "python"})(),
        )
        monkeypatch.setattr(
            "desloppify.app.commands.move.directory.lang_mod.get_lang",
            lambda name: captured.append(name) or FakeLang(),
        )
        monkeypatch.setattr(
            "desloppify.app.commands.move.directory.load_lang_move_module",
            lambda _n: FakeMoveMod(),
        )

        class FakeArgs:
            dest = str(dest_dir)
            dry_run = True
            lang = "python"

        _cmd_move_dir(FakeArgs(), str(source_dir))
        assert captured == ["python"]


class TestLoadLangMoveModule:
    """Language move-module loading behavior for missing vs broken imports."""

    def test_falls_back_to_scaffold_when_language_module_missing(self, monkeypatch):
        target_module = "desloppify.languages.python.move"
        scaffold_module = "desloppify.languages._framework.scaffold_move"
        scaffold = object()

        def _fake_import(module_name: str):
            if module_name == target_module:
                raise ModuleNotFoundError(
                    f"No module named '{target_module}'",
                    name=target_module,
                )
            if module_name == scaffold_module:
                return scaffold
            raise AssertionError(f"unexpected import request: {module_name}")

        monkeypatch.setattr(
            "desloppify.app.commands.helpers.dynamic_loaders.importlib.import_module",
            _fake_import,
        )
        assert load_lang_move_module("python") is scaffold

    def test_raises_when_language_module_import_is_broken(self, monkeypatch):
        target_module = "desloppify.languages.python.move"

        def _fake_import(module_name: str):
            if module_name == target_module:
                exc = ImportError("cannot import name 'broken' from dependency")
                exc.name = "dependency"
                raise exc
            raise AssertionError(f"unexpected import request: {module_name}")

        monkeypatch.setattr(
            "desloppify.app.commands.helpers.dynamic_loaders.importlib.import_module",
            _fake_import,
        )

        with pytest.raises(CommandError) as exc:
            load_lang_move_module("python")
        assert "Failed to import language move module" in str(exc.value)
        assert target_module in str(exc.value)


# ---------------------------------------------------------------------------
# safe_write
# ---------------------------------------------------------------------------


class TestSafeWrite:
    """safe_write performs atomic writes."""

    def test_writes_content(self, tmp_path):
        target = tmp_path / "output.txt"
        safe_write(str(target), "hello world")
        assert target.read_text() == "hello world"

    def test_overwrites_existing(self, tmp_path):
        target = tmp_path / "output.txt"
        target.write_text("old content")
        safe_write(str(target), "new content")
        assert target.read_text() == "new content"

    def test_no_temp_file_left(self, tmp_path):
        target = tmp_path / "output.txt"
        safe_write(str(target), "hello")
        tmp_file = target.with_suffix(".txt.tmp")
        assert not tmp_file.exists()

    def test_string_path_works(self, tmp_path):
        target = str(tmp_path / "string_path.txt")
        safe_write(target, "content")
        assert Path(target).read_text() == "content"

    def test_path_object_works(self, tmp_path):
        target = tmp_path / "path_obj.txt"
        safe_write(target, "content")
        assert target.read_text() == "content"
