"""Shared holistic review packet construction and next-command helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from desloppify.base.coercions import coerce_positive_int
from desloppify.engine._state.schema import StateModel
import desloppify.intelligence.narrative.core as narrative_mod
from desloppify.intelligence.review.prepare import (
    HolisticReviewPrepareOptions,
    prepare_holistic_review,
)

from .. import runner_packets as runner_packets_mod
from ..helpers import parse_dimensions
from ..runtime_paths import (
    blind_packet_path,
    review_packet_dir,
    runtime_project_root,
)
from .policy import coerce_review_batch_file_limit, redacted_review_config


@dataclass(frozen=True)
class ReviewPacketContext:
    """Normalized review-packet CLI options shared across entrypoints."""

    path: Path
    dimensions: list[str] | None
    retrospective: bool
    retrospective_max_issues: int
    retrospective_max_batch_items: int


def resolve_review_packet_context(args: Any) -> ReviewPacketContext:
    """Parse shared packet options from CLI args."""
    dims = parse_dimensions(args)
    dimensions = list(dims) if dims else None
    retrospective = bool(getattr(args, "retrospective", False))
    retrospective_max_issues = coerce_positive_int(
        getattr(args, "retrospective_max_issues", None),
        default=30,
        minimum=1,
    )
    retrospective_max_batch_items = coerce_positive_int(
        getattr(args, "retrospective_max_batch_items", None),
        default=20,
        minimum=1,
    )
    return ReviewPacketContext(
        path=Path(getattr(args, "path", ".") or "."),
        dimensions=dimensions,
        retrospective=retrospective,
        retrospective_max_issues=retrospective_max_issues,
        retrospective_max_batch_items=retrospective_max_batch_items,
    )


def build_holistic_packet(
    *,
    state: StateModel,
    lang: Any,
    config: dict[str, Any],
    context: ReviewPacketContext,
    setup_lang_fn,
    prepare_holistic_review_fn=None,
) -> tuple[dict[str, Any], str]:
    """Build the canonical holistic review packet payload and lang name."""
    lang_run, found_files = setup_lang_fn(lang, context.path, config)
    lang_name = lang_run.name
    narrative = narrative_mod.compute_narrative(
        state,
        context=narrative_mod.NarrativeContext(lang=lang_name, command="review"),
    )
    prepare_fn = prepare_holistic_review_fn or prepare_holistic_review
    packet = prepare_fn(
        context.path,
        lang_run,
        state,
        options=HolisticReviewPrepareOptions(
            dimensions=context.dimensions,
            files=found_files or None,
            max_files_per_batch=coerce_review_batch_file_limit(config),
            include_issue_history=context.retrospective,
            issue_history_max_issues=context.retrospective_max_issues,
            issue_history_max_batch_items=context.retrospective_max_batch_items,
        ),
    )
    packet["narrative"] = narrative
    return packet, lang_name


def build_run_batches_next_command(context: ReviewPacketContext) -> str:
    """Return the canonical next command for local batch-based review."""
    parts: list[str] = [
        "desloppify",
        "review",
        "--run-batches",
        "--runner",
        "codex",
        "--parallel",
        "--scan-after-import",
    ]
    if context.dimensions:
        parts.extend(["--dimensions", ",".join(context.dimensions)])
    if context.retrospective:
        parts.extend(
            [
                "--retrospective",
                "--retrospective-max-issues",
                str(context.retrospective_max_issues),
                "--retrospective-max-batch-items",
                str(context.retrospective_max_batch_items),
            ]
        )
    return " ".join(parts)


def prepared_packet_contract(
    context: ReviewPacketContext,
    *,
    config: dict[str, Any] | None,
) -> dict[str, object]:
    """Build normalized invocation contract for prepared packet reuse."""
    redacted = redacted_review_config(config or {})
    payload = json.dumps(redacted, sort_keys=True, separators=(",", ":"))
    return {
        "path": str(context.path.resolve()),
        "dimensions": sorted(context.dimensions or []),
        "retrospective": context.retrospective,
        "retrospective_max_issues": context.retrospective_max_issues,
        "retrospective_max_batch_items": context.retrospective_max_batch_items,
        "config_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def build_external_submit_next_command(context: ReviewPacketContext) -> str:
    """Return the canonical next command for external-session submit."""
    parts: list[str] = [
        "desloppify",
        "review",
        "--external-submit",
        "--session-id",
        "<id>",
        "--import",
        "<file>",
    ]
    if context.retrospective:
        parts.extend(
            [
                "--retrospective",
                "--retrospective-max-issues",
                str(context.retrospective_max_issues),
                "--retrospective-max-batch-items",
                str(context.retrospective_max_batch_items),
            ]
        )
    return " ".join(parts)


def require_non_empty_packet(packet: dict[str, Any], *, path: Path) -> int:
    """Return packet total_files, raising ValueError when no reviewable files exist."""
    total = packet.get("total_files", 0)
    if isinstance(total, bool) or not isinstance(total, int):
        raise ValueError(
            f"invalid review packet shape for path '{path}': total_files must be an integer"
        )
    if total <= 0:
        raise ValueError(f"no files found at path '{path}'. Nothing to review.")
    return total


def build_review_packet_payload(
    *,
    state: StateModel,
    lang: Any,
    config: dict[str, Any],
    context: ReviewPacketContext,
    next_command: str,
    setup_lang_fn,
    prepare_holistic_review_fn=None,
) -> dict[str, Any]:
    """Build and validate a holistic review packet without persisting artifacts."""
    packet, _lang_name = build_holistic_packet(
        state=state,
        lang=lang,
        config=config,
        context=context,
        setup_lang_fn=setup_lang_fn,
        prepare_holistic_review_fn=prepare_holistic_review_fn,
    )
    packet["config"] = redacted_review_config(config)
    packet["next_command"] = next_command
    require_non_empty_packet(packet, path=context.path)
    return packet


def write_review_packet_snapshot(
    packet: dict[str, Any],
    *,
    stamp: str,
    project_root_override: Path | None = None,
    review_packet_dir_override: Path | None = None,
    blind_path_override: Path | None = None,
    safe_write_text_fn,
) -> tuple[Path, Path]:
    """Persist immutable + blind packet snapshots and return their paths."""
    runtime_root = runtime_project_root(project_root_override=project_root_override)
    blind_path = blind_path_override or blind_packet_path(
        project_root_override=runtime_root,
        stamp=stamp,
    )
    packet_dir = review_packet_dir(
        project_root_override=runtime_root,
        review_packet_dir_override=review_packet_dir_override,
    )
    return runner_packets_mod.write_packet_snapshot(
        packet,
        stamp=stamp,
        review_packet_dir=packet_dir,
        blind_path=blind_path,
        safe_write_text_fn=safe_write_text_fn,
    )


__all__ = [
    "ReviewPacketContext",
    "build_external_submit_next_command",
    "build_holistic_packet",
    "prepared_packet_contract",
    "build_review_packet_payload",
    "build_run_batches_next_command",
    "require_non_empty_packet",
    "resolve_review_packet_context",
    "write_review_packet_snapshot",
]
