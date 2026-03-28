"""Shared pytest fixtures for review tests."""

from __future__ import annotations

import pytest

import desloppify.engine.plan_state as plan_mod
from desloppify.tests.review.shared_review_fixtures import (
    empty_state,
    mock_lang,
    mock_lang_with_zones,
    sample_issues_data,
    state_with_issues,
)


@pytest.fixture(autouse=True)
def _isolate_plan(monkeypatch):
    """Prevent review tests from touching the real .desloppify/plan.json."""
    monkeypatch.setattr(plan_mod, "has_living_plan", lambda: False)


__all__ = [
    "empty_state",
    "mock_lang",
    "mock_lang_with_zones",
    "sample_issues_data",
    "state_with_issues",
]
