"""Shared utilities for advocacy detectors."""

from __future__ import annotations

import os
from pathlib import Path

_SKIP_DIRS = frozenset({
    "node_modules", ".git", "dist", "build", ".next",
    "__pycache__", ".mypy_cache", ".pytest_cache", "vendor",
    ".desloppify", ".venv", "venv",
})


def find_source_files(
    path: Path,
    extensions: frozenset[str],
) -> list[str]:
    """Find files matching the given extensions under path.

    Skips common non-content directories (node_modules, .git, etc.).
    """
    if path.is_file():
        return [str(path)]

    files: list[str] = []
    for root, dirs, filenames in os.walk(path):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for name in filenames:
            if any(name.endswith(ext) for ext in extensions):
                files.append(os.path.join(root, name))
    return files
