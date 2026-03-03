"""Shared scan workflow phases used by the scan command facade."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from desloppify.languages._framework.runtime import LangRun

from desloppify import state as state_mod
from desloppify.app.commands.helpers.lang import resolve_lang, resolve_lang_settings
from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.app.commands.helpers.runtime_options import resolve_lang_runtime_options
from desloppify.app.commands.helpers.score import target_strict_score_from_config
from desloppify.app.commands.scan.scan_coverage import (
    coerce_int as _coerce_int,
    persist_scan_coverage as _persist_scan_coverage,
    seed_runtime_coverage_warnings as _seed_runtime_coverage_warnings,
)
from desloppify.app.commands.scan.scan_helpers import (
    _audit_excluded_dirs,
    _collect_codebase_metrics,
    _effective_include_slow,
    _resolve_scan_profile,
    _warn_explicit_lang_with_no_files,
)
from desloppify.app.commands.scan.scan_wontfix import (
    augment_with_stale_wontfix_issues as _augment_stale_wontfix_impl,
)
from desloppify.core.text_api import PROJECT_ROOT
from desloppify.engine import work_queue as issues_mod
from desloppify.engine import planning as plan_mod
from desloppify.engine.planning.scan import PlanScanOptions
from desloppify.core.file_paths import rel
from desloppify.core.source_discovery import (
    disable_file_cache,
    enable_file_cache,
    get_exclusions,
)
from desloppify.intelligence.review.dimensions.metadata import (
    resettable_default_dimensions,
)
from desloppify.languages._framework.treesitter import (
    disable_parse_cache,
    enable_parse_cache,
)
from desloppify.languages._framework.base.types import DetectorCoverageRecord
from desloppify.languages._framework.runtime import LangRunOverrides, make_lang_run
from desloppify.core.config import save_config as _save_config
from desloppify.core.output_api import colorize

_WONTFIX_DECAY_SCANS_DEFAULT = 20


class ScanStateContractError(ValueError):
    """Raised when persisted scan state violates required runtime contracts."""


def _clear_needs_rescan_flag(config: dict[str, object]) -> None:
    """Best-effort clear for config.needs_rescan after a successful scan merge."""
    if not config.get("needs_rescan"):
        return
    try:
        config["needs_rescan"] = False
        _save_config(config)
    except OSError as exc:
        _ = exc
        config["needs_rescan"] = True


def _reconcile_plan_post_scan(runtime: "ScanRuntime") -> None:
    """Reconcile plan queue metadata and stale subjective review dimensions."""
    from desloppify.app.commands.scan.scan_plan_reconcile import reconcile_plan_post_scan
    reconcile_plan_post_scan(runtime)


def _state_subjective_assessments(
    state: state_mod.StateModel,
) -> dict[str, object]:
    """Return normalized subjective assessment store from state."""
    assessments = state.get("subjective_assessments")
    if isinstance(assessments, dict):
        return assessments
    raise ScanStateContractError(
        "state.subjective_assessments must be an object; rerun with a valid state file"
    )


def _state_lang_capabilities(
    state: state_mod.StateModel,
) -> dict[str, dict[str, object]]:
    """Return normalized language capability map from state."""
    capabilities = state.get("lang_capabilities")
    if capabilities is None:
        normalized: dict[str, dict[str, object]] = {}
        state["lang_capabilities"] = normalized
        return normalized
    if isinstance(capabilities, dict):
        return capabilities
    raise ScanStateContractError(
        "state.lang_capabilities must be an object when present"
    )


def _state_issues(state: state_mod.StateModel) -> dict[str, dict[str, Any]]:
    """Return normalized issue map from state."""
    issues = state.get("issues")
    if isinstance(issues, dict):
        return issues
    raise ScanStateContractError(
        "state.issues must be an object; state file appears corrupted"
    )


def _subjective_reset_dimensions(*, lang_name: str | None = None) -> tuple[str, ...]:
    """Resolve subjective dimensions that should reset on scan baseline reset."""
    return resettable_default_dimensions(lang_name=lang_name)


@dataclass
class ScanRuntime:
    """Resolved runtime context for a single scan invocation."""

    args: argparse.Namespace
    state_path: Path | None
    state: state_mod.StateModel
    path: Path
    config: dict[str, object]
    lang: LangRun | None
    lang_label: str
    profile: str
    effective_include_slow: bool
    zone_overrides: dict[str, object] | None
    reset_subjective_count: int = 0
    expired_manual_override_count: int = 0
    coverage_warnings: list[DetectorCoverageRecord] = field(default_factory=list)


@dataclass
class ScanMergeResult:
    """State merge outputs and previous score snapshots."""

    diff: dict[str, object]
    prev_overall: float | None
    prev_objective: float | None
    prev_strict: float | None
    prev_verified: float | None
    prev_dim_scores: dict[str, object]


@dataclass
class ScanNoiseSnapshot:
    """Noise budget settings and hidden issue counts for this scan."""

    noise_budget: int
    global_noise_budget: int
    budget_warning: str | None
    hidden_by_detector: dict[str, int]
    hidden_total: int


def _configure_lang_runtime(
    args: argparse.Namespace,
    config: dict[str, object],
    state: state_mod.StateModel,
    lang: LangRun | None,
) -> LangRun | None:
    """Populate runtime context and threshold overrides for a selected language."""
    if not lang:
        return None

    lang_options = resolve_lang_runtime_options(args, lang)
    lang_settings = resolve_lang_settings(config, lang)
    runtime_lang = make_lang_run(
        lang,
        overrides=LangRunOverrides(
            review_cache=state.get("review_cache", {}),
            review_max_age_days=config.get("review_max_age_days", 30),
            runtime_settings=lang_settings,
            runtime_options=lang_options,
            large_threshold_override=config.get("large_files_threshold", 0),
            props_threshold_override=config.get("props_threshold", 0),
        ),
    )

    lang_capabilities = _state_lang_capabilities(state)
    lang_capabilities[runtime_lang.name] = {
        "fixers": sorted(runtime_lang.fixers.keys()),
        "typecheck_cmd": runtime_lang.typecheck_cmd,
    }
    return runtime_lang


def _reset_subjective_assessments_for_scan_reset(
    state: state_mod.StateModel,
    *,
    lang_name: str | None = None,
) -> int:
    """Reset known subjective dimensions to 0 so the next scan starts fresh."""
    assessments = _state_subjective_assessments(state)

    reset_keys = {
        key.strip()
        for key in assessments
        if isinstance(key, str) and key.strip()
    }
    reset_keys.update(_subjective_reset_dimensions(lang_name=lang_name))

    now = state_mod.utc_now()
    for key in sorted(reset_keys):
        payload = assessments.get(key)
        if isinstance(payload, dict):
            payload["score"] = 0.0
            payload["source"] = "scan_reset_subjective"
            payload["assessed_at"] = now
            payload["reset_by"] = "scan_reset_subjective"
            payload["placeholder"] = True
            payload.pop("integrity_penalty", None)
            payload.pop("components", None)
            payload.pop("component_scores", None)
            continue
        assessments[key] = {
            "score": 0.0,
            "source": "scan_reset_subjective",
            "assessed_at": now,
            "reset_by": "scan_reset_subjective",
            "placeholder": True,
        }
    return len(reset_keys)


def _expire_provisional_manual_override_assessments(
    state: state_mod.StateModel,
) -> int:
    """Expire provisional manual-override assessments at scan start."""
    assessments = _state_subjective_assessments(state)

    now = state_mod.utc_now()
    expired = 0
    for payload in assessments.values():
        if not isinstance(payload, dict):
            continue
        if payload.get("provisional_override") is not True:
            continue
        payload["score"] = 0.0
        payload["source"] = "manual_override_expired"
        payload["assessed_at"] = now
        payload["reset_by"] = "manual_override_expired"
        payload["placeholder"] = True
        payload.pop("provisional_override", None)
        payload.pop("provisional_until_scan", None)
        payload.pop("integrity_penalty", None)
        payload.pop("components", None)
        payload.pop("component_scores", None)
        expired += 1
    return expired


def prepare_scan_runtime(args) -> ScanRuntime:
    """Resolve state/config/language and apply scan-time runtime settings."""
    runtime = command_runtime(args)
    state_file = runtime.state_path
    state = runtime.state if isinstance(runtime.state, dict) else {}
    state_mod.ensure_state_defaults(state)
    path = Path(args.path)
    config = runtime.config if isinstance(runtime.config, dict) else {}
    lang_config = resolve_lang(args)
    reset_subjective_count = 0
    expired_manual_override_count = _expire_provisional_manual_override_assessments(
        state
    )
    if getattr(args, "reset_subjective", False):
        reset_subjective_count = _reset_subjective_assessments_for_scan_reset(
            state,
            lang_name=getattr(lang_config, "name", None),
        )

    include_slow = not getattr(args, "skip_slow", False)
    profile = _resolve_scan_profile(getattr(args, "profile", None), lang_config)
    effective_include_slow = _effective_include_slow(include_slow, profile)

    lang = _configure_lang_runtime(args, config, state, lang_config)
    coverage_warnings = _seed_runtime_coverage_warnings(lang)
    zone_overrides_raw = config.get("zone_overrides")
    zone_overrides = zone_overrides_raw if isinstance(zone_overrides_raw, dict) else None

    return ScanRuntime(
        args=args,
        state_path=state_file,
        state=state,
        path=path,
        config=config,
        lang=lang,
        lang_label=f" ({lang.name})" if lang else "",
        profile=profile,
        effective_include_slow=effective_include_slow,
        zone_overrides=zone_overrides,
        reset_subjective_count=reset_subjective_count,
        expired_manual_override_count=expired_manual_override_count,
        coverage_warnings=coverage_warnings,
    )


def _augment_with_stale_exclusion_issues(
    issues: list[dict[str, Any]],
    runtime: ScanRuntime,
) -> list[dict[str, Any]]:
    """Append stale exclude issues when excluded dirs are unreferenced."""
    extra_exclusions = get_exclusions()
    if not (extra_exclusions and runtime.lang and runtime.lang.file_finder):
        return issues

    scanned_files = runtime.lang.file_finder(runtime.path)
    stale = _audit_excluded_dirs(
        extra_exclusions, scanned_files, PROJECT_ROOT
    )
    if not stale:
        return issues

    augmented = list(issues)
    augmented.extend(stale)
    for stale_issue in stale:
        print(colorize(f"  ℹ {stale_issue['summary']}", "dim"))
    return augmented


def _augment_with_stale_wontfix_issues(
    issues: list[dict[str, Any]],
    runtime: ScanRuntime,
    *,
    decay_scans: int,
) -> tuple[list[dict[str, Any]], int]:
    """Append re-triage issues for stale/worsening wontfix debt."""
    return _augment_stale_wontfix_impl(
        issues,
        state=runtime.state,
        scan_path=runtime.path,
        project_root=PROJECT_ROOT,
        decay_scans=decay_scans,
    )


def run_scan_generation(
    runtime: ScanRuntime,
) -> tuple[list[dict[str, Any]], dict[str, object], dict[str, object] | None]:
    """Run detector pipeline and return issues, potentials, and codebase metrics."""
    enable_file_cache()
    enable_parse_cache()
    try:
        issues, potentials = plan_mod.generate_issues(
            runtime.path,
            lang=runtime.lang,
            options=PlanScanOptions(
                include_slow=runtime.effective_include_slow,
                zone_overrides=runtime.zone_overrides,
                profile=runtime.profile,
            ),
        )
    finally:
        disable_parse_cache()
        disable_file_cache()

    codebase_metrics = _collect_codebase_metrics(runtime.lang, runtime.path)
    _warn_explicit_lang_with_no_files(
        runtime.args, runtime.lang, runtime.path, codebase_metrics
    )
    issues = _augment_with_stale_exclusion_issues(issues, runtime)
    decay_scans = _coerce_int(
        runtime.config.get("wontfix_decay_scans"),
        default=_WONTFIX_DECAY_SCANS_DEFAULT,
    )
    issues, monitored_wontfix = _augment_with_stale_wontfix_issues(
        issues,
        runtime,
        decay_scans=max(decay_scans, 0),
    )
    potentials["stale_wontfix"] = monitored_wontfix
    return issues, potentials, codebase_metrics


def merge_scan_results(
    runtime: ScanRuntime,
    issues: list[dict[str, Any]],
    potentials: dict[str, object],
    codebase_metrics: dict[str, object] | None,
) -> ScanMergeResult:
    """Merge issues into persistent state and return diff + previous score snapshot."""
    scan_path_rel = rel(str(runtime.path))
    prev_scan_path = runtime.state.get("scan_path")
    path_changed = prev_scan_path is not None and prev_scan_path != scan_path_rel

    if not path_changed:
        prev = state_mod.score_snapshot(runtime.state)
    else:
        prev = state_mod.ScoreSnapshot(None, None, None, None)
    prev_dim_scores = (
        runtime.state.get("dimension_scores", {}) if not path_changed else {}
    )

    if runtime.lang and runtime.lang.zone_map is not None:
        runtime.state["zone_distribution"] = runtime.lang.zone_map.counts()
    _persist_scan_coverage(runtime.state, runtime.lang)

    target_score = target_strict_score_from_config(runtime.config, fallback=95.0)

    diff = state_mod.merge_scan(
        runtime.state,
        issues,
        options=state_mod.MergeScanOptions(
            lang=runtime.lang.name if runtime.lang else None,
            scan_path=scan_path_rel,
            force_resolve=getattr(runtime.args, "force_resolve", False),
            exclude=get_exclusions(),
            potentials=potentials,
            codebase_metrics=codebase_metrics,
            include_slow=runtime.effective_include_slow,
            ignore=runtime.config.get("ignore", []),
            subjective_integrity_target=target_score,
        ),
    )

    issues_mod.expire_stale_holistic(
        runtime.state, runtime.config.get("holistic_max_age_days", 30)
    )
    state_mod.save_state(
        runtime.state,
        runtime.state_path,
        subjective_integrity_target=target_score,
    )

    _clear_needs_rescan_flag(runtime.config)
    _reconcile_plan_post_scan(runtime)

    return ScanMergeResult(
        diff=diff,
        prev_overall=prev.overall,
        prev_objective=prev.objective,
        prev_strict=prev.strict,
        prev_verified=prev.verified,
        prev_dim_scores=prev_dim_scores,
    )


def resolve_noise_snapshot(
    state: state_mod.StateModel,
    config: dict[str, object],
) -> ScanNoiseSnapshot:
    """Resolve noise budget settings and hidden issue counters."""
    noise_budget, global_noise_budget, budget_warning = (
        state_mod.resolve_issue_noise_settings(config)
    )
    issues_by_id = _state_issues(state)
    open_issues = [
        issue
        for issue in state_mod.path_scoped_issues(
            issues_by_id, state.get("scan_path")
        ).values()
        if issue.get("status") == "open"
    ]
    _, hidden_by_detector = state_mod.apply_issue_noise_budget(
        open_issues,
        budget=noise_budget,
        global_budget=global_noise_budget,
    )

    return ScanNoiseSnapshot(
        noise_budget=noise_budget,
        global_noise_budget=global_noise_budget,
        budget_warning=budget_warning,
        hidden_by_detector=hidden_by_detector,
        hidden_total=sum(hidden_by_detector.values()),
    )


def persist_reminder_history(
    runtime: ScanRuntime,
    narrative: dict[str, object],
) -> None:
    """Persist reminder history emitted by narrative computation."""
    if not (narrative and "reminder_history" in narrative):
        return

    runtime.state["reminder_history"] = narrative["reminder_history"]
    target_score = target_strict_score_from_config(runtime.config, fallback=95.0)
    state_mod.save_state(
        runtime.state,
        runtime.state_path,
        subjective_integrity_target=target_score,
    )


__all__ = [
    "ScanStateContractError",
    "ScanMergeResult",
    "ScanNoiseSnapshot",
    "ScanRuntime",
    "merge_scan_results",
    "persist_reminder_history",
    "prepare_scan_runtime",
    "resolve_noise_snapshot",
    "run_scan_generation",
]
