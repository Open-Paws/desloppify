"""Detect missing no-animal-violence enforcement tools.

Checks whether a project's existing toolchain (ESLint, Vale, pre-commit,
GitHub Actions, Semgrep) has the corresponding no-animal-violence plugins
configured.  Each missing tool produces a tier-3 finding with specific
install instructions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _check_eslint_plugin(scan_path: Path) -> list[dict]:
    """Check for eslint-plugin-no-animal-violence in JS/TS projects."""
    pkg_path = scan_path / "package.json"
    if not pkg_path.exists():
        return []

    text = _read_text(pkg_path)
    if text is None:
        return []

    try:
        pkg = json.loads(text)
    except json.JSONDecodeError:
        return []

    # Only relevant if the project uses eslint
    all_deps = {
        **pkg.get("dependencies", {}),
        **pkg.get("devDependencies", {}),
    }
    has_eslint = "eslint" in all_deps
    if not has_eslint:
        # Check for eslint config files
        eslint_configs = list(scan_path.glob(".eslintrc*")) + list(
            scan_path.glob("eslint.config.*")
        )
        if not eslint_configs:
            return []

    if "eslint-plugin-no-animal-violence" in all_deps:
        return []

    return [
        {
            "file": str(pkg_path.relative_to(scan_path)),
            "name": "eslint-plugin-no-animal-violence",
            "tier": 3,
            "confidence": "high",
            "summary": (
                "ESLint configured but eslint-plugin-no-animal-violence not installed — "
                "run: npm install -D eslint-plugin-no-animal-violence"
            ),
            "detail": {
                "tool": "eslint",
                "install": "npm install -D eslint-plugin-no-animal-violence",
                "docs": "https://github.com/Open-Paws/eslint-plugin-no-animal-violence",
            },
        }
    ]


def _check_vale_styles(scan_path: Path) -> list[dict]:
    """Check for vale-no-animal-violence style package."""
    vale_ini = scan_path / ".vale.ini"
    if not vale_ini.exists():
        return []

    text = _read_text(vale_ini)
    if text is None:
        return []

    if re.search(r"(?i)(NoAnimalViolence|Speciesism|no-animal-violence)", text):
        return []

    return [
        {
            "file": ".vale.ini",
            "name": "vale-no-animal-violence",
            "tier": 3,
            "confidence": "high",
            "summary": (
                "Vale configured but no-animal-violence styles not installed — "
                "add NoAnimalViolence package to .vale.ini"
            ),
            "detail": {
                "tool": "vale",
                "install": "vale sync (after adding package to .vale.ini)",
                "docs": "https://github.com/Open-Paws/vale-no-animal-violence",
            },
        }
    ]


def _check_pre_commit(scan_path: Path) -> list[dict]:
    """Check for no-animal-violence pre-commit hook."""
    config_path = scan_path / ".pre-commit-config.yaml"
    if not config_path.exists():
        return []

    text = _read_text(config_path)
    if text is None:
        return []

    if "no-animal-violence" in text:
        return []

    return [
        {
            "file": ".pre-commit-config.yaml",
            "name": "no-animal-violence-pre-commit",
            "tier": 3,
            "confidence": "high",
            "summary": (
                "pre-commit configured but no-animal-violence hook not installed — "
                "add repo: https://github.com/Open-Paws/no-animal-violence-pre-commit"
            ),
            "detail": {
                "tool": "pre-commit",
                "install": "Add to .pre-commit-config.yaml repos list",
                "docs": "https://github.com/Open-Paws/no-animal-violence-pre-commit",
            },
        }
    ]


def _check_github_action(scan_path: Path) -> list[dict]:
    """Check for no-animal-violence GitHub Action."""
    workflows_dir = scan_path / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return []

    workflow_files = list(workflows_dir.glob("*.yml")) + list(
        workflows_dir.glob("*.yaml")
    )
    if not workflow_files:
        return []

    for wf in workflow_files:
        text = _read_text(wf)
        if text and "no-animal-violence" in text:
            return []

    return [
        {
            "file": ".github/workflows/",
            "name": "no-animal-violence-action",
            "tier": 3,
            "confidence": "high",
            "summary": (
                "GitHub Actions configured but no-animal-violence action not present — "
                "add Open-Paws/no-animal-violence-action to a CI workflow"
            ),
            "detail": {
                "tool": "github-actions",
                "install": "uses: Open-Paws/no-animal-violence-action@v1",
                "docs": "https://github.com/Open-Paws/no-animal-violence-action",
            },
        }
    ]


def _check_semgrep(scan_path: Path) -> list[dict]:
    """Check for semgrep-rules-no-animal-violence in Python projects."""
    has_python = (scan_path / "pyproject.toml").exists() or (
        scan_path / "setup.cfg"
    ).exists()
    if not has_python:
        return []

    # Check for semgrep config
    semgrep_paths = [
        scan_path / ".semgrep.yml",
        scan_path / ".semgrep.yaml",
        scan_path / ".semgrep",
    ]
    has_semgrep = any(p.exists() for p in semgrep_paths)

    # Also check GitHub workflows for semgrep
    workflows_dir = scan_path / ".github" / "workflows"
    if not has_semgrep and workflows_dir.is_dir():
        for wf in list(workflows_dir.glob("*.yml")) + list(
            workflows_dir.glob("*.yaml")
        ):
            text = _read_text(wf)
            if text and "semgrep" in text.lower():
                has_semgrep = True
                break

    if not has_semgrep:
        return []

    # Check if no-animal-violence rules are referenced
    for sp in semgrep_paths:
        if sp.exists():
            text = _read_text(sp)
            if text and "no-animal-violence" in text:
                return []

    return [
        {
            "file": "pyproject.toml",
            "name": "semgrep-rules-no-animal-violence",
            "tier": 3,
            "confidence": "high",
            "summary": (
                "Semgrep configured but no-animal-violence rules not present — "
                "add rules from Open-Paws/semgrep-rules-no-animal-violence"
            ),
            "detail": {
                "tool": "semgrep",
                "install": "Add to .semgrep.yml or semgrep CI config",
                "docs": "https://github.com/Open-Paws/semgrep-rules-no-animal-violence",
            },
        }
    ]


def detect_advocacy_tool_presence(
    scan_path: Path,
    lang_extensions: frozenset[str] | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """Scan for missing no-animal-violence enforcement tools.

    Returns (entries, potentials) matching the standard detector interface.
    """

    entries: list[dict] = []

    entries.extend(_check_eslint_plugin(scan_path))
    entries.extend(_check_vale_styles(scan_path))
    entries.extend(_check_pre_commit(scan_path))
    entries.extend(_check_github_action(scan_path))
    entries.extend(_check_semgrep(scan_path))

    # Potentials = number of toolchains checked that had a config present
    # (i.e., tools where the check was applicable)
    tools_checked = 0
    for check_fn in [
        lambda: (scan_path / "package.json").exists()
        or bool(list(scan_path.glob(".eslintrc*"))),
        lambda: (scan_path / ".vale.ini").exists(),
        lambda: (scan_path / ".pre-commit-config.yaml").exists(),
        lambda: (scan_path / ".github" / "workflows").is_dir(),
        lambda: (scan_path / "pyproject.toml").exists()
        or (scan_path / "setup.cfg").exists(),
    ]:
        if check_fn():
            tools_checked += 1

    potentials = {"advocacy_tool_presence": max(tools_checked, 1)}
    return entries, potentials
