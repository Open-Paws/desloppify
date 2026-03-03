"""Shared persistence helpers for resolve command handlers."""

from __future__ import annotations

from pathlib import Path

from desloppify import state as state_mod
from desloppify.core import config as config_mod
from desloppify.core.exception_sets import CommandError


def _save_state_or_exit(state: dict, state_file: Path | None) -> None:
    """Persist state with a consistent CLI error boundary."""
    try:
        state_mod.save_state(state, state_file)
    except OSError as exc:
        raise CommandError(f"could not save state: {exc}") from exc


def _save_config_or_exit(config: dict) -> None:
    """Persist config with a consistent CLI error boundary."""
    try:
        config_mod.save_config(config)
    except OSError as exc:
        raise CommandError(f"could not save config: {exc}") from exc


__all__ = ["_save_config_or_exit", "_save_state_or_exit"]
