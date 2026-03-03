"""Import guards for deprecated compatibility facades."""

from __future__ import annotations

import ast
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE_ROOT = _PROJECT_ROOT / "desloppify"
_ALLOWED_COMPAT_MODULES: set[str] = set()


def _runtime_python_files() -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for path in _PACKAGE_ROOT.rglob("*.py"):
        rel = path.relative_to(_PROJECT_ROOT).as_posix()
        if "/tests/" in rel:
            continue
        if rel in _ALLOWED_COMPAT_MODULES:
            continue
        files.append((path, rel))
    return files


def _compat_import_violations(path: Path, rel: str) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {"desloppify.utils", "desloppify.file_discovery"}:
                    violations.append(f"{rel}:{node.lineno} import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in {"desloppify.utils", "desloppify.file_discovery"}:
                violations.append(f"{rel}:{node.lineno} from {module} import ...")
                continue
            if module == "desloppify":
                for alias in node.names:
                    if alias.name in {"utils", "file_discovery"}:
                        violations.append(
                            f"{rel}:{node.lineno} from desloppify import {alias.name}"
                        )
    return violations


def test_runtime_code_avoids_deprecated_compat_facades():
    violations: list[str] = []
    for path, rel in _runtime_python_files():
        violations.extend(_compat_import_violations(path, rel))
    assert not violations, "runtime imports deprecated compat facades:\n" + "\n".join(
        sorted(violations)
    )
