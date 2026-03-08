"""I/O and transactional persistence helpers for plan override commands."""

from __future__ import annotations

from pathlib import Path

from desloppify import state as state_mod
from desloppify.base.discovery.file_paths import safe_write_text
from desloppify.engine.plan import get_plan_file, plan_path_for_state, save_plan


def _resolve_state_file(path: Path | None) -> Path:
    return path if path is not None else state_mod.get_state_file()


def _resolve_plan_file(path: Path | None) -> Path:
    return path if path is not None else get_plan_file()


def _plan_file_for_state(state_file: Path | None) -> Path | None:
    if state_file is None:
        return None
    return plan_path_for_state(state_file)


def _snapshot_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text()


def _restore_file_snapshot(path: Path, snapshot: str | None) -> None:
    if snapshot is None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
        return
    safe_write_text(path, snapshot)


def save_plan_state_transactional(
    *,
    plan: dict,
    plan_path: Path | None,
    state_data: dict,
    state_path_value: Path | None,
) -> None:
    """Persist plan+state together; rollback both files on partial write failure."""
    effective_plan_path = _resolve_plan_file(plan_path)
    effective_state_path = _resolve_state_file(state_path_value)
    plan_snapshot = _snapshot_file(effective_plan_path)
    state_snapshot = _snapshot_file(effective_state_path)

    try:
        state_mod.save_state(state_data, effective_state_path)
        save_plan(plan, effective_plan_path)
    except Exception:
        _restore_file_snapshot(effective_state_path, state_snapshot)
        _restore_file_snapshot(effective_plan_path, plan_snapshot)
        raise


__all__ = [
    "_plan_file_for_state",
    "save_plan_state_transactional",
]
