"""Tests for scoped runtime state behavior."""

from __future__ import annotations

import desloppify.base.runtime_state as runtime_state
from desloppify.base.discovery.source import (
    disable_file_cache,
    enable_file_cache,
    get_exclusions,
    is_file_cache_enabled,
    set_exclusions,
)


def test_runtime_scope_isolates_exclusions():
    original = get_exclusions()
    set_exclusions(["global-only"])
    try:
        with runtime_state.runtime_scope(runtime_state.make_runtime_context()):
            assert get_exclusions() == ()
            set_exclusions(["scoped-only"])
            assert get_exclusions() == ("scoped-only",)

        assert get_exclusions() == ("global-only",)
    finally:
        set_exclusions(list(original))


def test_runtime_scope_restores_file_cache_flag():
    disable_file_cache()
    assert not is_file_cache_enabled()

    with runtime_state.runtime_scope(runtime_state.make_runtime_context()):
        assert not is_file_cache_enabled()
        enable_file_cache()
        assert is_file_cache_enabled()

    assert not is_file_cache_enabled()


def test_source_file_cache_is_scoped():
    key = ("scan", ".py")
    runtime_state.current_runtime_context().source_file_cache.clear()
    runtime_state.current_runtime_context().source_file_cache.put(key, ("global.py",))

    with runtime_state.runtime_scope(runtime_state.make_runtime_context()):
        cache = runtime_state.current_runtime_context().source_file_cache
        assert cache.get(key) is None
        cache.put(key, ("scoped.py",))
        assert cache.get(key) == ("scoped.py",)

    assert runtime_state.current_runtime_context().source_file_cache.get(key) == (
        "global.py",
    )


def test_treesitter_parse_cache_is_scoped():
    from desloppify.languages._framework.treesitter.imports.cache import (
        current_parse_tree_cache,
    )

    global_cache = current_parse_tree_cache()
    global_cache.enable()
    global_cache._trees[("global.py", "python")] = (b"src", object())

    with runtime_state.runtime_scope(runtime_state.make_runtime_context()):
        scoped_cache = current_parse_tree_cache()
        assert scoped_cache is not global_cache
        assert scoped_cache._trees == {}

    assert current_parse_tree_cache() is global_cache
    global_cache.disable()


def test_file_text_cache_read_result_success(tmp_path):
    file_path = tmp_path / "ok.py"
    file_path.write_text("print('ok')\n")
    cache = runtime_state.FileTextCache()

    result = cache.read_result(str(file_path))
    assert result.ok is True
    assert result.content == "print('ok')\n"
    assert result.error_kind is None
    assert cache.last_error_kind(str(file_path)) is None


def test_file_text_cache_read_result_tracks_error_kind(tmp_path):
    missing_path = tmp_path / "missing.py"
    cache = runtime_state.FileTextCache()

    result = cache.read_result(str(missing_path))
    assert result.ok is False
    assert result.content is None
    assert result.error_kind == "FileNotFoundError"
    assert cache.last_error_kind(str(missing_path)) == "FileNotFoundError"
