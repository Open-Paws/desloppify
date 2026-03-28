"""Tests for autofix command option resolution and I/O helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from desloppify.app.commands.autofix.fixer_selection import (
    _COMMAND_POST_FIX,
    load_fixer,
    resolve_fixer_config,
)
from desloppify.base.exception_sets import CommandError
from desloppify.languages._framework.base.types import FixerConfig, LangConfig

# ── Helpers ───────────────────────────────────────────────────


def _make_fixer(name: str = "test_fixer", post_fix=None) -> FixerConfig:
    return FixerConfig(
        label=f"Fix {name}",
        detect=lambda p: [],
        fix=lambda *a, **kw: [],
        detector=name,
        post_fix=post_fix,
    )


def _make_lang(name: str = "python", fixers: dict | None = None) -> LangConfig:
    return LangConfig(
        name=name,
        extensions=[".py"],
        exclusions=[],
        default_src="src",
        build_dep_graph=lambda p: {},
        entry_patterns=[],
        barrel_names=set(),
        fixers=fixers or {},
    )


class _FakeArgs:
    """Minimal args object for _load_fixer."""

    def __init__(self, lang="python"):
        self.lang = lang
        self.path = "/tmp/test"


# ── _resolve_fixer_config: success paths ──────────────────────


def test_load_fixer_returns_lang_and_fixer_config():
    """Successful fixer resolution returns (LangConfig, FixerConfig) tuple."""
    fc = _make_fixer("unused")
    lang = _make_lang(fixers={"unused": fc})
    args = _FakeArgs()

    with patch("desloppify.app.commands.autofix.fixer_selection.resolve_lang", return_value=lang):
        result_lang, result_fc = resolve_fixer_config(args, "unused")

    assert result_lang is lang
    assert result_fc is fc


def test_load_fixer_attaches_command_post_fix():
    """When _COMMAND_POST_FIX has an entry and fixer has no post_fix, it's attached."""
    fc = _make_fixer("logs")  # no post_fix
    lang = _make_lang(fixers={"logs": fc})
    args = _FakeArgs()

    sentinel = MagicMock()
    original = _COMMAND_POST_FIX.copy()
    try:
        _COMMAND_POST_FIX["logs"] = sentinel
        with patch("desloppify.app.commands.autofix.fixer_selection.resolve_lang", return_value=lang):
            _, result_fc = resolve_fixer_config(args, "logs")
        assert result_fc.post_fix is sentinel
        # Original should be unchanged (dataclasses.replace creates a copy)
        assert fc.post_fix is None
    finally:
        _COMMAND_POST_FIX.clear()
        _COMMAND_POST_FIX.update(original)


def test_load_fixer_does_not_override_existing_post_fix():
    """When fixer already has post_fix, _COMMAND_POST_FIX is not applied."""
    existing_hook = MagicMock()
    fc = _make_fixer("logs", post_fix=existing_hook)
    lang = _make_lang(fixers={"logs": fc})
    args = _FakeArgs()

    original = _COMMAND_POST_FIX.copy()
    try:
        _COMMAND_POST_FIX["logs"] = MagicMock()
        with patch("desloppify.app.commands.autofix.fixer_selection.resolve_lang", return_value=lang):
            _, result_fc = resolve_fixer_config(args, "logs")
        assert result_fc.post_fix is existing_hook
    finally:
        _COMMAND_POST_FIX.clear()
        _COMMAND_POST_FIX.update(original)


# ── _resolve_fixer_config: exit paths ────────────────────────


def test_load_fixer_exits_when_no_lang():
    """When resolve_lang returns None, sys.exit(1) is called."""
    args = _FakeArgs()
    with patch("desloppify.app.commands.autofix.fixer_selection.resolve_lang", return_value=None):
        with pytest.raises(CommandError) as exc_info:
            resolve_fixer_config(args, "unused")
        assert exc_info.value.exit_code == 1


def test_load_fixer_exits_when_no_fixers():
    """When language has no fixers, sys.exit(1) is called."""
    lang = _make_lang(fixers={})
    args = _FakeArgs()
    with patch("desloppify.app.commands.autofix.fixer_selection.resolve_lang", return_value=lang):
        with pytest.raises(CommandError) as exc_info:
            resolve_fixer_config(args, "unused")
        assert exc_info.value.exit_code == 1


def test_load_fixer_exits_when_fixer_name_unknown():
    """When requested fixer name is not in the registry, sys.exit(1) is called."""
    fc = _make_fixer("unused")
    lang = _make_lang(fixers={"unused": fc})
    args = _FakeArgs()
    with patch("desloppify.app.commands.autofix.fixer_selection.resolve_lang", return_value=lang):
        with pytest.raises(CommandError) as exc_info:
            resolve_fixer_config(args, "nonexistent")
        assert exc_info.value.exit_code == 1


def test_load_fixer_compat_alias_still_resolves() -> None:
    fc = _make_fixer("unused")
    lang = _make_lang(fixers={"unused": fc})
    args = _FakeArgs()
    with patch("desloppify.app.commands.autofix.fixer_selection.resolve_lang", return_value=lang):
        assert load_fixer(args, "unused") == (lang, fc)
