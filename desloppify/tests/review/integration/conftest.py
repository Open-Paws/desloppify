"""Shared fixtures for review integration tests."""

from __future__ import annotations

import pytest

import desloppify.engine.plan_state as plan_mod


@pytest.fixture(autouse=True)
def _isolate_plan(monkeypatch):
    """Prevent review integration tests from touching the real .desloppify/plan.json.

    ``do_import`` triggers ``_sync_plan_after_review_change`` which
    calls ``has_living_plan()`` / ``load_plan()`` / ``save_plan()`` on
    the real plan file.  Mocking ``has_living_plan`` to return False
    short-circuits that path so tests don't leak into production state.
    """
    monkeypatch.setattr(plan_mod, "has_living_plan", lambda: False)
