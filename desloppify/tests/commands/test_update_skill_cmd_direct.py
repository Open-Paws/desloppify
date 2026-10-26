"""Direct coverage tests for the update-skill command module."""

from __future__ import annotations

import argparse
import socket
import urllib.request
from importlib.resources import files
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


def test_update_installed_skill_handles_shared_file_write(
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
        "_read_local_docs_file",
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


def _fake_cmd_path(root: Path) -> Path:
    """Place a fake ``cmd.py`` so that ``root`` is five parents up from it."""
    fake_cmd = root / "desloppify" / "app" / "commands" / "update_skill" / "cmd.py"
    fake_cmd.parent.mkdir(parents=True)
    return fake_cmd


def _bundled(filename: str) -> str:
    return (
        files(update_skill_cmd_mod._BUNDLED_DOCS_PACKAGE)
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )


def test_read_local_docs_file_falls_back_to_bundled_package_data(monkeypatch, tmp_path: Path) -> None:
    """When no repo-root docs/ exists, the copy bundled in the package is used."""
    monkeypatch.setattr(update_skill_cmd_mod, "__file__", str(_fake_cmd_path(tmp_path)))

    content = update_skill_cmd_mod._read_local_docs_file("SKILL.md")
    assert content == _bundled("SKILL.md")
    assert update_skill_cmd_mod._read_local_docs_file("does-not-exist.md") is None


def test_read_local_docs_file_ignores_docs_without_desloppify_pyproject(
    monkeypatch, tmp_path: Path
) -> None:
    """In an installed package, ``site-packages/docs/`` must not shadow bundled docs."""
    site_packages = tmp_path / "site-packages"
    monkeypatch.setattr(update_skill_cmd_mod, "__file__", str(_fake_cmd_path(site_packages)))
    (site_packages / "docs").mkdir()
    (site_packages / "docs" / "SKILL.md").write_text("planted skill", encoding="utf-8")

    assert update_skill_cmd_mod._read_local_docs_file("SKILL.md") == _bundled("SKILL.md")

    # Another project's pyproject.toml next to docs/ is not enough either.
    (site_packages / "pyproject.toml").write_text(
        '[project]\nname = "other-package"\n', encoding="utf-8"
    )
    assert update_skill_cmd_mod._read_local_docs_file("SKILL.md") == _bundled("SKILL.md")


def test_read_local_docs_file_prefers_docs_in_source_checkout(monkeypatch, tmp_path: Path) -> None:
    """A desloppify source checkout (e.g. a fork with custom overlays) uses its docs/."""
    monkeypatch.setattr(update_skill_cmd_mod, "__file__", str(_fake_cmd_path(tmp_path)))
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "desloppify"\n', encoding="utf-8"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "SKILL.md").write_text("fork skill", encoding="utf-8")

    assert update_skill_cmd_mod._read_local_docs_file("SKILL.md") == "fork skill"
    # Files missing from the checkout still come from the bundled copy.
    assert update_skill_cmd_mod._read_local_docs_file("CLAUDE.md") == _bundled("CLAUDE.md")


def _block_network(monkeypatch) -> None:
    def _no_network(*args, **kwargs):
        raise AssertionError("update-skill must not touch the network")

    monkeypatch.setattr(urllib.request, "urlopen", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)


def test_update_installed_skill_writes_bundled_docs_without_network(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """With bundled docs available, update-skill writes them and never downloads."""
    monkeypatch.setattr(update_skill_cmd_mod, "__file__", str(_fake_cmd_path(tmp_path / "pkg")))
    _block_network(monkeypatch)
    monkeypatch.setattr(update_skill_cmd_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(update_skill_cmd_mod, "colorize", lambda text, _style: text)

    assert update_skill_cmd_mod.update_installed_skill("claude") is True

    written = (tmp_path / ".claude" / "skills" / "desloppify" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert written == update_skill_cmd_mod._build_section(
        _bundled("SKILL.md"), _bundled("CLAUDE.md")
    )


def test_update_installed_skill_fails_closed_when_overlay_missing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    """A local skill doc with no overlay must not be written, and nothing is fetched."""
    skill_content = "<!-- desloppify-skill-version: 5 -->\nbody\n"
    _block_network(monkeypatch)
    monkeypatch.setattr(
        update_skill_cmd_mod,
        "_read_local_docs_file",
        lambda filename: skill_content if filename == "SKILL.md" else None,
    )
    monkeypatch.setattr(update_skill_cmd_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(update_skill_cmd_mod, "colorize", lambda text, _style: text)

    assert update_skill_cmd_mod.update_installed_skill("claude") is False
    assert not (tmp_path / ".claude").exists()
    assert "Overlay CLAUDE.md not found" in capsys.readouterr().out


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
