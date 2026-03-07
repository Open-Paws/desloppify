"""Thin wrapper around review runner_process for triage stage execution."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from desloppify.app.commands.review._runner_process_types import CodexBatchRunnerDeps
from desloppify.app.commands.review.runner_process import (
    codex_batch_command,
    run_codex_batch,
)
from desloppify.base.discovery.file_paths import safe_write_text


def _output_file_has_text(output_file: Path) -> bool:
    """Return True when the output file exists and contains non-empty text."""
    if not output_file.exists():
        return False
    try:
        return len(output_file.read_text().strip()) > 0
    except OSError:
        return False


def run_triage_stage(
    *,
    prompt: str,
    repo_root: Path,
    output_file: Path,
    log_file: Path,
    timeout_seconds: int = 1800,
    validate_output_fn: Callable[[Path], bool] | None = None,
) -> int:
    """Execute a triage stage via codex subprocess. Returns exit code."""
    deps = CodexBatchRunnerDeps(
        timeout_seconds=timeout_seconds,
        subprocess_run=subprocess.run,
        timeout_error=subprocess.TimeoutExpired,
        safe_write_text_fn=safe_write_text,
        use_popen_runner=True,
        subprocess_popen=subprocess.Popen,
        live_log_interval_seconds=10.0,
        stall_after_output_seconds=120,
        max_retries=1,
        retry_backoff_seconds=5.0,
        sleep_fn=time.sleep,
        validate_output_fn=validate_output_fn,
    )
    return run_codex_batch(
        prompt=prompt,
        repo_root=repo_root,
        output_file=output_file,
        log_file=log_file,
        deps=deps,
    )


__all__ = ["run_triage_stage"]
