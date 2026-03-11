"""Direct coverage tests for app.commands.runner helper modules."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import desloppify.app.commands.runner.codex_batch as codex_batch_mod
import desloppify.app.commands.runner.run_logs as run_logs_mod


def test_codex_batch_command_uses_sanitized_reasoning_effort(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DESLOPPIFY_CODEX_REASONING_EFFORT", "HIGH")

    command = codex_batch_mod.codex_batch_command(
        prompt="review prompt",
        repo_root=tmp_path,
        output_file=tmp_path / "out.json",
    )

    # On Windows with .cmd wrappers, prefix may be ["cmd", "/c", "...codex.cmd"]
    assert any(c.endswith("codex") or "codex" in c for c in command[:3])
    assert "exec" in command
    assert "--ephemeral" in command
    assert f'model_reasoning_effort="high"' in command
    assert str(tmp_path) in command

    monkeypatch.setenv("DESLOPPIFY_CODEX_REASONING_EFFORT", "invalid")
    command = codex_batch_mod.codex_batch_command(
        prompt="review prompt",
        repo_root=tmp_path,
        output_file=tmp_path / "out.json",
    )
    assert f'model_reasoning_effort="low"' in command


def test_run_codex_batch_retries_timeout_or_stall_until_success(monkeypatch, tmp_path: Path) -> None:
    attempts: list[int] = []
    sleeps: list[float] = []
    log_file = tmp_path / "batch.log"

    monkeypatch.setattr(
        codex_batch_mod,
        "resolve_retry_config",
        lambda _deps: SimpleNamespace(
            max_attempts=2,
            use_popen=False,
            live_log_interval=0.1,
            stall_seconds=5,
            retry_backoff_seconds=0.25,
        ),
    )

    def fake_run_batch_attempt(**kwargs):
        attempts.append(kwargs["attempt"])
        return (
            f"ATTEMPT {kwargs['attempt']}",
            SimpleNamespace(stdout_text="stdout", stderr_text="stderr", exit_code=1, ok=False),
        )

    monkeypatch.setattr(codex_batch_mod, "run_batch_attempt", fake_run_batch_attempt)
    monkeypatch.setattr(codex_batch_mod, "handle_early_attempt_return", lambda _result: None)
    monkeypatch.setattr(
        codex_batch_mod,
        "handle_timeout_or_stall",
        lambda **kwargs: 7 if kwargs["header"] == "ATTEMPT 1" else 0,
    )
    monkeypatch.setattr(codex_batch_mod, "handle_successful_attempt", lambda **_kwargs: None)
    monkeypatch.setattr(codex_batch_mod, "handle_failed_attempt", lambda **_kwargs: 1)

    code = codex_batch_mod.run_codex_batch(
        prompt="prompt",
        repo_root=tmp_path,
        output_file=tmp_path / "out.json",
        log_file=log_file,
        deps=SimpleNamespace(
            sleep_fn=sleeps.append,
            safe_write_text_fn=lambda path, text: path.write_text(text, encoding="utf-8"),
        ),
        codex_batch_command_fn=lambda **_kwargs: ["codex", "exec"],
    )

    assert code == 0
    assert attempts == [1, 2]
    assert sleeps == [0.25]


def test_run_followup_scan_handles_force_bypass_timeout_and_oserror(
    capsys,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def timeout_run(cmd, *, cwd, timeout):
        calls.append(cmd)
        raise TimeoutError

    timeout_code = codex_batch_mod.run_followup_scan(
        lang_name="python",
        scan_path="src",
        deps=SimpleNamespace(
            python_executable="python",
            project_root=tmp_path,
            timeout_seconds=10,
            subprocess_run=timeout_run,
            timeout_error=TimeoutError,
            colorize_fn=lambda text, _style: text,
        ),
        force_queue_bypass=True,
    )
    assert timeout_code == 124
    assert "--force-rescan" in calls[0]
    assert "--attest" in calls[0]

    oserror_code = codex_batch_mod.run_followup_scan(
        lang_name="python",
        scan_path="src",
        deps=SimpleNamespace(
            python_executable="python",
            project_root=tmp_path,
            timeout_seconds=10,
            subprocess_run=lambda *_a, **_k: (_ for _ in ()).throw(OSError("boom")),
            timeout_error=TimeoutError,
            colorize_fn=lambda text, _style: text,
        ),
    )
    assert oserror_code == 1
    out = capsys.readouterr()
    assert "Follow-up scan queue bypass enabled" in out.out
    assert "Follow-up scan timed out after 10s." in out.err
    assert "Follow-up scan failed: boom" in out.err


def test_make_run_log_writer_appends_timestamped_lines_and_ignores_oserror(
    monkeypatch,
    tmp_path: Path,
) -> None:
    run_log_path = tmp_path / "run.log"
    writer = run_logs_mod.make_run_log_writer(run_log_path)
    writer("started")
    text = run_log_path.read_text(encoding="utf-8")
    assert "started" in text
    assert text.endswith(" started\n")

    writer = run_logs_mod.make_run_log_writer(tmp_path / "missing" / "run.log")

    def fail_open(*_args, **_kwargs):
        raise OSError("nope")

    monkeypatch.setattr(Path, "open", fail_open)
    writer("ignored")
