"""Regression tests for runtime-sensitive path discovery helpers."""

from pathlib import Path

import desloppify.base.discovery.paths as paths_api_mod
from desloppify.base.runtime_state import current_runtime_context


def test_get_project_root_reflects_env_changes_after_import(monkeypatch, tmp_path):
    """get_project_root should resolve DESLOPPIFY_ROOT lazily on each call."""
    ctx = current_runtime_context()
    monkeypatch.setattr(ctx, "project_root", None)

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    monkeypatch.setenv("DESLOPPIFY_ROOT", str(first_root))
    assert paths_api_mod.get_project_root() == first_root.resolve()

    monkeypatch.setenv("DESLOPPIFY_ROOT", str(second_root))
    assert paths_api_mod.get_project_root() == second_root.resolve()


def test_project_root_proxy_tracks_runtime_context_changes(monkeypatch, tmp_path):
    """PROJECT_ROOT compatibility export should remain dynamically resolved."""
    ctx = current_runtime_context()
    proxy = paths_api_mod.PROJECT_ROOT

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    monkeypatch.setattr(ctx, "project_root", first_root)
    assert Path(str(proxy)) == first_root.resolve()

    monkeypatch.setattr(ctx, "project_root", second_root)
    assert Path(str(proxy)) == second_root.resolve()


def test_src_path_proxy_tracks_env_changes_after_import(monkeypatch, tmp_path):
    """SRC_PATH compatibility export should reflect DESLOPPIFY_SRC updates."""
    ctx = current_runtime_context()
    monkeypatch.setattr(ctx, "project_root", tmp_path)
    monkeypatch.setenv("DESLOPPIFY_SRC", "src-a")

    proxy = paths_api_mod.SRC_PATH
    assert Path(str(proxy)) == (tmp_path / "src-a").resolve()

    monkeypatch.setenv("DESLOPPIFY_SRC", "src-b")
    assert Path(str(proxy)) == (tmp_path / "src-b").resolve()
