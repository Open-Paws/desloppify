"""update-skill command: install or update the desloppify skill document."""

from __future__ import annotations

import argparse
import pathlib
import re
from importlib.resources import files

from desloppify.app.skill_docs import (
    SKILL_BEGIN,
    SKILL_END,
    SKILL_TARGETS,
    SKILL_VERSION,
    SKILL_VERSION_RE,
    SkillInstall,
    find_installed_skill,
)
from desloppify.base.discovery.file_paths import safe_write_text
from desloppify.base.discovery.paths import get_project_root
from desloppify.base.exception_sets import CommandError
from desloppify.base.output.terminal import colorize


def _build_section(skill_content: str, overlay_content: str | None) -> str:
    """Assemble the complete skill section from the skill doc and its overlay."""
    parts = [skill_content.rstrip()]
    if overlay_content:
        parts.append(overlay_content.rstrip())
    return "\n\n".join(parts) + "\n"


# Interfaces whose skill systems parse YAML frontmatter and require ``---``
# to appear on the very first line of the file.
_FRONTMATTER_FIRST_INTERFACES = frozenset({"amp", "codex"})


def _ensure_frontmatter_first(content: str) -> str:
    """Move YAML frontmatter to the top if HTML comments precede it.

    Some skill systems (e.g. AMP) require ``---`` on line 1 for frontmatter
    parsing.  SKILL.md ships with ``<!-- desloppify-begin -->`` and a version
    comment before the ``---`` block.  This function relocates those HTML
    comment lines to just after the closing ``---``.
    """
    lines = content.split("\n")

    # Find the opening ``---``.
    fm_start = None
    for i, line in enumerate(lines):
        if line.strip() == "---":
            fm_start = i
            break
    if fm_start is None or fm_start == 0:
        return content  # already fine or no frontmatter

    # Collect the HTML-comment lines that precede the frontmatter.
    prefix_lines = lines[:fm_start]

    # Find the closing ``---``.
    fm_end = None
    for i, line in enumerate(lines[fm_start + 1 :], fm_start + 1):
        if line.strip() == "---":
            fm_end = i
            break
    if fm_end is None:
        return content  # malformed frontmatter, leave untouched

    # Reassemble: frontmatter first, then the prefix lines, then the rest.
    reordered = (
        lines[fm_start : fm_end + 1]
        + prefix_lines
        + lines[fm_end + 1 :]
    )
    return "\n".join(reordered)


def _replace_section(file_content: str, new_section: str) -> str:
    """Replace the desloppify section in a shared file, preserving surrounding content.

    Uses first ``<!-- desloppify-begin -->`` and last ``<!-- desloppify-end -->``
    so the overlay (which also has an end marker) is captured correctly.

    Raises ``CommandError`` if the file already contains desloppify content
    (detected by the version marker) but is missing the begin/end markers —
    this prevents silently appending duplicate content.
    """
    begin = file_content.find(SKILL_BEGIN)
    end = file_content.rfind(SKILL_END)
    if begin == -1 or end == -1:
        # Check if the file already has desloppify content without markers.
        if SKILL_VERSION_RE.search(file_content):
            raise CommandError(
                "This file already contains desloppify skill content but is "
                "missing <!-- desloppify-begin --> / <!-- desloppify-end --> "
                "markers. Please add these markers around the existing "
                "desloppify section, or remove the old content first."
            )
        # No section markers and no existing content — append (first install).
        return file_content.rstrip() + "\n\n" + new_section

    before = file_content[:begin]
    after = file_content[end + len(SKILL_END):]
    before = before.rstrip() + "\n\n" if before.strip() else ""
    after = "\n" + after.lstrip("\n") if after.strip() else "\n"
    return before + new_section + after


def resolve_interface(
    explicit: str | None = None,
    install: SkillInstall | None = None,
) -> str | None:
    """Resolve which interface to update.

    Uses the explicit argument if given, otherwise infers from an existing
    install's overlay marker or file path.
    """
    if explicit:
        return explicit.lower()

    if install is None:
        install = find_installed_skill()
    if not install:
        return None

    if install.overlay:
        return install.overlay.lower()

    for name, (target, _overlay, _ded) in SKILL_TARGETS.items():
        if target == install.rel_path:
            return name
    return None


_BUNDLED_DOCS_PACKAGE = "desloppify.data.global"


def _source_checkout_root() -> pathlib.Path | None:
    """Return the desloppify repo root when running from a source checkout.

    ``__file__`` is ``desloppify/app/commands/update_skill/cmd.py``, so the repo
    root is five parents up.  In an installed package that same path is
    ``site-packages/``, where any other distribution could ship a top-level
    ``docs/`` directory.  Only trust it when a desloppify ``pyproject.toml``
    sits next to it.
    """
    root = pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent
    pyproject = root / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    if not re.search(r'^name\s*=\s*"desloppify"\s*$', text, re.MULTILINE):
        return None
    return root


def _read_local_docs_file(filename: str) -> str | None:
    """Read a skill/overlay doc from local sources, without using the network.

    Lookup order:
    1. ``docs/`` at the repo root, but only in a desloppify source checkout
       (forks with custom overlays).
    2. The copy bundled in the installed package (``desloppify.data.global``),
       which always matches the installed desloppify version.

    Nothing is ever downloaded: skill instructions written into a user's agent
    config come from the version they installed, not from whatever is
    currently on GitHub.
    """
    checkout_root = _source_checkout_root()
    if checkout_root is not None:
        local_path = checkout_root / "docs" / filename
        if local_path.is_file():
            try:
                return local_path.read_text(encoding="utf-8")
            except OSError:
                return None

    try:
        bundled = files(_BUNDLED_DOCS_PACKAGE).joinpath(filename)
        if bundled.is_file():
            return bundled.read_text(encoding="utf-8")
    except (ModuleNotFoundError, OSError):
        return None
    return None


def _update_installed_skill_with_deps(
    interface: str,
    *,
    read_docs_fn,
    get_project_root_fn,
    safe_write_text_fn,
    colorize_fn,
) -> bool:
    """Install the skill document for the given interface from local docs."""
    target_rel, overlay_name, dedicated = SKILL_TARGETS[interface]
    target_path = get_project_root_fn() / target_rel

    skill_content = read_docs_fn("SKILL.md")
    if not skill_content:
        print(colorize_fn("Skill document SKILL.md not found in bundled docs.", "red"))
        return False

    overlay_content = None
    if overlay_name:
        overlay_content = read_docs_fn(f"{overlay_name}.md")
        if overlay_content is None:
            # Fail closed rather than writing a skill without its overlay.
            print(
                colorize_fn(
                    f"Overlay {overlay_name}.md not found in bundled docs.", "red"
                )
            )
            return False

    if "desloppify-skill-version" not in skill_content:
        print(colorize_fn("Bundled SKILL.md doesn't look like a skill document.", "red"))
        return False

    print(colorize_fn(f"Using bundled skill document ({interface})...", "dim"))

    new_section = _build_section(skill_content, overlay_content)
    if interface in _FRONTMATTER_FIRST_INTERFACES:
        new_section = _ensure_frontmatter_first(new_section)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if dedicated:
        result = new_section
    elif target_path.is_file():
        existing = target_path.read_text(encoding="utf-8", errors="replace")
        result = _replace_section(existing, new_section)
    else:
        result = new_section

    safe_write_text_fn(target_path, result)

    version_match = SKILL_VERSION_RE.search(new_section)
    version = version_match.group(1) if version_match else "?"
    print(
        colorize_fn(
            f"Updated {target_rel} (v{version}, tool expects v{SKILL_VERSION})",
            "green",
        )
    )
    return True


def update_installed_skill(interface: str) -> bool:
    """Install the skill document for the given interface.

    Returns True on success, False on failure. Prints status messages.
    """
    return _update_installed_skill_with_deps(
        interface,
        read_docs_fn=_read_local_docs_file,
        get_project_root_fn=get_project_root,
        safe_write_text_fn=safe_write_text,
        colorize_fn=colorize,
    )


def _run_cmd_update_skill(
    args: argparse.Namespace,
    *,
    resolve_interface_fn,
    update_installed_skill_fn,
    colorize_fn,
) -> None:
    """Run the update-skill command with injectable package seams."""
    interface = resolve_interface_fn(getattr(args, "interface", None))

    if not interface:
        print(colorize_fn("No installed skill document found.", "yellow"))
        print()
        names = ", ".join(sorted(SKILL_TARGETS))
        print(f"Install with: desloppify update-skill <{names}>")
        return

    if interface not in SKILL_TARGETS:
        names = ", ".join(sorted(SKILL_TARGETS))
        print(colorize_fn(f"Unknown interface '{interface}'.", "red"))
        print(f"Available: {names}")
        return

    update_installed_skill_fn(interface)


def cmd_update_skill(args: argparse.Namespace) -> None:
    """Install or update the desloppify skill document."""
    _run_cmd_update_skill(
        args,
        resolve_interface_fn=resolve_interface,
        update_installed_skill_fn=update_installed_skill,
        colorize_fn=colorize,
    )
