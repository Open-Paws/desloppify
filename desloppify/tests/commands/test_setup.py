"""Tests for the bundled offline `setup` command."""

from __future__ import annotations

import argparse
from importlib.resources import files
from pathlib import Path

import pytest

import desloppify.app.commands.registry as registry_mod
import desloppify.app.commands.scan.reporting.agent_context as agent_context_mod
import desloppify.app.commands.setup.cmd as setup_cmd_mod
import desloppify.app.skill_docs as skill_docs_mod
from desloppify.base.exception_sets import CommandError
from desloppify.cli import create_parser


def _setup_args(*, local: bool = False, interface: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(local=local, interface=interface)


def test_setup_parser_and_registry_are_wired() -> None:
    parser = create_parser()
    args = parser.parse_args(["setup", "--interface", "claude"])
    assert args.command == "setup"
    assert args.interface == "claude"
    assert args.local is False

    handlers = registry_mod.get_command_handlers()
    assert handlers["setup"] is setup_cmd_mod.cmd_setup


def test_global_install_writes_supported_targets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".cursor").mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    setup_cmd_mod.cmd_setup(_setup_args())

    claude_target = tmp_path / ".claude" / "skills" / "desloppify" / "SKILL.md"
    cursor_target = tmp_path / ".cursor" / "rules" / "desloppify.md"
    assert claude_target.is_file()
    assert cursor_target.is_file()
    assert "desloppify-skill-version" in claude_target.read_text(encoding="utf-8")
    assert "<!-- desloppify-overlay: claude -->" in claude_target.read_text(encoding="utf-8")
    assert "<!-- desloppify-overlay: cursor -->" in cursor_target.read_text(encoding="utf-8")


def test_global_single_interface_installs_only_requested_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".cursor").mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    setup_cmd_mod.cmd_setup(_setup_args(interface="claude"))

    assert (tmp_path / ".claude" / "skills" / "desloppify" / "SKILL.md").is_file()
    assert not (tmp_path / ".cursor" / "rules" / "desloppify.md").exists()


def test_global_setup_skips_missing_tool_dirs_with_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / ".claude").mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    setup_cmd_mod.cmd_setup(_setup_args())

    out = capsys.readouterr().out
    assert "Installed global skill files:" in out
    assert "Skipping cursor (~/.cursor not found)" in out
    assert (tmp_path / ".claude" / "skills" / "desloppify" / "SKILL.md").is_file()
    assert not (tmp_path / ".cursor" / "rules" / "desloppify.md").exists()


def test_global_setup_errors_when_requested_tool_dir_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    with pytest.raises(CommandError, match=r"~/.cursor/ not found"):
        setup_cmd_mod.cmd_setup(_setup_args(interface="cursor"))


def test_global_setup_errors_when_no_supported_tools_detected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    with pytest.raises(CommandError, match="No supported AI tools detected"):
        setup_cmd_mod.cmd_setup(_setup_args())


def test_local_install_writes_agents_md_in_project_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(setup_cmd_mod, "get_project_root", lambda: tmp_path)

    setup_cmd_mod.cmd_setup(_setup_args(local=True, interface="hermes"))

    agents_path = tmp_path / "AGENTS.md"
    assert agents_path.is_file()
    content = agents_path.read_text(encoding="utf-8")
    assert "<!-- desloppify-begin -->" in content
    assert "<!-- desloppify-overlay: hermes -->" in content


def test_local_setup_replaces_only_desloppify_section(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(setup_cmd_mod, "get_project_root", lambda: tmp_path)
    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text(
        "Project heading\n\n"
        "<!-- desloppify-begin -->\n"
        "old skill section\n"
        "<!-- desloppify-end -->\n\n"
        "Keep this footer\n",
        encoding="utf-8",
    )

    setup_cmd_mod.cmd_setup(_setup_args(local=True, interface="windsurf"))

    content = agents_path.read_text(encoding="utf-8")
    assert "Project heading" in content
    assert "Keep this footer" in content
    assert "old skill section" not in content
    assert "<!-- desloppify-overlay: windsurf -->" in content


def test_local_setup_requires_interface() -> None:
    with pytest.raises(CommandError, match="Specify one: --interface windsurf\\|gemini\\|hermes"):
        setup_cmd_mod.cmd_setup(_setup_args(local=True))


def test_codex_global_setup_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    setup_cmd_mod.cmd_setup(_setup_args(interface="codex"))

    out = capsys.readouterr().out
    assert "Codex global skill path is not yet confirmed" in out
    assert not any(tmp_path.iterdir())


def test_bundled_resources_are_readable() -> None:
    resource_dir = files("desloppify.data.global")
    for filename in (
        "SKILL.md",
        "CLAUDE.md",
        "CURSOR.md",
        "CODEX.md",
        "WINDSURF.md",
        "GEMINI.md",
        "HERMES.md",
    ):
        text = resource_dir.joinpath(filename).read_text(encoding="utf-8")
        assert text.strip()


def test_find_global_skill_discovers_home_install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    target = home / ".claude" / "skills" / "desloppify" / "SKILL.md"
    target.parent.mkdir(parents=True)
    project.mkdir()
    target.write_text(
        "<!-- desloppify-skill-version: 6 -->\n<!-- desloppify-overlay: claude -->\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(skill_docs_mod, "get_project_root", lambda: project)

    install = skill_docs_mod.find_global_skill()

    assert install is not None
    assert install.rel_path == "~/.claude/skills/desloppify/SKILL.md"
    assert install.overlay == "claude"
    assert install.stale is False


def test_check_skill_version_warns_for_stale_global_install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    target = home / ".claude" / "skills" / "desloppify" / "SKILL.md"
    target.parent.mkdir(parents=True)
    project.mkdir()
    target.write_text(
        "<!-- desloppify-skill-version: 1 -->\n<!-- desloppify-overlay: claude -->\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(skill_docs_mod, "get_project_root", lambda: project)

    warning = skill_docs_mod.check_skill_version()

    assert warning is not None
    assert "Your global desloppify skill is outdated" in warning
    assert "Run: desloppify setup" in warning


def test_scan_auto_update_respects_current_global_install(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []
    global_install = skill_docs_mod.SkillInstall(
        rel_path="~/.claude/skills/desloppify/SKILL.md",
        version=skill_docs_mod.SKILL_VERSION,
        overlay="claude",
        stale=False,
    )
    monkeypatch.setattr(agent_context_mod, "is_agent_environment", lambda: True)
    monkeypatch.setattr(agent_context_mod.skill_docs_mod, "find_installed_skill", lambda: None)
    monkeypatch.setattr(
        agent_context_mod.skill_docs_mod,
        "find_global_skill",
        lambda: global_install,
    )
    monkeypatch.setattr(agent_context_mod, "update_installed_skill", lambda interface: calls.append(interface))

    agent_context_mod.auto_update_skill()

    assert calls == []
    assert capsys.readouterr().out == ""


def test_scan_auto_update_warns_for_stale_global_install_without_downloading(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []
    stale_global_install = skill_docs_mod.SkillInstall(
        rel_path="~/.claude/skills/desloppify/SKILL.md",
        version=1,
        overlay="claude",
        stale=True,
    )
    monkeypatch.setattr(agent_context_mod, "is_agent_environment", lambda: True)
    monkeypatch.setattr(agent_context_mod.skill_docs_mod, "find_installed_skill", lambda: None)
    monkeypatch.setattr(
        agent_context_mod.skill_docs_mod,
        "find_global_skill",
        lambda: stale_global_install,
    )
    monkeypatch.setattr(agent_context_mod, "update_installed_skill", lambda interface: calls.append(interface))

    agent_context_mod.auto_update_skill()

    out = capsys.readouterr().out
    assert calls == []
    assert "Global skill document is outdated" in out
    assert "Run: desloppify setup" in out
