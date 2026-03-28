"""Direct coverage tests for review runner parallel progress helpers."""

from __future__ import annotations

import threading
import time

import desloppify.app.commands.review.runner_parallel.progress as progress_mod
from desloppify.app.commands.review.runner_parallel.types import BatchExecutionOptions


def test_coerce_batch_execution_options_defaults() -> None:
    options = progress_mod._coerce_batch_execution_options(None)

    assert options.run_parallel is False
    assert options.max_parallel_workers is None
    assert options.heartbeat_seconds == 15.0
    assert options.clock_fn is time.monotonic


def test_coerce_batch_execution_options_normalizes_invalid_types() -> None:
    options = BatchExecutionOptions(
        run_parallel=1,
        max_parallel_workers=True,
        heartbeat_seconds=True,
        clock_fn="not-callable",
    )

    resolved = progress_mod._coerce_batch_execution_options(options)

    assert resolved.run_parallel is True
    assert resolved.max_parallel_workers is None
    assert resolved.heartbeat_seconds is None
    assert resolved.clock_fn is time.monotonic


def test_coerce_batch_execution_options_keeps_valid_values() -> None:
    custom_clock = lambda: 42.0
    options = BatchExecutionOptions(
        run_parallel=False,
        max_parallel_workers=4,
        heartbeat_seconds=2.5,
        clock_fn=custom_clock,
    )

    resolved = progress_mod._coerce_batch_execution_options(options)

    assert resolved.run_parallel is False
    assert resolved.max_parallel_workers == 4
    assert resolved.heartbeat_seconds == 2.5
    assert resolved.clock_fn is custom_clock


def test_progress_contract_none_for_non_callable() -> None:
    assert progress_mod._progress_contract(None) == "none"


def test_progress_contract_caches_callable() -> None:
    cache: dict[int, str] = {}

    def cb(_event):
        return None

    assert progress_mod._progress_contract(cb, contract_cache=cache) == "event"
    assert cache[id(cb)] == "event"
    assert progress_mod._progress_contract(cb, contract_cache=cache) == "event"


def test_emit_progress_noop_for_non_callable() -> None:
    err = progress_mod._emit_progress(None, 0, "start", code=0)
    assert err is None


def test_emit_progress_emits_event_payload_copy() -> None:
    events = []
    details = {"k": "v"}

    def cb(event):
        events.append(event)

    err = progress_mod._emit_progress(
        cb,
        batch_index=2,
        event="done",
        code=0,
        details=details,
        contract_cache={},
    )

    assert err is None
    assert len(events) == 1
    evt = events[0]
    assert evt.batch_index == 2
    assert evt.event == "done"
    assert evt.code == 0
    assert evt.details == {"k": "v"}
    assert evt.details is not details


def test_emit_progress_wraps_callback_errors() -> None:
    def bad_cb(_event):
        raise ValueError("boom")

    err = progress_mod._emit_progress(bad_cb, 3, "heartbeat")

    assert isinstance(err, RuntimeError)
    assert "progress callback failed" in str(err)
    assert "batch=3" in str(err)


def test_record_execution_error_logs_and_tracks_failure() -> None:
    failures: set[int] = set()
    captured: list[tuple[int, Exception]] = []
    exc = RuntimeError("x")

    progress_mod._record_execution_error(
        error_log_fn=lambda idx, err: captured.append((idx, err)),
        failures=failures,
        idx=7,
        exc=exc,
    )

    assert failures == {7}
    assert captured == [(7, exc)]


def test_record_execution_error_best_effort_on_logger_failure(monkeypatch) -> None:
    failures: set[int] = set()
    calls: list[tuple[str, Exception]] = []

    def bad_logger(_idx, _exc):
        raise TypeError("bad logger")

    monkeypatch.setattr(
        progress_mod,
        "log_best_effort_failure",
        lambda _logger, action, err: calls.append((action, err)),
    )

    progress_mod._record_execution_error(
        error_log_fn=bad_logger,
        failures=failures,
        idx=9,
        exc=RuntimeError("broken"),
    )

    assert failures == {9}
    assert calls and calls[0][0] == "record batch execution error via callback"


def test_record_progress_error_tracks_and_logs() -> None:
    failures: set[int] = set()
    lock = threading.Lock()
    captured: list[tuple[int, Exception]] = []
    err = RuntimeError("boom")

    progress_mod._record_progress_error(
        idx=4,
        err=err,
        progress_failures=failures,
        lock=lock,
        error_log_fn=lambda idx, exc: captured.append((idx, exc)),
    )

    assert failures == {4}
    assert captured == [(4, err)]


def test_record_progress_error_best_effort_on_logger_failure(monkeypatch) -> None:
    failures: set[int] = set()
    lock = threading.Lock()
    calls: list[tuple[str, Exception]] = []

    def bad_logger(_idx, _exc):
        raise ValueError("broken")

    monkeypatch.setattr(
        progress_mod,
        "log_best_effort_failure",
        lambda _logger, action, err: calls.append((action, err)),
    )

    progress_mod._record_progress_error(
        idx=1,
        err=RuntimeError("x"),
        progress_failures=failures,
        lock=lock,
        error_log_fn=bad_logger,
    )

    assert failures == {1}
    assert calls and calls[0][0] == "record batch progress failure via callback"
