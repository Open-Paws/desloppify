"""Batch execution orchestration for review command."""
from __future__ import annotations
import math
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any
from ..batches_runtime import build_batch_tasks, make_run_log_writer, resolve_run_log_path
from ..prompt_sections import explode_to_single_dimension
from ..runner_parallel import BatchExecutionOptions
from ..runtime.policy import resolve_batch_run_policy
from .execution_dry_run import maybe_handle_dry_run
from .execution_progress import (
    build_initial_batch_status,
    build_progress_reporter,
    mark_interrupted_batches,
    record_execution_issue,
)
from .execution_results import (
    collect_and_reconcile_results,
    enforce_import_coverage,
    import_and_finalize,
    log_run_start,
    merge_and_write_results,
)
from .execution_summary import build_run_summary_writer
from .scope import (
    normalize_dimension_list,
    print_preflight_dimension_scope_notice,
    require_batches,
    scored_dimensions_for_lang,
    validate_runner,
)
def do_run_batches(
    args,
    state,
    lang,
    state_file,
    *,
    config: dict[str, Any] | None,
    run_stamp_fn,
    load_or_prepare_packet_fn,
    selected_batch_indexes_fn,
    prepare_run_artifacts_fn,
    run_codex_batch_fn,
    execute_batches_fn,
    collect_batch_results_fn,
    print_failures_fn,
    print_failures_and_raise_fn,
    merge_batch_results_fn,
    build_import_provenance_fn,
    do_import_fn,
    run_followup_scan_fn,
    safe_write_text_fn,
    colorize_fn,
    project_root: Path,
    subagent_runs_dir: Path,
) -> None:
    """Run holistic investigation batches with a local subagent runner."""
    config = config or {}
    runner = getattr(args, "runner", "codex")
    validate_runner(runner, colorize_fn=colorize_fn)
    allow_partial = bool(getattr(args, "allow_partial", False))
    policy = resolve_batch_run_policy(args)
    run_parallel = policy.run_parallel
    max_parallel_batches = policy.max_parallel_batches
    heartbeat_seconds = policy.heartbeat_seconds
    batch_timeout_seconds = policy.batch_timeout_seconds
    batch_max_retries = policy.batch_max_retries
    batch_retry_backoff_seconds = policy.batch_retry_backoff_seconds
    stall_warning_seconds = policy.stall_warning_seconds
    stall_kill_seconds = policy.stall_kill_seconds
    stamp = run_stamp_fn()
    packet, immutable_packet_path, prompt_packet_path = load_or_prepare_packet_fn(
        args,
        state=state,
        lang=lang,
        config=config,
        stamp=stamp,
    )
    scan_path = str(getattr(args, "path", ".") or ".")
    packet_dimensions = normalize_dimension_list(packet.get("dimensions", []))
    scored_dimensions = scored_dimensions_for_lang(lang.name)
    print_preflight_dimension_scope_notice(
        selected_dims=packet_dimensions,
        scored_dims=scored_dimensions,
        explicit_selection=bool(getattr(args, "dimensions", None)),
        scan_path=scan_path,
        colorize_fn=colorize_fn,
    )
    suggested_prepare_cmd = f"desloppify review --prepare --path {scan_path}"
    raw_dim_prompts = packet.get("dimension_prompts")
    batches = explode_to_single_dimension(
        require_batches(
            packet,
            colorize_fn=colorize_fn,
            suggested_prepare_cmd=suggested_prepare_cmd,
        ),
        dimension_prompts=raw_dim_prompts if isinstance(raw_dim_prompts, dict) else None,
    )
    selected_indexes = selected_batch_indexes_fn(args, batch_count=len(batches))
    total_batches = len(selected_indexes)
    effective_workers = min(total_batches, max_parallel_batches) if run_parallel else 1
    waves = max(1, math.ceil(total_batches / max(1, effective_workers)))
    worst_case_seconds = waves * batch_timeout_seconds
    worst_case_minutes = max(1, math.ceil(worst_case_seconds / 60))
    print(
        colorize_fn(
            "  Runtime expectation: "
            f"{total_batches} batch(es), workers={effective_workers}, "
            f"timeout-per-batch={int(batch_timeout_seconds / 60)}m, "
            f"worst-case upper bound ~{worst_case_minutes}m.",
            "dim",
        )
    )
    run_dir, logs_dir, prompt_files, output_files, log_files = prepare_run_artifacts_fn(
        stamp=stamp,
        selected_indexes=selected_indexes,
        batches=batches,
        packet_path=prompt_packet_path,
        run_root=subagent_runs_dir,
        repo_root=project_root,
    )
    run_log_path = resolve_run_log_path(
        getattr(args, "run_log_file", None),
        project_root=project_root,
        run_dir=run_dir,
    )
    append_run_log = make_run_log_writer(run_log_path)
    log_run_start(
        append_run_log=append_run_log,
        colorize_fn=colorize_fn,
        run_log_path=run_log_path,
        run_dir=run_dir,
        immutable_packet_path=immutable_packet_path,
        prompt_packet_path=prompt_packet_path,
        runner=runner,
        run_parallel=run_parallel,
        max_parallel_batches=max_parallel_batches,
        batch_timeout_seconds=batch_timeout_seconds,
        heartbeat_seconds=heartbeat_seconds,
        stall_warning_seconds=stall_warning_seconds,
        stall_kill_seconds=stall_kill_seconds,
        batch_max_retries=batch_max_retries,
        batch_retry_backoff_seconds=batch_retry_backoff_seconds,
        worst_case_minutes=worst_case_minutes,
        selected_indexes=selected_indexes,
    )
    if maybe_handle_dry_run(
        args=args,
        stamp=stamp,
        selected_indexes=selected_indexes,
        run_dir=run_dir,
        logs_dir=logs_dir,
        immutable_packet_path=immutable_packet_path,
        prompt_packet_path=prompt_packet_path,
        prompt_files=prompt_files,
        output_files=output_files,
        safe_write_text_fn=safe_write_text_fn,
        colorize_fn=colorize_fn,
        append_run_log=append_run_log,
    ):
        return
    tasks = build_batch_tasks(
        selected_indexes=selected_indexes,
        prompt_files=prompt_files,
        output_files=output_files,
        log_files=log_files,
        project_root=project_root,
        run_codex_batch_fn=run_codex_batch_fn,
    )
    batch_positions = {batch_idx: pos + 1 for pos, batch_idx in enumerate(selected_indexes)}
    summary_created_at = datetime.now(UTC).isoformat(timespec="seconds")
    stall_warned_batches: set[int] = set()
    batch_status = build_initial_batch_status(
        selected_indexes=selected_indexes,
        batch_positions=batch_positions,
        prompt_files=prompt_files,
        output_files=output_files,
        log_files=log_files,
    )
    if run_parallel:
        print(
            colorize_fn(
                "  Parallel runner config: "
                f"max-workers={min(total_batches, max_parallel_batches)}, "
                f"heartbeat={heartbeat_seconds:.1f}s",
                "dim",
            )
        )
    report_progress = build_progress_reporter(
        batch_positions=batch_positions,
        batch_status=batch_status,
        stall_warned_batches=stall_warned_batches,
        total_batches=total_batches,
        stall_warning_seconds=stall_warning_seconds,
        prompt_files=prompt_files,
        output_files=output_files,
        log_files=log_files,
        append_run_log=append_run_log,
        colorize_fn=colorize_fn,
    )
    record_issue = partial(record_execution_issue, append_run_log)
    write_run_summary = build_run_summary_writer(
        run_dir=run_dir,
        summary_created_at=summary_created_at,
        stamp=stamp,
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
        logs_dir=logs_dir,
        run_log_path=run_log_path,
        batch_status=batch_status,
        safe_write_text_fn=safe_write_text_fn,
        colorize_fn=colorize_fn,
        append_run_log=append_run_log,
    )
    try:
        execution_failures = execute_batches_fn(
            tasks=tasks,
            options=BatchExecutionOptions(
                run_parallel=run_parallel,
                max_parallel_workers=max_parallel_batches,
                heartbeat_seconds=heartbeat_seconds,
            ),
            progress_fn=report_progress,
            error_log_fn=record_issue,
        )
    except KeyboardInterrupt:
        mark_interrupted_batches(
            selected_indexes=selected_indexes,
            batch_status=batch_status,
            batch_positions=batch_positions,
        )
        write_run_summary(
            successful_batches=[],
            failed_batches=[],
            interrupted=True,
            interruption_reason="keyboard_interrupt",
        )
        append_run_log("run-interrupted reason=keyboard_interrupt")
        raise SystemExit(130) from None
    batch_results, successful_indexes, failures, failure_set = collect_and_reconcile_results(
        collect_batch_results_fn=collect_batch_results_fn,
        selected_indexes=selected_indexes,
        execution_failures=execution_failures,
        output_files=output_files,
        packet=packet,
        batch_positions=batch_positions,
        batch_status=batch_status,
    )
    write_run_summary(
        successful_batches=[idx + 1 for idx in successful_indexes],
        failed_batches=[idx + 1 for idx in sorted(failure_set)],
    )
    if failures and (not allow_partial or not batch_results):
        append_run_log(
            f"run-finished failures={[idx + 1 for idx in sorted(failure_set)]} mode=exit"
        )
        print_failures_and_raise_fn(
            failures=failures,
            packet_path=immutable_packet_path,
            logs_dir=logs_dir,
            colorize_fn=colorize_fn,
        )
    elif failures:
        print(
            colorize_fn(
                "  Partial completion enabled: importing successful batches and keeping failed batches open.",
                "yellow",
            )
        )
        print_failures_fn(
            failures=failures,
            packet_path=immutable_packet_path,
            logs_dir=logs_dir,
            colorize_fn=colorize_fn,
        )
        append_run_log(
            "run-partial "
            f"successful={[idx + 1 for idx in successful_indexes]} "
            f"failed={[idx + 1 for idx in sorted(failure_set)]}"
        )
    merged_path, missing_after_import = merge_and_write_results(
        merge_batch_results_fn=merge_batch_results_fn,
        build_import_provenance_fn=build_import_provenance_fn,
        batch_results=batch_results,
        batches=batches,
        successful_indexes=successful_indexes,
        packet=packet,
        packet_dimensions=packet_dimensions,
        scored_dimensions=scored_dimensions,
        scan_path=scan_path,
        runner=runner,
        prompt_packet_path=prompt_packet_path,
        stamp=stamp,
        run_dir=run_dir,
        safe_write_text_fn=safe_write_text_fn,
        colorize_fn=colorize_fn,
    )
    enforce_import_coverage(
        missing_after_import=missing_after_import,
        packet_dimensions=packet_dimensions,
        allow_partial=allow_partial,
        scan_path=scan_path,
        colorize_fn=colorize_fn,
    )
    import_and_finalize(
        do_import_fn=do_import_fn,
        run_followup_scan_fn=run_followup_scan_fn,
        merged_path=merged_path,
        state=state,
        lang=lang,
        state_file=state_file,
        config=config,
        allow_partial=allow_partial,
        successful_indexes=successful_indexes,
        failure_set=failure_set,
        append_run_log=append_run_log,
        args=args,
    )
__all__ = ["do_run_batches"]
