"""Progress and heartbeat reporting helpers for batch execution."""

from __future__ import annotations

from datetime import UTC, datetime

from ..runner_parallel import BatchProgressEvent


def record_execution_issue(append_run_log_fn, batch_index: int, exc: Exception) -> None:
    """Record one execute_batches callback/task failure in run.log."""
    if batch_index < 0:
        append_run_log_fn(f"execution-error heartbeat error={exc}")
        return
    append_run_log_fn(f"execution-error batch={batch_index + 1} error={exc}")


def _handle_heartbeat(
    *,
    details: dict,
    total_batches: int,
    stall_warning_seconds: float,
    stall_warned_batches: set[int],
    append_run_log,
    colorize_fn,
) -> None:
    """Handle a heartbeat progress event — print status and stall warnings."""
    active = details.get("active_batches")
    queued = details.get("queued_batches", [])
    elapsed = details.get("elapsed_seconds", {})
    if not isinstance(active, list):
        active = []
    if not isinstance(queued, list):
        queued = []
    if not active and not queued:
        return
    segments: list[str] = []
    for idx in active[:6]:
        secs = 0
        if isinstance(elapsed, dict):
            raw_secs = elapsed.get(idx, 0)
            secs = int(raw_secs) if isinstance(raw_secs, int | float) else 0
        segments.append(f"#{idx + 1}:{secs}s")
    if len(active) > 6:
        segments.append(f"+{len(active) - 6} more")
    queued_segment = ""
    if queued:
        queued_segment = f", queued {len(queued)}"
    print(
        colorize_fn(
            "  Batch heartbeat: "
            f"{len(active)}/{total_batches} active{queued_segment} "
            f"({', '.join(segments) if segments else 'running batches pending'})",
            "dim",
        )
    )
    append_run_log(
        "heartbeat "
        f"active={[idx + 1 for idx in active]} queued={[idx + 1 for idx in queued]} "
        f"elapsed={{{', '.join(f'{idx + 1}:{elapsed.get(idx, 0)}' for idx in active)}}}"
    )
    if stall_warning_seconds > 0 and isinstance(elapsed, dict):
        slow_active = [
            idx
            for idx in active
            if isinstance(elapsed.get(idx), int | float)
            and int(elapsed.get(idx) or 0) >= stall_warning_seconds
        ]
        newly_warned = [idx for idx in slow_active if idx not in stall_warned_batches]
        if newly_warned:
            stall_warned_batches.update(newly_warned)
            warning_message = (
                "  Stall warning: batches "
                f"{[idx + 1 for idx in sorted(newly_warned)]} exceeded "
                f"{stall_warning_seconds}s elapsed. "
                "This may be normal for long runs; review run.log and batch logs."
            )
            print(colorize_fn(warning_message, "yellow"))
            append_run_log(
                "stall-warning "
                f"threshold={stall_warning_seconds}s batches={[idx + 1 for idx in sorted(newly_warned)]}"
            )


def build_progress_reporter(
    *,
    batch_positions: dict[int, int],
    batch_status: dict[str, dict[str, object]],
    stall_warned_batches: set[int],
    total_batches: int,
    stall_warning_seconds: float,
    prompt_files: dict,
    output_files: dict,
    log_files: dict,
    append_run_log,
    colorize_fn,
):
    """Build the progress callback closure used during batch execution."""

    def _report_progress(
        progress_event: BatchProgressEvent,
    ) -> None:
        batch_index = progress_event.batch_index
        event = progress_event.event
        code = progress_event.code
        details = progress_event.details
        if event == "heartbeat":
            _handle_heartbeat(
                details=details,
                total_batches=total_batches,
                stall_warning_seconds=stall_warning_seconds,
                stall_warned_batches=stall_warned_batches,
                append_run_log=append_run_log,
                colorize_fn=colorize_fn,
            )
            return

        position = batch_positions.get(batch_index, 0)
        key = str(batch_index + 1)
        state = batch_status.setdefault(
            key,
            {
                "position": position,
                "status": "pending",
                "prompt_path": str(prompt_files.get(batch_index, "")),
                "result_path": str(output_files.get(batch_index, "")),
                "log_path": str(log_files.get(batch_index, "")),
            },
        )
        if event == "queued":
            state["status"] = "queued"
            print(
                colorize_fn(
                    f"  Batch {position}/{total_batches} queued (#{batch_index + 1})",
                    "dim",
                )
            )
            append_run_log(f"batch-queued batch={batch_index + 1} position={position}/{total_batches}")
            return
        if event == "start":
            state["status"] = "running"
            state["started_at"] = datetime.now(UTC).isoformat(timespec="seconds")
            print(
                colorize_fn(
                    f"  Batch {position}/{total_batches} started (#{batch_index + 1})",
                    "dim",
                )
            )
            append_run_log(f"batch-start batch={batch_index + 1} position={position}/{total_batches}")
            return
        if event == "done":
            status = "done" if code == 0 else f"failed ({code})"
            tone = "dim" if code == 0 else "yellow"
            elapsed_seconds = details.get("elapsed_seconds")
            elapsed_suffix = ""
            if isinstance(elapsed_seconds, int | float):
                elapsed_suffix = f" in {int(max(0, elapsed_seconds))}s"
                state["elapsed_seconds"] = int(max(0, elapsed_seconds))
            state["status"] = "succeeded" if code == 0 else "failed"
            state["exit_code"] = int(code) if isinstance(code, int) else code
            state["completed_at"] = datetime.now(UTC).isoformat(timespec="seconds")
            if batch_index in stall_warned_batches:
                stall_warned_batches.discard(batch_index)
            print(
                colorize_fn(
                    f"  Batch {position}/{total_batches} {status}{elapsed_suffix} (#{batch_index + 1})",
                    tone,
                )
            )
            append_run_log(
                f"batch-done batch={batch_index + 1} position={position}/{total_batches} "
                f"code={code} elapsed={state.get('elapsed_seconds', 0)}"
            )

    return _report_progress


def build_initial_batch_status(
    *,
    selected_indexes: list[int],
    batch_positions: dict[int, int],
    prompt_files: dict,
    output_files: dict,
    log_files: dict,
) -> dict[str, dict[str, object]]:
    """Create the initial per-batch status payload."""
    return {
        str(idx + 1): {
            "position": batch_positions.get(idx, 0),
            "status": "pending",
            "prompt_path": str(prompt_files[idx]),
            "result_path": str(output_files[idx]),
            "log_path": str(log_files[idx]),
        }
        for idx in selected_indexes
    }


def mark_interrupted_batches(
    *,
    selected_indexes: list[int],
    batch_status: dict[str, dict[str, object]],
    batch_positions: dict[int, int],
) -> None:
    """Mark still-pending/active batches as interrupted after Ctrl-C."""
    for idx in selected_indexes:
        key = str(idx + 1)
        state_entry = batch_status.setdefault(
            key,
            {"position": batch_positions.get(idx, 0), "status": "pending"},
        )
        if state_entry.get("status") in {"pending", "queued", "running"}:
            state_entry["status"] = "interrupted"


__all__ = [
    "build_initial_batch_status",
    "build_progress_reporter",
    "mark_interrupted_batches",
    "record_execution_issue",
]
