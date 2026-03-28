"""Tests for review registry, prompts, hashing, and review CLI options."""

from __future__ import annotations

import pytest

from desloppify.cli import create_parser
from desloppify.base.registry import DETECTORS, display_order
from desloppify.intelligence.review import (
    DIMENSION_PROMPTS,
    REVIEW_SYSTEM_PROMPT,
)
from desloppify.intelligence.review import (
    DIMENSIONS as REVIEW_DIMENSIONS,
)
from desloppify.intelligence.review import hash_file

# ── Registry tests ────────────────────────────────────────────────


class TestRegistry:
    def test_review_in_registry(self):
        assert "review" in DETECTORS
        meta = DETECTORS["review"]
        assert meta.dimension == "Test health"
        assert meta.action_type == "refactor"

    def test_review_in_display_order(self):
        assert "review" in display_order()

    def test_detector_registry_mapping_is_read_only(self):
        with pytest.raises(TypeError):
            DETECTORS["_tmp"] = DETECTORS["review"]  # type: ignore[index]


# ── Dimension prompts tests ───────────────────────────────────────


class TestDimensionPrompts:
    def test_all_dimensions_have_prompts(self):
        for dim in REVIEW_DIMENSIONS:
            assert dim in DIMENSION_PROMPTS
            prompt = DIMENSION_PROMPTS[dim]
            assert "description" in prompt
            assert "look_for" in prompt
            assert "skip" in prompt

    def test_system_prompt_not_empty(self):
        assert len(REVIEW_SYSTEM_PROMPT) > 100


# ── Hash tests ────────────────────────────────────────────────────


class TestHashFile:
    def test_hash_consistency(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h1 = hash_file(str(f))
        h2 = hash_file(str(f))
        assert h1 == h2
        assert len(h1) == 16

    def test_hash_changes_with_content(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        h1 = hash_file(str(f))
        f.write_text("world")
        h2 = hash_file(str(f))
        assert h1 != h2

    def test_hash_missing_file(self):
        assert hash_file("/nonexistent/file.txt") == ""


# ── CLI tests ─────────────────────────────────────────────────────


class TestCLI:
    def test_review_parser_exists(self):
        parser = create_parser()
        # Should parse without error
        args = parser.parse_args(["review", "--prepare"])
        assert args.command == "review"
        assert args.prepare is True

    def test_review_import_flag(self):
        parser = create_parser()
        args = parser.parse_args(["review", "--import", "issues.json"])
        assert args.command == "review"
        assert args.import_file == "issues.json"

    def test_review_allow_partial_flag(self):
        parser = create_parser()
        args = parser.parse_args(["review", "--import", "issues.json", "--allow-partial"])
        assert args.allow_partial is True

    def test_review_max_age_flag_rejected(self):
        parser = create_parser()
        try:
            parser.parse_args(["review", "--max-age", "60"])
            raise AssertionError("Expected SystemExit for removed --max-age")
        except SystemExit as exc:
            assert exc.code == 2

    def test_review_max_files_flag_rejected(self):
        parser = create_parser()
        try:
            parser.parse_args(["review", "--max-files", "25"])
            raise AssertionError("Expected SystemExit for removed --max-files")
        except SystemExit as exc:
            assert exc.code == 2

    def test_review_refresh_flag_rejected(self):
        parser = create_parser()
        try:
            parser.parse_args(["review", "--refresh"])
            raise AssertionError("Expected SystemExit for removed --refresh")
        except SystemExit as exc:
            assert exc.code == 2

    def test_review_dimensions_flag(self):
        parser = create_parser()
        args = parser.parse_args(
            ["review", "--dimensions", "naming_quality,comment_quality"]
        )
        assert args.dimensions == "naming_quality,comment_quality"

    def test_review_run_batches_flags(self):
        parser = create_parser()
        args = parser.parse_args(
            [
                "review",
                "--run-batches",
                "--runner",
                "codex",
                "--parallel",
                "--max-parallel-batches",
                "3",
                "--batch-timeout-seconds",
                "90",
                "--batch-max-retries",
                "2",
                "--batch-retry-backoff-seconds",
                "1.5",
                "--batch-heartbeat-seconds",
                "2.5",
                "--batch-stall-warning-seconds",
                "45",
                "--batch-stall-kill-seconds",
                "75",
                "--run-log-file",
                ".desloppify/subagents/runs/custom.log",
                "--dry-run",
                "--only-batches",
                "1,3",
            ]
        )
        assert args.run_batches is True
        assert args.runner == "codex"
        assert args.parallel is True
        assert args.max_parallel_batches == 3
        assert args.batch_timeout_seconds == 90
        assert args.batch_max_retries == 2
        assert args.batch_retry_backoff_seconds == 1.5
        assert args.batch_heartbeat_seconds == 2.5
        assert args.batch_stall_warning_seconds == 45
        assert args.batch_stall_kill_seconds == 75
        assert args.run_log_file == ".desloppify/subagents/runs/custom.log"
        assert args.dry_run is True
        assert args.only_batches == "1,3"


# ── New dimension tests ──────────────────────────────────────────

