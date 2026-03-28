"""Parallel execution internals tests for review runner orchestration."""

from __future__ import annotations

import threading
from concurrent.futures import Future

from desloppify.app.commands.review.runner_parallel.execution import (
    _complete_parallel_future,
    _heartbeat,
    _resolve_parallel_runtime,
)


class TestResolveParallelRuntime:
    """_resolve_parallel_runtime: normalizes worker count and heartbeat."""

    def test_default_workers_capped_by_task_count(self):
        workers, _ = _resolve_parallel_runtime(
            indexes=[0, 1, 2],
            max_parallel_workers=None,
            heartbeat_seconds=10.0,
        )
        assert workers == 3  # min(3, 8)

    def test_custom_workers(self):
        workers, _ = _resolve_parallel_runtime(
            indexes=list(range(20)),
            max_parallel_workers=4,
            heartbeat_seconds=None,
        )
        assert workers == 4

    def test_workers_capped_at_task_count(self):
        """Requested workers > tasks => capped to task count."""
        workers, _ = _resolve_parallel_runtime(
            indexes=[0, 1],
            max_parallel_workers=16,
            heartbeat_seconds=None,
        )
        assert workers == 2

    def test_invalid_workers_uses_default(self):
        workers, _ = _resolve_parallel_runtime(
            indexes=list(range(10)),
            max_parallel_workers=-1,
            heartbeat_seconds=None,
        )
        assert workers == 8  # default capped at task count (10)

    def test_heartbeat_enabled(self):
        _, heartbeat = _resolve_parallel_runtime(
            indexes=[0],
            max_parallel_workers=1,
            heartbeat_seconds=15.0,
        )
        assert heartbeat == 15.0

    def test_heartbeat_disabled(self):
        _, heartbeat = _resolve_parallel_runtime(
            indexes=[0],
            max_parallel_workers=1,
            heartbeat_seconds=None,
        )
        assert heartbeat is None

    def test_heartbeat_zero_disabled(self):
        _, heartbeat = _resolve_parallel_runtime(
            indexes=[0],
            max_parallel_workers=1,
            heartbeat_seconds=0,
        )
        assert heartbeat is None

    def test_heartbeat_negative_disabled(self):
        _, heartbeat = _resolve_parallel_runtime(
            indexes=[0],
            max_parallel_workers=1,
            heartbeat_seconds=-5,
        )
        assert heartbeat is None


class TestCompleteParallelFuture:
    """_complete_parallel_future: handles future result + progress callbacks."""

    def _make_future(self, result=None, exception=None) -> Future:
        """Create a finished Future with a preset result or exception."""
        f = Future()
        if exception is not None:
            f.set_exception(exception)
        else:
            f.set_result(result)
        return f

    def test_success_code_zero(self):
        """Successful future with code 0 => not added to failures."""
        future = self._make_future(result=0)
        futures = {future: 5}
        failures: set[int] = set()
        progress_failures: set[int] = set()
        started_at = {5: 100.0}
        lock = threading.Lock()

        _complete_parallel_future(
            future=future,
            futures=futures,
            progress_fn=None,
            error_log_fn=None,
            contract_cache={},
            failures=failures,
            progress_failures=progress_failures,
            started_at=started_at,
            lock=lock,
            clock_fn=lambda: 110.0,
        )
        assert 5 not in failures

    def test_nonzero_code_adds_to_failures(self):
        """Future returning nonzero code => added to failures."""
        future = self._make_future(result=1)
        futures = {future: 3}
        failures: set[int] = set()
        progress_failures: set[int] = set()
        started_at = {3: 100.0}
        lock = threading.Lock()

        _complete_parallel_future(
            future=future,
            futures=futures,
            progress_fn=None,
            error_log_fn=None,
            contract_cache={},
            failures=failures,
            progress_failures=progress_failures,
            started_at=started_at,
            lock=lock,
            clock_fn=lambda: 110.0,
        )
        assert 3 in failures

    def test_exception_adds_to_failures(self):
        """Future that raised an exception => added to failures via error handling."""
        future = self._make_future(exception=RuntimeError("boom"))
        futures = {future: 7}
        failures: set[int] = set()
        progress_failures: set[int] = set()
        started_at = {7: 100.0}
        lock = threading.Lock()
        errors_logged: list = []

        _complete_parallel_future(
            future=future,
            futures=futures,
            progress_fn=None,
            error_log_fn=lambda idx, exc: errors_logged.append((idx, exc)),
            contract_cache={},
            failures=failures,
            progress_failures=progress_failures,
            started_at=started_at,
            lock=lock,
            clock_fn=lambda: 110.0,
        )
        assert 7 in failures
        assert len(errors_logged) == 1
        assert errors_logged[0][0] == 7

    def test_progress_failure_does_not_mark_as_failure(self):
        """Prior progress callback failures are logged but don't fail successful tasks."""
        future = self._make_future(result=0)
        futures = {future: 2}
        failures: set[int] = set()
        progress_failures: set[int] = {2}  # pre-populated
        started_at = {2: 100.0}
        lock = threading.Lock()

        _complete_parallel_future(
            future=future,
            futures=futures,
            progress_fn=None,
            error_log_fn=None,
            contract_cache={},
            failures=failures,
            progress_failures=progress_failures,
            started_at=started_at,
            lock=lock,
            clock_fn=lambda: 110.0,
        )
        assert 2 not in failures

    def test_missing_started_at_uses_clock(self):
        """If idx not in started_at, falls back to clock_fn for elapsed calc."""
        future = self._make_future(result=0)
        futures = {future: 9}
        failures: set[int] = set()
        progress_failures: set[int] = set()
        started_at: dict[int, float] = {}  # no entry for idx=9
        lock = threading.Lock()
        clock_calls = []

        def clock():
            clock_calls.append(1)
            return 200.0

        _complete_parallel_future(
            future=future,
            futures=futures,
            progress_fn=None,
            error_log_fn=None,
            contract_cache={},
            failures=failures,
            progress_failures=progress_failures,
            started_at=started_at,
            lock=lock,
            clock_fn=clock,
        )
        # Should still succeed without errors
        assert 9 not in failures

    def test_progress_fn_called_on_completion(self):
        """Progress callback receives a 'done' event on successful completion."""
        future = self._make_future(result=0)
        futures = {future: 4}
        failures: set[int] = set()
        progress_failures: set[int] = set()
        started_at = {4: 100.0}
        lock = threading.Lock()
        events = []

        _complete_parallel_future(
            future=future,
            futures=futures,
            progress_fn=lambda evt: events.append(evt),
            error_log_fn=None,
            contract_cache={},
            failures=failures,
            progress_failures=progress_failures,
            started_at=started_at,
            lock=lock,
            clock_fn=lambda: 110.0,
        )
        assert len(events) == 1
        assert events[0].event == "done"
        assert events[0].batch_index == 4
        assert events[0].code == 0


class TestHeartbeat:
    """_heartbeat: emits progress with active/queued batch status."""

    def test_heartbeat_emits_event(self):
        """Heartbeat sends a progress event with active/queued info."""
        # Set up two pending futures: one started, one not yet
        f1, f2 = Future(), Future()
        futures = {f1: 0, f2: 1}
        started_at = {0: 100.0}  # only idx=0 started
        lock = threading.Lock()
        events = []

        _heartbeat(
            {f1, f2},
            futures,
            started_at,
            lock,
            [0, 1],
            lambda evt: events.append(evt),
            lambda: 115.0,
            contract_cache={},
        )
        assert len(events) == 1
        evt = events[0]
        assert evt.event == "heartbeat"
        assert evt.batch_index == -1
        assert 0 in evt.details["active_batches"]
        assert 1 in evt.details["queued_batches"]
        assert evt.details["active_count"] == 1
        assert evt.details["queued_count"] == 1

    def test_heartbeat_no_progress_fn(self):
        """Heartbeat with non-callable progress_fn => no error."""
        f1 = Future()
        futures = {f1: 0}
        started_at = {0: 100.0}
        lock = threading.Lock()
        # Should not raise
        _heartbeat(
            {f1}, futures, started_at, lock, [0], None, lambda: 110.0,
            contract_cache={},
        )

    def test_heartbeat_error_logged(self):
        """When progress callback fails, error_log_fn receives it."""
        f1 = Future()
        futures = {f1: 0}
        started_at = {0: 100.0}
        lock = threading.Lock()
        errors = []

        def bad_progress(evt):
            raise ValueError("callback broken")

        _heartbeat(
            {f1}, futures, started_at, lock, [0],
            bad_progress, lambda: 110.0,
            error_log_fn=lambda idx, exc: errors.append((idx, exc)),
            contract_cache={},
        )
        assert len(errors) == 1
        assert errors[0][0] == -1  # heartbeat uses idx=-1

    def test_heartbeat_elapsed_calculation(self):
        """Elapsed time is computed per active batch."""
        f1 = Future()
        futures = {f1: 0}
        started_at = {0: 100.0}
        lock = threading.Lock()
        events = []

        _heartbeat(
            {f1}, futures, started_at, lock, [0],
            lambda evt: events.append(evt),
            lambda: 145.0,  # 45s elapsed
            contract_cache={},
        )
        assert events[0].details["elapsed_seconds"][0] == 45


# ── Integration-style test: serial execution ─────────────────────
# Skipping _execute_serial and _execute_parallel integration tests because
# they require the full _emit_progress / BatchProgressEvent pipeline and
# would effectively just be testing the threading machinery with mocks
# that replicate the internal wiring. The unit tests above cover the
# individual decision points that matter most.
