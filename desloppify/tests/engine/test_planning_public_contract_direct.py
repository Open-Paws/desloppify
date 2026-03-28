"""Direct coverage for planning package public-contract documentation."""

from __future__ import annotations

import ast
from pathlib import Path


def test_runtime_modules_use_canonical_state_and_plan_surfaces() -> None:
    package_root = Path(__file__).resolve().parents[2]
    checks = {
        "cli.py": (
            ["from desloppify.state_io import load_state"],
            ["from desloppify.state import"],
        ),
        "app/commands/review/preflight.py": (
            ["from desloppify.state_io import StateModel, save_state"],
            ["from desloppify.state import"],
        ),
        "app/commands/plan/override/io.py": (
            ["from desloppify.state_io import StateModel, get_state_file, save_state"],
            ["from desloppify import state as state_mod"],
        ),
        "app/commands/helpers/queue_progress.py": (
            [
                "from desloppify.engine.plan_state import load_plan",
                "from desloppify.state_scoring import score_snapshot",
            ],
            [
                "from desloppify.engine import plan",
                "from desloppify import state as state_mod",
            ],
        ),
        "engine/_work_queue/core.py": (
            ["from desloppify.engine._state.schema import StateModel"],
            ["from desloppify.state import"],
        ),
    }

    for rel, (required, forbidden) in checks.items():
        source = (package_root / rel).read_text(encoding="utf-8")
        for token in required:
            assert token in source, f"missing canonical import {token!r} in {rel}"
        for token in forbidden:
            assert token not in source, f"legacy import {token!r} still present in {rel}"


def _private_plan_import_offenders(package_rel: str) -> list[str]:
    package_root = Path(__file__).resolve().parents[2]
    search_root = package_root / package_rel
    if not search_root.exists():
        return []
    offenders: list[str] = []
    for module_path in search_root.rglob("*.py"):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        has_private_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.startswith("desloppify.engine._plan"):
                    has_private_import = True
                    break
            elif isinstance(node, ast.Import):
                if any(
                    alias.name.startswith("desloppify.engine._plan")
                    for alias in node.names
                ):
                    has_private_import = True
                    break
        if has_private_import:
            offenders.append(str(module_path.relative_to(package_root)))
    return offenders


def test_planning_avoids_private_plan_imports() -> None:
    """Planning package must not import from _plan directly."""
    offenders = _private_plan_import_offenders("engine/planning")
    assert offenders == []
