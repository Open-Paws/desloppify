"""Tests for the progression event log."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from desloppify.engine._state.progression import (
    PROGRESSION_VERSION,
    _trim_if_needed,
    append_progression_event,
    build_execution_drain_event,
    build_postflight_scan_event,
    build_review_complete_event,
    build_scan_complete_event,
    build_scan_preflight_event,
    build_triage_complete_event,
    load_progression,
    maybe_append_entered_planning,
    maybe_append_execution_drain,
)


@pytest.fixture()
def progression_file(tmp_path: Path) -> Path:
    return tmp_path / "progression.jsonl"


def _mock_state(
    *,
    scan_count: int = 5,
    strict: float = 72.0,
    overall: float = 80.0,
    objective: float = 85.0,
    verified: float = 70.0,
    open_count: int = 3,
) -> dict:
    issues = {f"issue-{i}": {"status": "open"} for i in range(open_count)}
    return {
        "scan_count": scan_count,
        "strict_score": strict,
        "overall_score": overall,
        "objective_score": objective,
        "verified_strict_score": verified,
        "work_items": issues,
        "dimension_scores": {
            "naming": {"score": 80.0, "strict": 75.0},
            "complexity": {"score": 90.0, "strict": 88.0},
        },
        "scan_history": [],
    }


def _mock_plan(*, phase: str = "execute") -> dict:
    return {
        "refresh_state": {"lifecycle_phase": phase},
        "queue_order": [],
        "skipped": {},
        "epic_triage_meta": {},
    }


class TestAppendAndLoad:
    def test_true_append(self, progression_file: Path) -> None:
        """Two events produce 2 lines."""
        e1 = {"event_type": "test1", "schema_version": 1, "payload": {}}
        e2 = {"event_type": "test2", "schema_version": 1, "payload": {}}
        append_progression_event(e1, path=progression_file)
        append_progression_event(e2, path=progression_file)

        events = load_progression(progression_file)
        assert len(events) == 2
        assert events[0]["event_type"] == "test1"
        assert events[1]["event_type"] == "test2"

    def test_corrupt_line_resilience(
        self, progression_file: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Corrupt lines are skipped with warning; valid lines returned."""
        progression_file.write_text(
            'not valid json\n'
            '{"event_type":"valid","schema_version":1,"payload":{}}\n'
        )
        with caplog.at_level(logging.WARNING):
            events = load_progression(progression_file)
        assert len(events) == 1
        assert events[0]["event_type"] == "valid"
        assert any("corrupt" in r.message for r in caplog.records)

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.jsonl"
        assert load_progression(missing) == []

    def test_lock_timeout_logs_warning(
        self, progression_file: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Lock acquisition failure logs warning but still appends."""
        event = {"event_type": "test", "schema_version": 1, "payload": {}}
        with (
            patch(
                "desloppify.engine._state.progression._acquire_lock",
                side_effect=TimeoutError("test timeout"),
            ),
            caplog.at_level(logging.WARNING),
        ):
            append_progression_event(event, path=progression_file)

        assert any("lock" in r.message.lower() for r in caplog.records)
        events = load_progression(progression_file)
        assert len(events) == 1


class TestTrim:
    def test_trim_enforcement(self, progression_file: Path) -> None:
        """2001 lines trimmed to 2000."""
        lines = [
            json.dumps({"event_type": "e", "n": i}) + "\n"
            for i in range(2001)
        ]
        progression_file.write_text("".join(lines))
        _trim_if_needed(progression_file, max_lines=2000)

        result = load_progression(progression_file)
        assert len(result) == 2000
        assert result[0]["n"] == 1  # first line (n=0) was trimmed

    def test_no_trim_when_under_limit(self, progression_file: Path) -> None:
        lines = [
            json.dumps({"event_type": "e", "n": i}) + "\n"
            for i in range(100)
        ]
        progression_file.write_text("".join(lines))
        _trim_if_needed(progression_file, max_lines=2000)
        assert len(load_progression(progression_file)) == 100


class TestBuilders:
    def test_scan_preflight(self) -> None:
        plan = _mock_plan()
        event = build_scan_preflight_event(
            plan,
            result="blocked",
            reason="5 items remaining",
            queue_count=5,
            phase_before="execute",
        )
        assert event["event_type"] == "scan_preflight"
        assert event["schema_version"] == PROGRESSION_VERSION
        assert event["payload"]["result"] == "blocked"
        assert event["payload"]["queue_item_count"] == 5
        assert event["phase_before"] == "execute"

    def test_scan_complete(self) -> None:
        state = _mock_state()
        plan = _mock_plan()
        diff = {"new": 3, "auto_resolved": 1, "reopened": 0, "total_current": 10}
        prev_scores = {"overall": 78.0, "strict": 70.0}
        prev_dim_scores = {
            "naming": {"score": 75.0, "strict": 70.0},
            "complexity": {"score": 88.0, "strict": 85.0},
        }
        event = build_scan_complete_event(
            state,
            plan,
            diff,
            prev_scores=prev_scores,
            lang="python",
            phase_before="scan",
            execution_summary={"resolve": 2, "skip": 1},
            prev_dimension_scores=prev_dim_scores,
        )
        assert event["event_type"] == "scan_complete"
        payload = event["payload"]
        assert payload["scores"]["strict"] == 72.0
        assert payload["prev_scores"] == prev_scores
        assert payload["scan_diff"]["new"] == 3
        assert payload["dimension_scores"]["naming"]["score"] == 80.0
        assert payload["lang"] == "python"
        assert payload["execution_summary"]["resolve"] == 2
        # Dimension deltas: naming strict went 70→75, complexity 85→88
        assert payload["dimension_deltas"]["naming"] == 5.0
        assert payload["dimension_deltas"]["complexity"] == 3.0
        assert payload["prev_dimension_scores"] == prev_dim_scores

    def test_postflight_scan(self) -> None:
        plan = _mock_plan(phase="plan")
        event = build_postflight_scan_event(
            plan,
            scan_count_marker=10,
            phase_before="scan",
        )
        assert event["event_type"] == "postflight_scan_completed"
        assert event["payload"]["scan_count_marker"] == 10

    def test_review_complete(self) -> None:
        state = _mock_state()
        plan = _mock_plan()
        event = build_review_complete_event(
            state,
            plan,
            assessment_mode="trusted_internal",
            covered_count=3,
            new_ids_count=2,
            phase_before="review_postflight",
            covered_dimensions=["naming", "complexity", "error_handling"],
            new_review_ids=["rev-1", "rev-2"],
            dimension_notes_summary={"naming": "Consistent snake_case in api/"},
            review_issue_summaries=[
                {"dimension": "naming", "summary": "Inconsistent naming in utils", "confidence": "high"},
            ],
        )
        assert event["event_type"] == "subjective_review_completed"
        payload = event["payload"]
        assert payload["assessment_mode"] == "trusted_internal"
        assert payload["covered_dimension_count"] == 3
        assert payload["covered_dimensions"] == ["naming", "complexity", "error_handling"]
        assert payload["new_review_ids_count"] == 2
        assert payload["new_review_ids"] == ["rev-1", "rev-2"]
        assert payload["dimension_notes_summary"]["naming"] == "Consistent snake_case in api/"
        assert len(payload["review_issue_summaries"]) == 1
        assert "scores" in payload
        assert "dimension_scores" in payload

    def test_triage_complete(self) -> None:
        state = _mock_state()
        plan = _mock_plan()
        plan["epic_triage_meta"]["issue_dispositions"] = {
            "id1": {"verdict": "genuine"},
            "id2": {"verdict": "genuine"},
            "id3": {"verdict": "false_positive"},
        }
        plan["skipped"] = {"s1": {}, "s2": {}}
        clusters = {"c1": {"issue_ids": ["id1"]}, "c2": {"issue_ids": ["id2"]}}
        event = build_triage_complete_event(
            plan,
            state,
            completion_mode="manual_triage",
            strategy_summary="Focus on naming first",
            organized=2,
            total=3,
            clusters=clusters,
            phase_before="triage_postflight",
        )
        assert event["event_type"] == "triage_complete"
        payload = event["payload"]
        assert payload["verdict_counts"]["genuine"] == 2
        assert payload["verdict_counts"]["false_positive"] == 1
        assert payload["cluster_count"] == 2
        assert payload["skip_count"] == 2

    def test_execution_drain(self) -> None:
        state = _mock_state()
        plan = _mock_plan()
        event = build_execution_drain_event(
            state,
            plan,
            trigger_action="resolve",
            issue_ids=["id1", "id2"],
            cluster_name="naming-fixes",
            phase_before="execute",
        )
        assert event["event_type"] == "execution_drain"
        payload = event["payload"]
        assert payload["trigger_action"] == "resolve"
        assert payload["issue_ids"] == ["id1", "id2"]
        assert payload["cluster_name"] == "naming-fixes"
        assert "scores" in payload


class TestConditionalHelpers:
    def test_entered_planning_on_phase_change(
        self, progression_file: Path
    ) -> None:
        """Phase change to planning phase fires exactly one event."""
        state = _mock_state()
        plan = _mock_plan(phase="plan")
        with patch(
            "desloppify.engine._state.progression.progression_path",
            return_value=progression_file,
        ):
            maybe_append_entered_planning(
                state,
                plan,
                source_command="resolve",
                trigger_action="workflow_resolve",
                issue_ids=["id1"],
                phase_before="execute",
            )
        events = load_progression(progression_file)
        planning_events = [
            e for e in events if e["event_type"] == "entered_planning_mode"
        ]
        assert len(planning_events) == 1

    def test_no_entered_planning_when_same_phase(
        self, progression_file: Path
    ) -> None:
        state = _mock_state()
        plan = _mock_plan(phase="execute")
        with patch(
            "desloppify.engine._state.progression.progression_path",
            return_value=progression_file,
        ):
            maybe_append_entered_planning(
                state,
                plan,
                source_command="resolve",
                trigger_action="resolve",
                issue_ids=["id1"],
                phase_before="execute",
            )
        events = load_progression(progression_file)
        assert not any(
            e["event_type"] == "entered_planning_mode" for e in events
        )

    def test_execution_drain_on_phase_change(
        self, progression_file: Path
    ) -> None:
        state = _mock_state()
        plan = _mock_plan(phase="plan")
        with patch(
            "desloppify.engine._state.progression.progression_path",
            return_value=progression_file,
        ):
            maybe_append_execution_drain(
                state,
                plan,
                trigger_action="resolve",
                issue_ids=["id1"],
                phase_before="execute",
            )
        events = load_progression(progression_file)
        drain_events = [
            e for e in events if e["event_type"] == "execution_drain"
        ]
        assert len(drain_events) == 1

    def test_no_execution_drain_when_same_phase(
        self, progression_file: Path
    ) -> None:
        state = _mock_state()
        plan = _mock_plan(phase="execute")
        with patch(
            "desloppify.engine._state.progression.progression_path",
            return_value=progression_file,
        ):
            maybe_append_execution_drain(
                state,
                plan,
                trigger_action="resolve",
                issue_ids=["id1"],
                phase_before="execute",
            )
        events = load_progression(progression_file)
        assert not any(e["event_type"] == "execution_drain" for e in events)

    def test_scan_without_phase_change_still_records(
        self, progression_file: Path
    ) -> None:
        """scan_complete is unconditional — fires even when phase_before == phase_after."""
        state = _mock_state()
        plan = _mock_plan(phase="execute")
        event = build_scan_complete_event(
            state,
            plan,
            {"new": 0, "auto_resolved": 0, "reopened": 0, "total_current": 5},
            prev_scores=None,
            lang="python",
            phase_before="execute",
            execution_summary={},
        )
        append_progression_event(event, path=progression_file)
        events = load_progression(progression_file)
        assert len(events) == 1
        assert events[0]["phase_before"] == "execute"
        assert events[0]["phase_after"] == "execute"
