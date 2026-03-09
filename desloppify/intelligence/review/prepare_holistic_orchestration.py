"""Orchestration helpers for holistic review payload preparation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from desloppify.intelligence.review._context.models import HolisticContext
from desloppify.intelligence.review._prepare.helpers import HOLISTIC_WORKFLOW

from .prepare_holistic_payload_parts import (
    _attach_issue_history_context,
    _build_selected_prompts,
)
from .prepare_holistic_scope import (
    collect_allowed_review_files,
    file_in_allowed_scope,
    filter_batches_to_file_scope,
)


def _resolve_review_files(
    path: Path,
    lang: object,
    options: object,
) -> tuple[list[str], set[str]]:
    """Resolve the full file list and the allowed-review-file set."""
    all_files = (
        options.files
        if options.files is not None
        else (lang.file_finder(path) if lang.file_finder else [])
    )
    allowed = collect_allowed_review_files(all_files, lang, base_path=path)
    return all_files, allowed


def _build_review_contexts(
    path: Path,
    lang: object,
    state: dict,
    all_files: list[str],
    *,
    is_file_cache_enabled_fn,
    enable_file_cache_fn,
    disable_file_cache_fn,
    build_holistic_context_fn,
    build_review_context_fn,
) -> tuple[HolisticContext, object]:
    """Build holistic and review contexts, managing the file cache lifecycle."""
    already_cached = is_file_cache_enabled_fn()
    if not already_cached:
        enable_file_cache_fn()
    try:
        context = HolisticContext.from_raw(
            build_holistic_context_fn(path, lang, state, files=all_files)
        )
        review_ctx = build_review_context_fn(path, lang, state, files=all_files)
    finally:
        if not already_cached:
            disable_file_cache_fn()
    return context, review_ctx


@dataclass
class _DimensionContext:
    """Resolved dimension configuration for holistic review."""

    dims: list[str]
    holistic_prompts: dict[str, Any]
    per_file_prompts: dict[str, Any]
    system_prompt: str
    lang_guide: str
    invalid_requested: list[str]
    invalid_default: list[str]


def _resolve_dimension_context(
    lang_name: str,
    options: object,
    *,
    load_dimensions_for_lang_fn,
    resolve_dimensions_fn,
    get_lang_guidance_fn,
) -> _DimensionContext:
    """Load, resolve, and validate dimensions for the review."""
    default_dims, holistic_prompts, system_prompt = load_dimensions_for_lang_fn(lang_name)
    _, per_file_prompts, _ = load_dimensions_for_lang_fn(lang_name)
    dims = resolve_dimensions_fn(
        cli_dimensions=options.dimensions,
        default_dimensions=default_dims,
    )
    lang_guide = get_lang_guidance_fn(lang_name)
    valid_dims = set(holistic_prompts) | set(per_file_prompts)
    invalid_requested = [
        dim for dim in (options.dimensions or []) if dim not in valid_dims
    ]
    invalid_default = [dim for dim in default_dims if dim not in valid_dims]
    return _DimensionContext(
        dims=dims,
        holistic_prompts=holistic_prompts,
        per_file_prompts=per_file_prompts,
        system_prompt=system_prompt,
        lang_guide=lang_guide,
        invalid_requested=invalid_requested,
        invalid_default=invalid_default,
    )


def _append_concerns_batch(
    batches: list[dict[str, Any]],
    state: dict,
    dims: list[str],
    allowed_review_files: set[str],
    max_files_per_batch: int,
    *,
    batch_concerns_fn,
    log_best_effort_failure_fn,
    log: object,
) -> None:
    """Generate concern signals and append as a batch (best-effort)."""
    try:
        from desloppify.engine._concerns.generators import generate_concerns

        concerns = generate_concerns(state)
        concerns = [
            concern
            for concern in concerns
            if file_in_allowed_scope(getattr(concern, "file", ""), allowed_review_files)
        ]
        concerns_batch = batch_concerns_fn(
            concerns,
            max_files=max_files_per_batch,
            active_dimensions=dims,
        )
        if concerns_batch:
            concern_dim = concerns_batch["dimensions"][0]
            merged = False
            for existing in batches:
                if existing.get("dimensions") == [concern_dim]:
                    existing_files = set(existing.get("files_to_read", []))
                    for filepath in concerns_batch.get("files_to_read", []):
                        if filepath not in existing_files:
                            existing["files_to_read"].append(filepath)
                            existing_files.add(filepath)
                    existing["concern_signals"] = concerns_batch.get("concern_signals", [])
                    existing["concern_signal_count"] = concerns_batch.get("concern_signal_count", 0)
                    merged = True
                    break
            if not merged:
                batches.append(concerns_batch)
    except (ImportError, AttributeError, TypeError, ValueError) as exc:
        log_best_effort_failure_fn(log, "generate review concern batch", exc)


def prepare_holistic_review_payload(
    path: Path,
    lang: object,
    state: dict,
    options,
    *,
    is_file_cache_enabled_fn,
    enable_file_cache_fn,
    disable_file_cache_fn,
    build_holistic_context_fn,
    build_review_context_fn,
    load_dimensions_for_lang_fn,
    resolve_dimensions_fn,
    get_lang_guidance_fn,
    build_investigation_batches_fn,
    batch_concerns_fn,
    filter_batches_to_dimensions_fn,
    append_full_sweep_batch_fn,
    serialize_context_fn,
    log_best_effort_failure_fn,
    logger,
) -> dict[str, object]:
    """Prepare holistic review payload with injected dependencies for patchability."""
    all_files, allowed_review_files = _resolve_review_files(path, lang, options)

    context, review_ctx = _build_review_contexts(
        path,
        lang,
        state,
        all_files,
        is_file_cache_enabled_fn=is_file_cache_enabled_fn,
        enable_file_cache_fn=enable_file_cache_fn,
        disable_file_cache_fn=disable_file_cache_fn,
        build_holistic_context_fn=build_holistic_context_fn,
        build_review_context_fn=build_review_context_fn,
    )

    dim_ctx = _resolve_dimension_context(
        lang.name,
        options,
        load_dimensions_for_lang_fn=load_dimensions_for_lang_fn,
        resolve_dimensions_fn=resolve_dimensions_fn,
        get_lang_guidance_fn=get_lang_guidance_fn,
    )

    batches = build_investigation_batches_fn(
        context,
        lang,
        repo_root=path,
        max_files_per_batch=options.max_files_per_batch,
    )

    _append_concerns_batch(
        batches,
        state,
        dim_ctx.dims,
        allowed_review_files,
        options.max_files_per_batch,
        batch_concerns_fn=batch_concerns_fn,
        log_best_effort_failure_fn=log_best_effort_failure_fn,
        log=logger,
    )

    batches = filter_batches_to_dimensions_fn(
        batches,
        dim_ctx.dims,
        fallback_max_files=options.max_files_per_batch,
    )
    include_full_sweep = bool(options.include_full_sweep)
    if options.dimensions:
        include_full_sweep = False
    if include_full_sweep:
        append_full_sweep_batch_fn(
            batches=batches,
            dims=dim_ctx.dims,
            all_files=all_files,
            lang=lang,
            max_files=options.max_files_per_batch,
        )
    batches = filter_batches_to_file_scope(
        batches,
        allowed_files=allowed_review_files,
    )

    selected_prompts = _build_selected_prompts(
        dim_ctx.dims,
        dim_ctx.holistic_prompts,
        dim_ctx.per_file_prompts,
    )

    payload: dict[str, Any] = {
        "command": "review",
        "mode": "holistic",
        "language": lang.name,
        "dimensions": dim_ctx.dims,
        "dimension_prompts": selected_prompts,
        "lang_guidance": dim_ctx.lang_guide,
        "holistic_context": context.to_dict(),
        "review_context": serialize_context_fn(review_ctx),
        "system_prompt": dim_ctx.system_prompt,
        "total_files": context.codebase_stats.get("total_files", 0),
        "workflow": HOLISTIC_WORKFLOW,
        "invalid_dimensions": {
            "requested": dim_ctx.invalid_requested,
            "default": dim_ctx.invalid_default,
        },
    }

    batches = _attach_issue_history_context(
        payload,
        batches,
        state,
        options,
        allowed_review_files,
    )

    payload["investigation_batches"] = batches
    return payload


__all__ = ["prepare_holistic_review_payload"]
