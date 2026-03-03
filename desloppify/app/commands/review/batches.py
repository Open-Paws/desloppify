"""Batch execution flow helpers for review command."""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from desloppify.core.exception_sets import CommandError
from .batches_runtime import (
    BatchRunSummaryConfig,
    build_batch_tasks,
    make_run_log_writer,
    resolve_run_log_path,
    write_run_summary as _write_run_summary_impl,
)
from .batches_scope import (
    collect_reviewed_files_from_batches,
    normalize_dimension_list,
    print_import_dimension_coverage_notice,
    print_preflight_dimension_scope_notice,
    print_review_quality,
    require_batches,
    scored_dimensions_for_lang,
    validate_runner,
)
from .runtime.policy import resolve_batch_run_policy


_build_batch_tasks = build_batch_tasks


def _record_execution_issue(append_run_log_fn, batch_index: int, exc: Exception) -> None:
    """Record one execute_batches callback/task failure in run.log."""
    if batch_index < 0:
        append_run_log_fn(f"execution-error heartbeat error={exc}")
        return
    append_run_log_fn(f"execution-error batch={batch_index + 1} error={exc}")



def do_run_batches(
    args,
    state,
    lang,
    state_file,
    *,
    config: dict | None,
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
    batches = require_batches(
        packet,
        colorize_fn=colorize_fn,
        suggested_prepare_cmd=suggested_prepare_cmd,
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

    append_run_log(
        "run-start "
        f"runner={runner} parallel={run_parallel} max_parallel={max_parallel_batches} "
        f"timeout={batch_timeout_seconds}s heartbeat={heartbeat_seconds:.1f}s "
        f"stall_warning={stall_warning_seconds}s stall_kill={stall_kill_seconds}s "
        f"retries={batch_max_retries} "
        f"retry_backoff={batch_retry_backoff_seconds:.1f}s upper_bound={worst_case_minutes}m "
        f"selected={[idx + 1 for idx in selected_indexes]}"
    )
    append_run_log(f"run-path {run_dir}")
    append_run_log(f"packet {immutable_packet_path}")
    append_run_log(f"blind-packet {prompt_packet_path}")
    print(colorize_fn(f"  Live run log: {run_log_path}", "dim"))

    if getattr(args, "dry_run", False):
        print(
            colorize_fn(
                "  Dry run only: prompts generated, runner execution skipped.", "yellow"
            )
        )
        print(colorize_fn(f"  Immutable packet: {immutable_packet_path}", "dim"))
        print(colorize_fn(f"  Blind packet: {prompt_packet_path}", "dim"))
        print(colorize_fn(f"  Prompts: {run_dir / 'prompts'}", "dim"))
        append_run_log("run-finished dry-run")
        return
    tasks = _build_batch_tasks(
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
    batch_status: dict[str, dict[str, object]] = {
        str(idx + 1): {
            "position": batch_positions.get(idx, 0),
            "status": "pending",
            "prompt_path": str(prompt_files[idx]),
            "result_path": str(output_files[idx]),
            "log_path": str(log_files[idx]),
        }
        for idx in selected_indexes
    }

    if run_parallel:
        print(
            colorize_fn(
                "  Parallel runner config: "
                f"max-workers={min(total_batches, max_parallel_batches)}, "
                f"heartbeat={heartbeat_seconds:.1f}s",
                "dim",
            )
        )

    def _report_progress(
        batch_index: int,
        event: str,
        code: int | None = None,
        **details,
    ) -> None:
        if event == "heartbeat":
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

    record_execution_issue = partial(_record_execution_issue, append_run_log)
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

    def write_run_summary(*, successful_batches, failed_batches, interrupted=False, interruption_reason=None):
        _write_run_summary_impl(
            summary_path=run_summary_path,
            summary_config=summary_config,
            batch_status=batch_status,
            successful_batches=successful_batches,
            failed_batches=failed_batches,
            safe_write_text_fn=safe_write_text_fn,
            colorize_fn=colorize_fn,
            append_run_log_fn=append_run_log,
            interrupted=interrupted,
            interruption_reason=interruption_reason,
        )

    try:
        execution_failures = execute_batches_fn(
            tasks=tasks,
            run_parallel=run_parallel,
            progress_fn=_report_progress,
            error_log_fn=record_execution_issue,
            max_parallel_workers=max_parallel_batches,
            heartbeat_seconds=heartbeat_seconds,
        )
    except KeyboardInterrupt:
        for idx in selected_indexes:
            key = str(idx + 1)
            state = batch_status.setdefault(
                key,
                {"position": batch_positions.get(idx, 0), "status": "pending"},
            )
            if state.get("status") in {"pending", "queued", "running"}:
                state["status"] = "interrupted"
        write_run_summary(
            successful_batches=[],
            failed_batches=[],
            interrupted=True,
            interruption_reason="keyboard_interrupt",
        )
        append_run_log("run-interrupted reason=keyboard_interrupt")
        raise SystemExit(130) from None

    allowed_dims = {
        str(dim) for dim in packet.get("dimensions", []) if isinstance(dim, str)
    }
    batch_results, failures = collect_batch_results_fn(
        selected_indexes=selected_indexes,
        failures=execution_failures,
        output_files=output_files,
        allowed_dims=allowed_dims,
    )

    execution_failure_set = set(execution_failures)
    failure_set = set(failures)
    successful_indexes = sorted(idx for idx in selected_indexes if idx not in failure_set)
    for idx in selected_indexes:
        key = str(idx + 1)
        state = batch_status.setdefault(
            key,
            {"position": batch_positions.get(idx, 0), "status": "pending"},
        )
        if idx not in failure_set:
            state["status"] = "succeeded"
            continue
        if idx in execution_failure_set:
            state["status"] = "failed"
            continue
        if not output_files[idx].exists():
            state["status"] = "missing_output"
            continue
        state["status"] = "parse_failed"

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

    merged = merge_batch_results_fn(batch_results)
    reviewed_files = collect_reviewed_files_from_batches(
        batches=batches,
        selected_indexes=successful_indexes,
    )
    full_sweep_included = any(
        str(batch.get("name", "")).strip().lower() == "full codebase sweep"
        for idx in successful_indexes
        if 0 <= idx < len(batches)
        for batch in [batches[idx]]
        if isinstance(batch, dict)
    )
    review_scope: dict[str, object] = {
        "reviewed_files_count": len(reviewed_files),
        "successful_batch_count": len(successful_indexes),
        "full_sweep_included": full_sweep_included,
    }
    total_files = packet.get("total_files")
    if isinstance(total_files, int) and not isinstance(total_files, bool) and total_files > 0:
        review_scope["total_files"] = total_files
    merged["review_scope"] = review_scope
    if reviewed_files:
        merged["reviewed_files"] = reviewed_files
        print(
            colorize_fn(
                f"  Reviewed files captured for cache refresh: {len(reviewed_files)}",
                "dim",
            )
        )
    merged["provenance"] = build_import_provenance_fn(
        runner=runner,
        blind_packet_path=prompt_packet_path,
        run_stamp=stamp,
        batch_indexes=successful_indexes,
    )
    merged_assessment_dims = normalize_dimension_list(
        list((merged.get("assessments") or {}).keys())
    )
    merged_issue_dims = normalize_dimension_list(
        [
            issue.get("dimension")
            for issue in (merged.get("issues") or [])
            if isinstance(issue, dict)
        ]
    )
    merged_imported_dims = normalize_dimension_list(
        merged_assessment_dims + merged_issue_dims
    )
    review_scope["imported_dimensions"] = merged_imported_dims
    missing_after_import = print_import_dimension_coverage_notice(
        assessed_dims=merged_assessment_dims,
        scored_dims=scored_dimensions,
        scan_path=scan_path,
        colorize_fn=colorize_fn,
    )
    merged["assessment_coverage"] = {
        "scored_dimensions": scored_dimensions,
        "selected_dimensions": packet_dimensions,
        "imported_dimensions": merged_assessment_dims,
        "missing_dimensions": missing_after_import,
    }
    merged_path = run_dir / "holistic_issues_merged.json"
    safe_write_text_fn(merged_path, json.dumps(merged, indent=2) + "\n")
    print(colorize_fn(f"\n  Merged outputs: {merged_path}", "bold"))
    print_review_quality(merged.get("review_quality", {}), colorize_fn=colorize_fn)

    try:
        do_import_fn(
            str(merged_path),
            state,
            lang,
            state_file,
            config=config,
            allow_partial=allow_partial,
            trusted_assessment_source=True,
            trusted_assessment_label="trusted internal run-batches import",
        )
    except SystemExit as exc:
        append_run_log(f"run-finished import-failed code={exc.code}")
        raise
    except Exception as exc:
        append_run_log(f"run-finished import-error error={exc}")
        raise
    append_run_log(
        "run-finished "
        f"successful={[idx + 1 for idx in successful_indexes]} "
        f"failed={[idx + 1 for idx in sorted(failure_set)]} imported={str(merged_path)}"
    )

    if getattr(args, "scan_after_import", False):
        followup_code = run_followup_scan_fn(
            lang_name=lang.name,
            scan_path=str(args.path),
        )
        if followup_code != 0:
            raise CommandError(
                f"Error: follow-up scan failed with exit code {followup_code}.",
                exit_code=followup_code,
            )


__all__ = ["do_run_batches"]
