"""Direct tests for batch execution summary writer helpers."""

from __future__ import annotations

from pathlib import Path

import desloppify.app.commands.review.batch.execution_summary as summary_mod
from desloppify.app.commands.review.batches_runtime import BatchRunSummaryConfig


def test_build_run_summary_writer_binds_summary_metadata(tmp_path: Path, monkeypatch) -> None:
    captured: dict = {}

    def _write_run_summary_impl(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(summary_mod, "_write_run_summary_impl", _write_run_summary_impl)
    summary_config = BatchRunSummaryConfig(
        created_at="2026-03-09T12:00:00+00:00",
        run_stamp="abc123",
        runner="codex",
        run_parallel=True,
        selected_indexes=[0, 2],
        allow_partial=True,
        max_parallel_batches=3,
        batch_timeout_seconds=120,
        batch_max_retries=1,
        batch_retry_backoff_seconds=2.0,
        heartbeat_seconds=1.0,
        stall_warning_seconds=30,
        stall_kill_seconds=90,
        immutable_packet_path=tmp_path / "packet.json",
        prompt_packet_path=tmp_path / "prompt.json",
        run_dir=tmp_path / "run",
        logs_dir=tmp_path / "logs",
        run_log_path=tmp_path / "run.log",
    )

    writer = summary_mod.build_run_summary_writer(
        run_dir=tmp_path / "run",
        summary_config=summary_config,
        batch_status={"1": {"status": "running"}},
        safe_write_text_fn=lambda *_a, **_k: None,
        colorize_fn=lambda text, _tone=None: text,
        append_run_log=lambda _line: None,
    )

    writer(successful_batches=[1], failed_batches=[], interrupted=False)

    assert captured["summary_path"] == (tmp_path / "run" / "run_summary.json")
    assert captured["summary_config"].run_stamp == "abc123"
    assert captured["summary_config"].runner == "codex"
    assert captured["batch_status"] == {"1": {"status": "running"}}
