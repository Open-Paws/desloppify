"""Direct coverage tests for the update-skill command module."""

from __future__ import annotations

import argparse
from pathlib import Path

import desloppify.app.commands.update_skill.cmd as update_skill_cmd_mod


def test_update_skill_helper_functions_cover_frontmatter_resolution_and_replace() -> None:
    content = (
        "<!-- desloppify-begin -->\n"
        "<!-- version -->\n"
        "---\n"
        "name: skill\n"
        "---\n"
        "body\n"
    )
    reordered = update_skill_cmd_mod._ensure_frontmatter_first(content)
    assert reordered.startswith("---\nname: skill\n---\n")
    assert "<!-- desloppify-begin -->" in reordered

    section = update_skill_cmd_mod._build_section("skill body\n", "overlay body\n")
    assert section == "skill body\n\noverlay body\n"

    replaced = update_skill_cmd_mod._replace_section(
        f"prefix\n\n{update_skill_cmd_mod.SKILL_BEGIN}\nold\n{update_skill_cmd_mod.SKILL_END}\n",
        "new section\n",
    )
    assert "prefix" in replaced
    assert "new section" in replaced
    assert "old" not in replaced


def test_resolve_interface_prefers_explicit_then_install_metadata(monkeypatch) -> None:
    assert update_skill_cmd_mod.resolve_interface("CoDeX") == "codex"

    install = update_skill_cmd_mod.SkillInstall(
        rel_path=".claude/skills/desloppify/SKILL.md",
        version=5,
        overlay="windsurf",
        stale=False,
    )
    assert update_skill_cmd_mod.resolve_interface(None, install=install) == "windsurf"

    inferred = update_skill_cmd_mod.SkillInstall(
        rel_path=".cursor/rules/desloppify.md",
        version=5,
        overlay=None,
        stale=False,
    )
    monkeypatch.setattr(update_skill_cmd_mod, "find_installed_skill", lambda: inferred)
    assert update_skill_cmd_mod.resolve_interface() == "cursor"


def test_update_installed_skill_handles_download_and_shared_file_write(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    skill_content = (
        "<!-- desloppify-begin -->\n"
        "<!-- desloppify-skill-version: 5 -->\n"
        "---\n"
        "name: desloppify\n"
        "---\n"
        "body\n"
        "<!-- desloppify-end -->\n"
    )
    overlay_content = "overlay text\n"
    writes: list[tuple[Path, str]] = []
    target = tmp_path / ".agents" / "skills" / "desloppify" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("prefix only", encoding="utf-8")

    monkeypatch.setattr(
        update_skill_cmd_mod,
        "_download",
        lambda filename: skill_content if filename == "SKILL.md" else overlay_content,
    )
    monkeypatch.setattr(update_skill_cmd_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        update_skill_cmd_mod,
        "safe_write_text",
        lambda path, text: writes.append((path, text)) or path.write_text(text, encoding="utf-8"),
    )
    monkeypatch.setattr(update_skill_cmd_mod, "colorize", lambda text, _style: text)

    assert update_skill_cmd_mod.update_installed_skill("codex") is True
    assert writes and writes[-1][0] == target
    written = target.read_text(encoding="utf-8")
    assert written.startswith("---\nname: desloppify\n---\n")
    assert "overlay text" in written
    out = capsys.readouterr().out
    assert "Updated .agents/skills/desloppify/SKILL.md" in out


def test_cmd_update_skill_handles_missing_and_unknown_interfaces(monkeypatch, capsys) -> None:
    monkeypatch.setattr(update_skill_cmd_mod, "resolve_interface", lambda _explicit=None: None)
    monkeypatch.setattr(update_skill_cmd_mod, "colorize", lambda text, _style: text)
    update_skill_cmd_mod.cmd_update_skill(argparse.Namespace(interface=None))
    out = capsys.readouterr().out
    assert "No installed skill document found." in out

    monkeypatch.setattr(
        update_skill_cmd_mod,
        "resolve_interface",
        lambda _explicit=None: "unknown_thing",
    )
    update_skill_cmd_mod.cmd_update_skill(argparse.Namespace(interface=None))
    out = capsys.readouterr().out
    assert "Unknown interface 'unknown_thing'." in out
