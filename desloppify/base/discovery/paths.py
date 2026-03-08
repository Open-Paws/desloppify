"""Public path and snippet helpers used by command/runtime code."""

from __future__ import annotations

import os
from pathlib import Path

from desloppify.base import text_utils as _text_utils
from desloppify.base.runtime_state import current_runtime_context

_DEFAULT_PROJECT_ROOT = Path(os.environ.get("DESLOPPIFY_ROOT", Path.cwd())).resolve()


def get_project_root() -> Path:
    """Return the active project root, checking RuntimeContext first."""
    override = current_runtime_context().project_root
    if override is not None:
        return Path(override).resolve()
    return _DEFAULT_PROJECT_ROOT


PROJECT_ROOT = get_project_root()
DEFAULT_PATH = PROJECT_ROOT / "src"
SRC_PATH = PROJECT_ROOT / os.environ.get("DESLOPPIFY_SRC", "src")


def get_default_path() -> Path:
    """Return default scan path."""
    return get_project_root() / "src"


def get_src_path() -> Path:
    """Return the configured source root directory."""
    return get_project_root() / os.environ.get("DESLOPPIFY_SRC", "src")


def read_code_snippet(
    filepath: str,
    line: int,
    context: int = 1,
    *,
    project_root: Path | str | None = None,
) -> str | None:
    """Read a snippet around a 1-based line number."""
    return _text_utils.read_code_snippet(
        filepath,
        line,
        context,
        project_root=(
            Path(project_root).resolve()
            if project_root is not None
            else get_project_root()
        ),
    )


def get_area(filepath: str, *, min_depth: int = 2) -> str:
    """Derive an area name from a file path (generic: first 2 components)."""
    text = (filepath or "").strip()
    if not text:
        return "(unknown)"
    parts = Path(text).parts
    if not parts:
        return "(unknown)"
    return "/".join(parts[:2]) if len(parts) >= min_depth else parts[0]


__all__ = [
    "PROJECT_ROOT",
    "DEFAULT_PATH",
    "SRC_PATH",
    "get_area",
    "get_project_root",
    "get_default_path",
    "get_src_path",
    "read_code_snippet",
]
