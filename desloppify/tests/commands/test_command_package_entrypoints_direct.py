"""Direct tests for lazy package-root command entrypoints."""

from __future__ import annotations

import argparse
import desloppify.app.commands.autofix as autofix_pkg
import desloppify.app.commands.autofix.cmd as autofix_cmd_mod
import desloppify.app.commands.backlog as backlog_pkg
import desloppify.app.commands.backlog.cmd as backlog_cmd_mod
import desloppify.app.commands.move as move_pkg
import desloppify.app.commands.move.cmd as move_cmd_mod
import desloppify.app.commands.next as next_pkg
import desloppify.app.commands.next.cmd as next_cmd_mod
import desloppify.app.commands.scan as scan_pkg
import desloppify.app.commands.scan.cmd as scan_cmd_mod
import desloppify.app.commands.show as show_pkg
import desloppify.app.commands.show.cmd as show_cmd_mod


def _assert_entrypoint_delegation(
    monkeypatch,
    *,
    package_mod,
    command_mod,
    entrypoint_name: str,
) -> None:
    args = argparse.Namespace(path=".")
    calls: list[argparse.Namespace] = []

    monkeypatch.setattr(command_mod, entrypoint_name, lambda value: calls.append(value))

    entrypoint = getattr(package_mod, entrypoint_name)

    assert entrypoint_name in package_mod.__all__
    assert callable(entrypoint)
    assert getattr(command_mod, entrypoint_name).__name__ == "<lambda>"
    assert entrypoint.__module__ == package_mod.__name__
    assert entrypoint.__name__ == entrypoint_name
    assert "stable package-root entrypoint" in (package_mod.__doc__ or "")

    entrypoint(args)

    assert calls == [args]


def test_autofix_package_root_entrypoint_delegates(monkeypatch) -> None:
    _assert_entrypoint_delegation(
        monkeypatch,
        package_mod=autofix_pkg,
        command_mod=autofix_cmd_mod,
        entrypoint_name="cmd_autofix",
    )


def test_backlog_package_root_entrypoint_delegates(monkeypatch) -> None:
    _assert_entrypoint_delegation(
        monkeypatch,
        package_mod=backlog_pkg,
        command_mod=backlog_cmd_mod,
        entrypoint_name="cmd_backlog",
    )


def test_move_package_root_entrypoint_delegates(monkeypatch) -> None:
    _assert_entrypoint_delegation(
        monkeypatch,
        package_mod=move_pkg,
        command_mod=move_cmd_mod,
        entrypoint_name="cmd_move",
    )


def test_next_package_root_entrypoint_delegates(monkeypatch) -> None:
    _assert_entrypoint_delegation(
        monkeypatch,
        package_mod=next_pkg,
        command_mod=next_cmd_mod,
        entrypoint_name="cmd_next",
    )


def test_scan_package_root_entrypoint_delegates(monkeypatch) -> None:
    _assert_entrypoint_delegation(
        monkeypatch,
        package_mod=scan_pkg,
        command_mod=scan_cmd_mod,
        entrypoint_name="cmd_scan",
    )


def test_show_package_root_entrypoint_delegates(monkeypatch) -> None:
    _assert_entrypoint_delegation(
        monkeypatch,
        package_mod=show_pkg,
        command_mod=show_cmd_mod,
        entrypoint_name="cmd_show",
    )
