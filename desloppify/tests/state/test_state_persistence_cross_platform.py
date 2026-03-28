"""Regression tests for cross-platform state persistence."""

from __future__ import annotations

import errno
import importlib
from unittest.mock import patch

import pytest


def test_state_lock_imports_and_round_trips_on_current_platform(tmp_path):
    persistence_mod = importlib.import_module("desloppify.engine._state.persistence")

    state_path = tmp_path / "state.json"
    with persistence_mod.state_lock(state_path) as state:
        state["scan_count"] = 3

    loaded = persistence_mod.load_state(state_path)
    assert loaded["scan_count"] == 3


def test_state_lock_times_out_without_bad_file_descriptor(tmp_path):
    persistence_mod = importlib.import_module("desloppify.engine._state.persistence")
    state_path = tmp_path / "state.json"

    with patch.object(
        persistence_mod,
        "_acquire_state_lock",
        side_effect=OSError(errno.EACCES, "busy"),
    ):
        with pytest.raises(TimeoutError, match="Could not acquire state lock"):
            with persistence_mod.state_lock(state_path, timeout=0.0):
                pass
