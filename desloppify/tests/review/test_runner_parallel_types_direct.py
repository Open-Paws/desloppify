"""Direct coverage tests for review runner parallel type payloads."""

from __future__ import annotations

from desloppify.app.commands.review.runner_parallel.types import (
    BatchExecutionOptions,
    BatchProgressEvent,
    BatchResult,
)


def test_batch_progress_event_defaults_details_dict() -> None:
    evt = BatchProgressEvent(batch_index=3, event="start")
    assert evt.batch_index == 3
    assert evt.event == "start"
    assert evt.code is None
    assert evt.details == {}


def test_batch_execution_options_defaults() -> None:
    opts = BatchExecutionOptions(run_parallel=True)
    assert opts.run_parallel is True
    assert opts.max_parallel_workers is None
    assert opts.heartbeat_seconds == 15.0
    assert callable(opts.clock_fn)


def test_batch_result_to_dict_contains_all_fields() -> None:
    result = BatchResult(
        batch_index=2,
        assessments={"naming": 75.0},
        dimension_notes={"naming": {"summary": "ok"}},
        dimension_judgment={"naming": {"verdict": "medium"}},
        issues=[{"id": "review::a"}],
        quality={"coverage": 0.8},
    )

    payload = result.to_dict()

    assert payload["batch_index"] == 2
    assert payload["assessments"] == {"naming": 75.0}
    assert payload["dimension_notes"] == {"naming": {"summary": "ok"}}
    assert payload["dimension_judgment"] == {"naming": {"verdict": "medium"}}
    assert payload["issues"] == [{"id": "review::a"}]
    assert payload["quality"] == {"coverage": 0.8}


def test_batch_result_to_dict_preserves_empty_defaults() -> None:
    result = BatchResult(
        batch_index=0,
        assessments={},
        dimension_notes={},
    )

    payload = result.to_dict()

    assert payload == {
        "batch_index": 0,
        "assessments": {},
        "dimension_notes": {},
        "dimension_judgment": {},
        "issues": [],
        "quality": {},
    }
