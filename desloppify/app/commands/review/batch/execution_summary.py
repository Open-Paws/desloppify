"""Run-summary writer construction for batch execution."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from ..batches_runtime import BatchRunSummaryConfig
from ..batches_runtime import write_run_summary as _write_run_summary_impl


def build_run_summary_writer(
    *,
    run_dir: Path,
    summary_created_at: str,
    stamp: str,
    runner: str,
    run_parallel: bool,
    selected_indexes: list[int],
    allow_partial: bool,
    max_parallel_batches: int,
    batch_timeout_seconds: int,
    batch_max_retries: int,
    batch_retry_backoff_seconds: float,
    heartbeat_seconds: float,
    stall_warning_seconds: int,
    stall_kill_seconds: int,
    immutable_packet_path: Path,
    prompt_packet_path: Path,
    logs_dir: Path,
    run_log_path: Path,
    batch_status: dict[str, dict[str, object]],
    safe_write_text_fn,
    colorize_fn,
    append_run_log,
):
    """Create the bound write_run_summary callable for a run."""
    run_summary_path = run_dir / "run_summary.json"
    summary_config = BatchRunSummaryConfig(
        created_at=summary_created_at,
        run_stamp=stamp,
        runner=runner,
        run_parallel=run_parallel,
        selected_indexes=selected_indexes,
        allow_partial=allow_partial,
        max_parallel_batches=max_parallel_batches,
        batch_timeout_seconds=batch_timeout_seconds,
        batch_max_retries=batch_max_retries,
        batch_retry_backoff_seconds=batch_retry_backoff_seconds,
        heartbeat_seconds=heartbeat_seconds,
        stall_warning_seconds=stall_warning_seconds,
        stall_kill_seconds=stall_kill_seconds,
        immutable_packet_path=immutable_packet_path,
        prompt_packet_path=prompt_packet_path,
        run_dir=run_dir,
        logs_dir=logs_dir,
        run_log_path=run_log_path,
    )
    return partial(
        _write_run_summary_impl,
        summary_path=run_summary_path,
        summary_config=summary_config,
        batch_status=batch_status,
        safe_write_text_fn=safe_write_text_fn,
        colorize_fn=colorize_fn,
        append_run_log_fn=append_run_log,
    )


__all__ = ["build_run_summary_writer"]
