"""Direct tests for narrative action submodules.

These tests import directly from submodule files (not the __init__.py facade)
so test_coverage recognizes the submodules as directly tested.
"""

from __future__ import annotations

import pytest

from desloppify.intelligence.narrative.action_engine import (
    _fixer_has_applicable_issues,
)
from desloppify.intelligence.narrative.action_engine import (
    compute_actions as _compute_actions,
)
from desloppify.intelligence.narrative.action_models import ActionContext
from desloppify.intelligence.narrative.action_tools import (
    compute_tools as _compute_tools,
)
from desloppify.state import empty_state as empty_state_factory


@pytest.fixture
def empty_state():
    return empty_state_factory()


class TestComputeActions:
    def test_empty_detectors(self, empty_state):
        result = _compute_actions(
            ActionContext(
                by_detector={},
                dimension_scores={},
                state=empty_state,
                debt={},
                lang="typescript",
            )
        )
        assert result == []

    def test_returns_actions_for_open_issues(self, empty_state):
        result = _compute_actions(
            ActionContext(
                by_detector={"unused": 5},
                dimension_scores={},
                state=empty_state,
                debt={},
                lang="typescript",
            )
        )
        assert len(result) >= 1
        assert any(a["detector"] == "unused" for a in result)

    def test_python_gets_manual_fix(self, empty_state):
        result = _compute_actions(
            ActionContext(
                by_detector={"unused": 5},
                dimension_scores={},
                state=empty_state,
                debt={},
                lang="python",
            )
        )
        if result:
            unused_actions = [a for a in result if a.get("detector") == "unused"]
            for action in unused_actions:
                assert action["type"] == "manual_fix"

    def test_debt_review_action(self, empty_state):
        result = _compute_actions(
            ActionContext(
                by_detector={},
                dimension_scores={},
                state=empty_state,
                debt={"overall_gap": 5.0},
                lang="typescript",
            )
        )
        assert any(a["type"] == "debt_review" for a in result)

    def test_no_debt_review_when_gap_small(self, empty_state):
        result = _compute_actions(
            ActionContext(
                by_detector={},
                dimension_scores={},
                state=empty_state,
                debt={"overall_gap": 1.0},
                lang="typescript",
            )
        )
        assert not any(a.get("type") == "debt_review" for a in result)

    def test_actions_sorted_by_type_and_impact(self, empty_state):
        result = _compute_actions(
            ActionContext(
                by_detector={"unused": 5, "structural": 3, "smells": 10},
                dimension_scores={},
                state=empty_state,
                debt={},
                lang="typescript",
            )
        )
        if len(result) >= 2:
            priorities = [a["priority"] for a in result]
            assert priorities == list(range(1, len(priorities) + 1))

    def test_subjective_review_action(self, empty_state):
        result = _compute_actions(
            ActionContext(
                by_detector={"subjective_review": 20},
                dimension_scores={},
                state=empty_state,
                debt={},
                lang="typescript",
            )
        )
        sr_actions = [a for a in result if a.get("detector") == "subjective_review"]
        if sr_actions:
            assert sr_actions[0]["command"] == "desloppify review --prepare"

    def test_review_issues_action(self, empty_state):
        result = _compute_actions(
            ActionContext(
                by_detector={"review": 3},
                dimension_scores={},
                state=empty_state,
                debt={},
                lang="typescript",
            )
        )
        review_actions = [a for a in result if a.get("detector") == "review"]
        if review_actions:
            assert "show review" in review_actions[0]["command"]


class TestFixerHasApplicableIssues:
    """Unit tests for _fixer_has_applicable_issues."""

    def test_non_smells_detector_always_applicable(self):
        assert _fixer_has_applicable_issues({}, "unused", "unused-imports") is True
        assert _fixer_has_applicable_issues({}, "logs", "debug-logs") is True

    def test_smells_with_matching_issue_is_applicable(self):
        state = {
            "issues": {
                "smells::server.ts::dead_useeffect": {
                    "status": "open",
                    "detector": "smells",
                    "detail": {"smell_id": "dead_useeffect"},
                }
            }
        }
        assert _fixer_has_applicable_issues(state, "smells", "dead-useeffect") is True

    def test_smells_with_no_matching_issue_is_not_applicable(self):
        state = {
            "issues": {
                "smells::server.ts::debug_tag": {
                    "status": "open",
                    "detector": "smells",
                    "detail": {"smell_id": "debug_tag"},
                }
            }
        }
        assert _fixer_has_applicable_issues(state, "smells", "dead-useeffect") is False

    def test_smells_resolved_issue_not_counted(self):
        state = {
            "issues": {
                "smells::server.ts::dead_useeffect": {
                    "status": "fixed",
                    "detector": "smells",
                    "detail": {"smell_id": "dead_useeffect"},
                }
            }
        }
        assert _fixer_has_applicable_issues(state, "smells", "dead-useeffect") is False

    def test_smells_empty_issues_not_applicable(self, empty_state):
        assert _fixer_has_applicable_issues(empty_state, "smells", "dead-useeffect") is False
        assert _fixer_has_applicable_issues(empty_state, "smells", "empty-if-chain") is False


class TestSmellsActionWithNoReact:
    """Regression tests for issue #127 — dead-useeffect suggested on non-React projects."""

    def test_smells_with_no_useeffect_issues_gets_manual_fix(self, empty_state):
        """When smells issues exist but none are dead_useeffect, no auto-fix for it."""
        # State has a non-useeffect smell but by_detector still shows smells count
        state = dict(empty_state)
        state["work_items"] = {
            "smells::server.ts::debug_tag": {
                "status": "open",
                "detector": "smells",
                "file": "server.ts",
                "detail": {"smell_id": "debug_tag"},
            }
        }
        result = _compute_actions(
            ActionContext(
                by_detector={"smells": 1},
                dimension_scores={},
                state=state,
                debt={},
                lang="typescript",
            )
        )
        smells_actions = [a for a in result if a.get("detector") == "smells"]
        assert smells_actions, "expected a smells action"
        # Should NOT suggest dead-useeffect since there are no dead_useeffect issues
        assert all("dead-useeffect" not in a.get("command", "") for a in smells_actions)

    def test_smells_with_dead_useeffect_issue_gets_auto_fix(self, empty_state):
        """When a dead_useeffect issue exists, dead-useeffect fixer is suggested."""
        state = dict(empty_state)
        state["work_items"] = {
            "smells::app.tsx::dead_useeffect": {
                "status": "open",
                "detector": "smells",
                "file": "app.tsx",
                "detail": {"smell_id": "dead_useeffect"},
            }
        }
        result = _compute_actions(
            ActionContext(
                by_detector={"smells": 1},
                dimension_scores={},
                state=state,
                debt={},
                lang="typescript",
            )
        )
        smells_actions = [a for a in result if a.get("detector") == "smells"]
        assert smells_actions
        assert any("dead-useeffect" in a.get("command", "") for a in smells_actions)

    def test_smells_with_empty_if_chain_issue_gets_correct_fixer(self, empty_state):
        """When only empty_if_chain issues exist, empty-if-chain fixer is suggested."""
        state = dict(empty_state)
        state["work_items"] = {
            "smells::util.ts::empty_if_chain": {
                "status": "open",
                "detector": "smells",
                "file": "util.ts",
                "detail": {"smell_id": "empty_if_chain"},
            }
        }
        result = _compute_actions(
            ActionContext(
                by_detector={"smells": 1},
                dimension_scores={},
                state=state,
                debt={},
                lang="typescript",
            )
        )
        smells_actions = [a for a in result if a.get("detector") == "smells"]
        assert smells_actions
        assert any("empty-if-chain" in a.get("command", "") for a in smells_actions)


class TestComputeTools:
    def test_empty(self):
        result = _compute_tools({}, {}, "typescript", {})
        assert "fixers" in result
        assert "move" in result
        assert "plan" in result

    def test_fixers_only_when_open(self):
        result = _compute_tools({"unused": 5}, {}, "typescript", {})
        assert len(result["fixers"]) >= 1

    def test_no_fixers_for_python(self):
        state = {"lang_capabilities": {"python": {"fixers": []}}}
        result = _compute_tools({"unused": 5}, state, "python", {})
        assert result["fixers"] == []

    def test_move_relevant_with_coupling(self):
        result = _compute_tools({"coupling": 3}, {}, "typescript", {})
        assert result["move"]["relevant"] is True

    def test_move_not_relevant_empty(self):
        result = _compute_tools({}, {}, "typescript", {})
        assert result["move"]["relevant"] is False
