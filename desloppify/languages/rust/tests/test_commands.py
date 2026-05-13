"""Tests for Rust command registry wiring."""

from __future__ import annotations

import json
from types import SimpleNamespace

from desloppify.languages.rust.commands import cmd_cycles, get_detect_commands


def test_get_detect_commands_includes_base_and_rust_specific_commands():
    commands = get_detect_commands()

    for name in (
        "deps",
        "cycles",
        "dupes",
        "smells",
        "rust_import_hygiene",
        "rust_async_locking",
        "rust_unsafe_api",
        "cargo_error",
    ):
        assert name in commands
        assert callable(commands[name])


def test_cmd_cycles_reports_disabled_json(tmp_path, capsys):
    cmd_cycles(SimpleNamespace(path=str(tmp_path), json=True, top=20))

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"count": 0, "entries": []}


def test_cmd_cycles_reports_disabled_text(tmp_path, capsys):
    cmd_cycles(SimpleNamespace(path=str(tmp_path), json=False, top=20))

    assert "Rust cycle detection is disabled" in capsys.readouterr().out
