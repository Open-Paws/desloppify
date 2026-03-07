"""Validation and guardrail helpers for triage stage workflow."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.app.commands.plan.triage_playbook import TRIAGE_CMD_ORGANIZE
from desloppify.base.output.terminal import colorize
from desloppify.engine.plan import (
    collect_triage_input,
    detect_recurring_patterns,
    extract_issue_citations,
    save_plan,
)
from desloppify.state import utc_now

from .confirmations import _MIN_ATTESTATION_LEN, _validate_attestation
from .display import show_plan_summary
from .helpers import manual_clusters_with_issues, observe_dimension_breakdown
from .stage_helpers import _unclustered_review_issues, _unenriched_clusters
from ._stage_rendering import _print_new_issues_since_last

_PATH_RE = re.compile(r'(?:src|supabase)/[\w./-]+\.\w+')
_EXT_SWAPS = {'.ts': '.tsx', '.tsx': '.ts', '.js': '.jsx', '.jsx': '.js'}
_VALID_EFFORTS = {"trivial", "small", "medium", "large"}


def _auto_confirm_observe_if_attested(
    *,
    plan: dict,
    stages: dict,
    attestation: str | None,
    triage_input,
) -> bool:
    if stages["observe"].get("confirmed_at"):
        return True
    if not attestation or len(attestation.strip()) < _MIN_ATTESTATION_LEN:
        print(colorize("  Cannot reflect: observe stage not confirmed.", "red"))
        print(colorize("  Run: desloppify plan triage --confirm observe", "dim"))
        print(colorize("  Or pass --attestation to auto-confirm observe inline.", "dim"))
        return False
    _by_dim, dim_names = observe_dimension_breakdown(triage_input)
    validation_err = _validate_attestation(
        attestation.strip(),
        "observe",
        dimensions=dim_names,
    )
    if validation_err:
        print(colorize(f"  {validation_err}", "red"))
        return False
    stages["observe"]["confirmed_at"] = utc_now()
    stages["observe"]["confirmed_text"] = attestation.strip()
    save_plan(plan)
    print(colorize("  ✓ Observe auto-confirmed via --attestation.", "green"))
    return True


def _validate_recurring_dimension_mentions(
    *,
    report: str,
    recurring_dims: list[str],
    recurring: dict,
) -> bool:
    if not recurring_dims:
        return True
    report_lower = report.lower()
    mentioned = [dim for dim in recurring_dims if dim.lower() in report_lower]
    if mentioned:
        return True
    print(colorize("  Recurring patterns detected but not addressed in report:", "red"))
    for dim in recurring_dims:
        info = recurring[dim]
        print(
            colorize(
                f"    {dim}: {len(info['resolved'])} resolved, "
                f"{len(info['open'])} still open — potential loop",
                "yellow",
            )
        )
    print(
        colorize(
            "  Your report must mention at least one recurring dimension name.",
            "dim",
        )
    )
    return False


def _require_reflect_stage_for_organize(stages: dict) -> bool:
    if "reflect" in stages:
        return True
    if "observe" not in stages:
        print(colorize("  Cannot organize: observe stage not complete.", "red"))
        print(colorize('  Run: desloppify plan triage --stage observe --report "..."', "dim"))
        return False
    print(colorize("  Cannot organize: reflect stage not complete.", "red"))
    print(colorize('  Run: desloppify plan triage --stage reflect --report "..."', "dim"))
    return False


def _auto_confirm_reflect_for_organize(
    *,
    args: argparse.Namespace,
    plan: dict,
    stages: dict,
    attestation: str | None,
) -> bool:
    if stages["reflect"].get("confirmed_at"):
        return True
    if not attestation or len(attestation.strip()) < _MIN_ATTESTATION_LEN:
        print(colorize("  Cannot organize: reflect stage not confirmed.", "red"))
        print(colorize("  Run: desloppify plan triage --confirm reflect", "dim"))
        print(colorize("  Or pass --attestation to auto-confirm reflect inline.", "dim"))
        return False

    runtime = command_runtime(args)
    triage_input = collect_triage_input(plan, runtime.state)
    recurring = detect_recurring_patterns(
        triage_input.open_issues,
        triage_input.resolved_issues,
    )
    _by_dim, observe_dims = observe_dimension_breakdown(triage_input)
    reflect_dims = sorted(set((list(recurring.keys()) if recurring else []) + observe_dims))
    reflect_clusters = [
        name for name in plan.get("clusters", {}) if not plan["clusters"][name].get("auto")
    ]
    validation_err = _validate_attestation(
        attestation.strip(),
        "reflect",
        dimensions=reflect_dims,
        cluster_names=reflect_clusters,
    )
    if validation_err:
        print(colorize(f"  {validation_err}", "red"))
        return False
    stages["reflect"]["confirmed_at"] = utc_now()
    stages["reflect"]["confirmed_text"] = attestation.strip()
    save_plan(plan)
    print(colorize("  ✓ Reflect auto-confirmed via --attestation.", "green"))
    return True


def _manual_clusters_or_error(plan: dict) -> list[str] | None:
    manual_clusters = manual_clusters_with_issues(plan)
    if manual_clusters:
        return manual_clusters
    any_clusters = [
        name for name, cluster in plan.get("clusters", {}).items() if cluster.get("issue_ids")
    ]
    if any_clusters:
        print(colorize("  Cannot organize: only auto-clusters exist.", "red"))
        print(colorize("  Create manual clusters that group issues by root cause:", "dim"))
    else:
        print(colorize("  Cannot organize: no clusters with issues exist.", "red"))
    print(colorize('    desloppify plan cluster create <name> --description "..."', "dim"))
    print(colorize("    desloppify plan cluster add <name> <issue-patterns>", "dim"))
    return None


def _clusters_enriched_or_error(plan: dict) -> bool:
    gaps = _unenriched_clusters(plan)
    if not gaps:
        return True
    print(colorize(f"  Cannot organize: {len(gaps)} cluster(s) need enrichment.", "red"))
    for name, missing in gaps:
        print(colorize(f"    {name}: missing {', '.join(missing)}", "yellow"))
    print()
    print(colorize("  Each cluster needs a description and action steps:", "dim"))
    print(
        colorize(
            '    desloppify plan cluster update <name> --description "what this cluster addresses" '
            '--steps "step 1" "step 2"',
            "dim",
        )
    )
    return False


def _unclustered_review_issues_or_error(plan: dict, state: dict) -> bool:
    """Block if open review issues aren't in any manual cluster. Return True if OK."""
    unclustered = _unclustered_review_issues(plan, state)
    if not unclustered:
        return True
    print(colorize(f"  Cannot organize: {len(unclustered)} review issue(s) have no cluster.", "red"))
    for fid in unclustered[:10]:
        short = fid.rsplit("::", 2)[-2] if "::" in fid else fid
        print(colorize(f"    {short}", "yellow"))
    if len(unclustered) > 10:
        print(colorize(f"    ... and {len(unclustered) - 10} more", "yellow"))
    print()
    print(colorize("  Every review issue needs an action plan. Either:", "dim"))
    print(colorize("    1. Add to a cluster: desloppify plan cluster add <name> <pattern>", "dim"))
    print(colorize('    2. Wontfix it: desloppify plan skip --permanent <pattern> --note "reason" --attest "..."', "dim"))
    return False


def _organize_report_or_error(report: str | None) -> str | None:
    if not report:
        print(colorize("  --report is required for --stage organize.", "red"))
        print(colorize("  Summarize your prioritized organization:", "dim"))
        print(colorize("  - Did you defer contradictory issues before clustering?", "dim"))
        print(colorize("  - What clusters did you create and why?", "dim"))
        print(
            colorize(
                "  - Explicit priority ordering: which cluster 1st, 2nd, 3rd and why?",
                "dim",
            )
        )
        print(colorize("  - What depends on what? What unblocks the most?", "dim"))
        return None
    if len(report) < 100:
        print(colorize(f"  Report too short: {len(report)} chars (minimum 100).", "red"))
        print(colorize("  Explain what you organized, your priorities, and focus order.", "dim"))
        return None
    return report


def _require_organize_stage_for_enrich(stages: dict) -> bool:
    """Gate: organize must be done before enrich."""
    if "organize" in stages:
        return True
    if "observe" not in stages:
        print(colorize("  Cannot enrich: observe stage not complete.", "red"))
        print(colorize('  Run: desloppify plan triage --stage observe --report "..."', "dim"))
        return False
    if "reflect" not in stages:
        print(colorize("  Cannot enrich: reflect stage not complete.", "red"))
        print(colorize('  Run: desloppify plan triage --stage reflect --report "..."', "dim"))
        return False
    print(colorize("  Cannot enrich: organize stage not complete.", "red"))
    print(colorize('  Run: desloppify plan triage --stage organize --report "..."', "dim"))
    return False


def _shallow_steps(plan: dict) -> list[tuple[str, int, int]]:
    """Return (cluster_name, bare_count, total_count) for clusters with steps lacking detail."""
    results: list[tuple[str, int, int]] = []
    for name, cluster in plan.get("clusters", {}).items():
        if cluster.get("auto") or not cluster.get("issue_ids"):
            continue
        steps = cluster.get("action_steps") or []
        if not steps:
            continue
        bare = sum(
            1 for s in steps
            if isinstance(s, dict) and not s.get("detail") and not s.get("issue_refs")
        )
        if bare > 0:
            results.append((name, bare, len(steps)))
    return results


def _steps_with_bad_paths(plan: dict, repo_root: Path) -> list[tuple[str, int, list[str]]]:
    """Return steps referencing file paths that don't exist on disk."""
    results: list[tuple[str, int, list[str]]] = []
    for name, cluster in plan.get("clusters", {}).items():
        if cluster.get("auto") or not cluster.get("issue_ids"):
            continue
        for i, step in enumerate(cluster.get("action_steps") or []):
            if not isinstance(step, dict):
                continue
            detail = step.get("detail", "")
            if not detail:
                continue
            bad: list[str] = []
            for path_str in _PATH_RE.findall(detail):
                p = repo_root / path_str
                if p.exists():
                    continue
                alt_ext = _EXT_SWAPS.get(p.suffix)
                if alt_ext and p.with_suffix(alt_ext).exists():
                    continue
                bad.append(path_str)
            if bad:
                results.append((name, i + 1, bad))
    return results


def _steps_without_effort(plan: dict) -> list[tuple[str, int, int]]:
    """Return (cluster_name, missing_count, total) for steps without effort tags."""
    results: list[tuple[str, int, int]] = []
    for name, cluster in plan.get("clusters", {}).items():
        if cluster.get("auto") or not cluster.get("issue_ids"):
            continue
        steps = cluster.get("action_steps") or []
        if not steps:
            continue
        missing = sum(
            1 for s in steps
            if isinstance(s, dict) and s.get("effort") not in _VALID_EFFORTS
        )
        if missing:
            results.append((name, missing, len(steps)))
    return results


def _cluster_file_overlaps(plan: dict) -> list[tuple[str, str, list[str]]]:
    """Return pairs of clusters with overlapping file references in step details."""
    cluster_files: dict[str, set[str]] = {}
    for name, cluster in plan.get("clusters", {}).items():
        if cluster.get("auto") or not cluster.get("issue_ids"):
            continue
        paths: set[str] = set()
        for step in cluster.get("action_steps") or []:
            if isinstance(step, dict) and step.get("detail"):
                paths.update(_PATH_RE.findall(step["detail"]))
        if paths:
            cluster_files[name] = paths

    overlaps: list[tuple[str, str, list[str]]] = []
    names = sorted(cluster_files.keys())
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            shared = cluster_files[a] & cluster_files[b]
            if shared:
                overlaps.append((a, b, sorted(shared)))
    return overlaps


def _clusters_with_directory_scatter(
    plan: dict, *, threshold: int = 5,
) -> list[tuple[str, int, list[str]]]:
    """Return clusters whose issues span too many unrelated directories.

    A cluster with issues in 5+ distinct top-level directories is likely
    grouped by theme/dimension rather than by file proximity.
    Returns (cluster_name, dir_count, sample_dirs).
    """
    results: list[tuple[str, int, list[str]]] = []
    for name, cluster in plan.get("clusters", {}).items():
        if cluster.get("auto") or not cluster.get("issue_ids"):
            continue
        # Collect file paths from step details
        dirs: set[str] = set()
        for step in cluster.get("action_steps") or []:
            if isinstance(step, dict) and step.get("detail"):
                for path_str in _PATH_RE.findall(step["detail"]):
                    # Use first 2 path components as the "area"
                    # e.g., src/domains/media-lightbox -> src/domains/media-lightbox
                    parts = path_str.split("/")
                    if len(parts) >= 3:
                        dirs.add("/".join(parts[:3]))
                    elif len(parts) >= 2:
                        dirs.add("/".join(parts[:2]))
        if len(dirs) >= threshold:
            results.append((name, len(dirs), sorted(dirs)[:6]))
    return results


def _clusters_with_high_step_ratio(
    plan: dict, *, max_ratio: float = 1.0,
) -> list[tuple[str, int, int, float]]:
    """Return clusters where step count >= issue count (1:1 mapping).

    A well-organized cluster should consolidate related issues into fewer
    steps (because multiple issues touching the same file become one step).
    Returns (cluster_name, steps, issues, ratio).
    """
    results: list[tuple[str, int, int, float]] = []
    for name, cluster in plan.get("clusters", {}).items():
        if cluster.get("auto") or not cluster.get("issue_ids"):
            continue
        steps = len(cluster.get("action_steps") or [])
        issues = len(cluster.get("issue_ids") or [])
        if issues >= 3 and steps > 0:  # only flag non-trivial clusters
            ratio = steps / issues
            if ratio > max_ratio:
                results.append((name, steps, issues, ratio))
    return results


def _steps_missing_issue_refs(plan: dict) -> list[tuple[str, int, int]]:
    """Return (cluster_name, missing_count, total) for steps without issue_refs."""
    results: list[tuple[str, int, int]] = []
    for name, cluster in plan.get("clusters", {}).items():
        if cluster.get("auto") or not cluster.get("issue_ids"):
            continue
        steps = cluster.get("action_steps") or []
        if not steps:
            continue
        missing = sum(
            1 for s in steps
            if isinstance(s, dict) and not s.get("issue_refs")
        )
        if missing:
            results.append((name, missing, len(steps)))
    return results


def _steps_with_vague_detail(plan: dict, repo_root: Path) -> list[tuple[str, int, str]]:
    """Return steps with detail too vague to be executor-ready.

    A step is "vague" if its detail is under 80 chars AND contains no file path.
    Executor-ready means: someone with zero context can read the step and know
    exactly which file to open and what to change.
    """
    results: list[tuple[str, int, str]] = []
    for name, cluster in plan.get("clusters", {}).items():
        if cluster.get("auto") or not cluster.get("issue_ids"):
            continue
        for i, step in enumerate(cluster.get("action_steps") or []):
            if not isinstance(step, dict):
                continue
            detail = step.get("detail", "")
            if not detail:
                continue
            has_path = bool(_PATH_RE.search(detail))
            if len(detail) < 80 and not has_path:
                results.append((name, i + 1, step.get("title", "(no title)")))
    return results


def _steps_referencing_skipped_issues(plan: dict) -> list[tuple[str, int, list[str]]]:
    """Return steps whose issue_refs include wontfixed/skipped issues."""
    wontfixed = set()
    for fid, issue in plan.get("issues", {}).items():
        if isinstance(issue, dict) and issue.get("status") in ("wontfix", "skipped"):
            wontfixed.add(fid)
    # Also check the wontfix list directly
    for fid in plan.get("wontfix", {}):
        wontfixed.add(fid)

    if not wontfixed:
        return []

    results: list[tuple[str, int, list[str]]] = []
    for name, cluster in plan.get("clusters", {}).items():
        if cluster.get("auto") or not cluster.get("issue_ids"):
            continue
        for i, step in enumerate(cluster.get("action_steps") or []):
            if not isinstance(step, dict):
                continue
            refs = step.get("issue_refs") or []
            stale = [r for r in refs if r in wontfixed]
            if stale:
                results.append((name, i + 1, stale))
    return results


def _enrich_report_or_error(report: str | None) -> str | None:
    if not report:
        print(colorize("  --report is required for --stage enrich.", "red"))
        print(colorize("  Summarize the enrichment work you did:", "dim"))
        print(colorize("  - Which clusters did you add detail/refs to?", "dim"))
        print(colorize("  - Are steps specific enough for an executor with zero context?", "dim"))
        print(colorize("  - Did you link issue_refs so steps auto-complete on resolve?", "dim"))
        return None
    if len(report) < 100:
        print(colorize(f"  Report too short: {len(report)} chars (minimum 100).", "red"))
        print(colorize("  Explain what enrichment you did and why steps are executor-ready.", "dim"))
        return None
    return report


def _require_enrich_stage_for_complete(
    *,
    plan: dict,
    meta: dict,
    stages: dict,
) -> bool:
    if "enrich" in stages:
        return True
    if "organize" not in stages:
        # Fall through to existing organize requirement
        return _require_organize_stage_for_complete(plan=plan, meta=meta, stages=stages)

    shallow = _shallow_steps(plan)
    if shallow:
        print(colorize("  Cannot complete: enrich stage not done.", "red"))
        print(colorize(f"  {len(shallow)} cluster(s) have steps without detail or issue_refs:", "yellow"))
        for name, bare, total in shallow[:5]:
            print(colorize(f"    {name}: {bare}/{total} steps need enrichment", "yellow"))
        print(colorize(
            '  Fix: desloppify plan cluster update <name> --update-step N --detail "sub-details"',
            "dim",
        ))
        print(colorize('  Then: desloppify plan triage --stage enrich --report "..."', "dim"))
    else:
        print(colorize("  Cannot complete: enrich stage not recorded.", "red"))
        print(colorize("  Steps look enriched. Record the stage:", "dim"))
        print(colorize('    desloppify plan triage --stage enrich --report "..."', "dim"))
    return False


def _auto_confirm_enrich_for_complete(
    *,
    plan: dict,
    stages: dict,
    attestation: str | None,
) -> bool:
    if stages.get("enrich", {}).get("confirmed_at"):
        return True
    if "enrich" not in stages:
        return False
    if not attestation or len(attestation.strip()) < _MIN_ATTESTATION_LEN:
        print(colorize("  Cannot complete: enrich stage not confirmed.", "red"))
        print(colorize("  Run: desloppify plan triage --confirm enrich", "dim"))
        print(colorize("  Or pass --attestation to auto-confirm enrich inline.", "dim"))
        return False

    # Re-validate shallow steps at auto-confirm time
    shallow = _shallow_steps(plan)
    if shallow:
        total_bare = sum(n for _, n, _ in shallow)
        print(colorize(f"  Cannot auto-confirm enrich: {total_bare} step(s) still lack detail or issue_refs.", "red"))
        for name, bare, total in shallow[:5]:
            print(colorize(f"    {name}: {bare}/{total} steps", "yellow"))
        print(colorize('  Fix: desloppify plan cluster update <name> --update-step N --detail "sub-details"', "dim"))
        return False

    cluster_names = [
        name for name in plan.get("clusters", {}) if not plan["clusters"][name].get("auto")
    ]
    validation_err = _validate_attestation(
        attestation.strip(),
        "enrich",
        cluster_names=cluster_names,
    )
    if validation_err:
        print(colorize(f"  {validation_err}", "red"))
        return False
    stages["enrich"]["confirmed_at"] = utc_now()
    stages["enrich"]["confirmed_text"] = attestation.strip()
    save_plan(plan)
    print(colorize("  ✓ Enrich auto-confirmed via --attestation.", "green"))
    return True


def _require_organize_stage_for_complete(
    *,
    plan: dict,
    meta: dict,
    stages: dict,
) -> bool:
    if "organize" in stages:
        return True
    if "observe" not in stages:
        print(colorize("  Cannot complete: no stages done yet.", "red"))
        print(colorize('  Start with: desloppify plan triage --stage observe --report "..."', "dim"))
        return False

    print(colorize("  Cannot complete: organize stage not done.", "red"))
    gaps = _unenriched_clusters(plan)
    if gaps:
        print(colorize(f"  {len(gaps)} cluster(s) still need enrichment:", "yellow"))
        for name, missing in gaps:
            print(colorize(f"    {name}: missing {', '.join(missing)}", "yellow"))
        print(
            colorize(
                '  Fix: desloppify plan cluster update <name> --description "..." --steps "step1" "step2"',
                "dim",
            )
        )
        print(colorize(f"  Then: {TRIAGE_CMD_ORGANIZE}", "dim"))
    else:
        manual = manual_clusters_with_issues(plan)
        if manual:
            print(colorize("  Clusters are enriched. Record the organize stage first:", "dim"))
            print(colorize(f"    {TRIAGE_CMD_ORGANIZE}", "dim"))
        else:
            print(colorize("  Create enriched clusters first, then record organize:", "dim"))
            print(colorize(f"    {TRIAGE_CMD_ORGANIZE}", "dim"))
    if meta.get("strategy_summary"):
        print(
            colorize(
                '  Or fast-track: --confirm-existing --note "why plan is still valid" --strategy "..."',
                "dim",
            )
        )
    return False


def _auto_confirm_organize_for_complete(
    *,
    plan: dict,
    stages: dict,
    attestation: str | None,
) -> bool:
    if stages["organize"].get("confirmed_at"):
        return True
    if not attestation or len(attestation.strip()) < _MIN_ATTESTATION_LEN:
        print(colorize("  Cannot complete: organize stage not confirmed.", "red"))
        print(colorize("  Run: desloppify plan triage --confirm organize", "dim"))
        print(colorize("  Or pass --attestation to auto-confirm organize inline.", "dim"))
        return False

    organize_clusters = [
        name for name in plan.get("clusters", {}) if not plan["clusters"][name].get("auto")
    ]
    validation_err = _validate_attestation(
        attestation.strip(),
        "organize",
        cluster_names=organize_clusters,
    )
    if validation_err:
        print(colorize(f"  {validation_err}", "red"))
        return False
    stages["organize"]["confirmed_at"] = utc_now()
    stages["organize"]["confirmed_text"] = attestation.strip()
    save_plan(plan)
    print(colorize("  ✓ Organize auto-confirmed via --attestation.", "green"))
    return True


def _completion_clusters_valid(plan: dict, state: dict | None = None) -> bool:
    manual_clusters = manual_clusters_with_issues(plan)
    if not manual_clusters:
        any_clusters = [
            name
            for name, cluster in plan.get("clusters", {}).items()
            if cluster.get("issue_ids")
        ]
        if not any_clusters:
            print(colorize("  Cannot complete: no clusters with issues exist.", "red"))
            print(colorize('  Create clusters: desloppify plan cluster create <name> --description "..."', "dim"))
            return False

    gaps = _unenriched_clusters(plan)
    if gaps:
        print(colorize(f"  Cannot complete: {len(gaps)} cluster(s) still need enrichment.", "red"))
        for name, missing in gaps:
            print(colorize(f"    {name}: missing {', '.join(missing)}", "yellow"))
        print(
            colorize(
                "  Small clusters (<5 issues) need at least 1 action step per issue.",
                "dim",
            )
        )
        print(
            colorize(
                '  Fix: desloppify plan cluster update <name> --description "..." --steps "step1" "step2"',
                "dim",
            )
        )
        return False

    # Check for unclustered review issues
    unclustered = _unclustered_review_issues(plan, state)
    if unclustered:
        print(colorize(f"  Cannot complete: {len(unclustered)} review issue(s) have no action plan.", "red"))
        for fid in unclustered[:5]:
            short = fid.rsplit("::", 2)[-2] if "::" in fid else fid
            print(colorize(f"    {short}", "yellow"))
        if len(unclustered) > 5:
            print(colorize(f"    ... and {len(unclustered) - 5} more", "yellow"))
        print(colorize("  Add to a cluster or wontfix each unclustered issue.", "dim"))
        return False

    return True


def _resolve_completion_strategy(
    strategy: str | None,
    *,
    meta: dict,
) -> str | None:
    if strategy:
        return strategy
    print(colorize("  --strategy is required.", "red"))
    existing = meta.get("strategy_summary", "")
    if existing:
        print(colorize(f"  Current strategy: {existing}", "dim"))
        print(colorize('  Use --strategy "same" to keep it, or provide a new summary.', "dim"))
    else:
        print(
            colorize(
                '  Provide --strategy "execution plan describing priorities, ordering, and verification approach"',
                "dim",
            )
        )
    return None


def _completion_strategy_valid(strategy: str) -> bool:
    if strategy.strip().lower() == "same":
        return True
    if len(strategy.strip()) >= 200:
        return True
    print(colorize(f"  Strategy too short: {len(strategy.strip())} chars (minimum 200).", "red"))
    print(colorize("  The strategy should describe:", "dim"))
    print(colorize("    - Execution order and priorities", "dim"))
    print(colorize("    - What each cluster accomplishes", "dim"))
    print(colorize("    - How to verify the work is correct", "dim"))
    return False


def _require_prior_strategy_for_confirm(meta: dict) -> bool:
    if meta.get("strategy_summary", ""):
        return True
    print(colorize("  Cannot confirm existing: no prior triage has been completed.", "red"))
    print(colorize("  The full OBSERVE → REFLECT → ORGANIZE → COMMIT flow is required the first time.", "dim"))
    print(colorize(f"  Create and enrich clusters, then: {TRIAGE_CMD_ORGANIZE}", "dim"))
    return False


def _confirm_existing_stages_valid(
    *,
    stages: dict,
    has_only_additions: bool,
    si,
) -> bool:
    if has_only_additions:
        _print_new_issues_since_last(si)
        return True
    if "observe" not in stages:
        print(colorize("  Cannot confirm existing: observe stage not complete.", "red"))
        print(colorize("  You must read issues first.", "dim"))
        print(colorize('  Run: desloppify plan triage --stage observe --report "..."', "dim"))
        return False
    if "reflect" not in stages:
        print(colorize("  Cannot confirm existing: reflect stage not complete.", "red"))
        print(colorize("  You must compare against completed work first.", "dim"))
        print(colorize('  Run: desloppify plan triage --stage reflect --report "..."', "dim"))
        return False
    return True


def _confirm_note_valid(note: str | None) -> bool:
    if not note:
        print(colorize("  --note is required for confirm-existing.", "red"))
        print(colorize('  Explain why the existing plan is still valid (min 100 chars).', "dim"))
        return False
    if len(note) < 100:
        print(colorize(f"  Note too short: {len(note)} chars (minimum 100).", "red"))
        return False
    return True


def _resolve_confirm_existing_strategy(
    strategy: str | None,
    *,
    has_only_additions: bool,
    meta: dict,
) -> str | None:
    if strategy:
        return strategy
    if has_only_additions:
        return "same"
    print(colorize("  --strategy is required.", "red"))
    existing = meta.get("strategy_summary", "")
    if existing:
        print(colorize('  Use --strategy "same" to keep it, or provide a new summary.', "dim"))
    return None


def _confirm_strategy_valid(strategy: str) -> bool:
    if strategy.strip().lower() == "same":
        return True
    if len(strategy.strip()) >= 200:
        return True
    print(colorize(f"  Strategy too short: {len(strategy.strip())} chars (minimum 200).", "red"))
    return False


def _confirmed_text_or_error(
    *,
    plan: dict,
    state: dict,
    confirmed: str | None,
) -> str | None:
    if confirmed and len(confirmed.strip()) >= _MIN_ATTESTATION_LEN:
        return confirmed.strip()
    print(colorize("  Current plan:", "bold"))
    show_plan_summary(plan, state)
    if confirmed:
        print(
            colorize(
                f"\n  --confirmed text too short ({len(confirmed.strip())} chars, min {_MIN_ATTESTATION_LEN}).",
                "red",
            )
        )
    print(colorize('\n  Add --confirmed "I validate this plan..." to proceed.', "dim"))
    return None


def _note_cites_new_issues_or_error(note: str, si) -> bool:
    new_ids = si.new_since_last
    if not new_ids:
        return True
    valid_ids = set(si.open_issues.keys())
    cited = extract_issue_citations(note, valid_ids)
    new_cited = cited & new_ids
    if new_cited:
        return True
    print(colorize("  Note must cite at least 1 new/changed issue.", "red"))
    print(colorize(f"  {len(new_ids)} new issue(s) since last triage:", "dim"))
    for fid in sorted(new_ids)[:5]:
        print(colorize(f"    {fid}", "dim"))
    if len(new_ids) > 5:
        print(colorize(f"    ... and {len(new_ids) - 5} more", "dim"))
    return False


__all__ = [
    "_auto_confirm_enrich_for_complete",
    "_auto_confirm_observe_if_attested",
    "_auto_confirm_organize_for_complete",
    "_auto_confirm_reflect_for_organize",
    "_cluster_file_overlaps",
    "_clusters_with_directory_scatter",
    "_clusters_with_high_step_ratio",
    "_clusters_enriched_or_error",
    "_enrich_report_or_error",
    "_unclustered_review_issues_or_error",
    "_completion_clusters_valid",
    "_completion_strategy_valid",
    "_confirm_existing_stages_valid",
    "_confirm_note_valid",
    "_confirm_strategy_valid",
    "_confirmed_text_or_error",
    "_manual_clusters_or_error",
    "_note_cites_new_issues_or_error",
    "_organize_report_or_error",
    "_require_enrich_stage_for_complete",
    "_require_organize_stage_for_complete",
    "_require_organize_stage_for_enrich",
    "_require_prior_strategy_for_confirm",
    "_require_reflect_stage_for_organize",
    "_resolve_completion_strategy",
    "_resolve_confirm_existing_strategy",
    "_shallow_steps",
    "_steps_missing_issue_refs",
    "_steps_referencing_skipped_issues",
    "_steps_with_bad_paths",
    "_steps_with_vague_detail",
    "_steps_without_effort",
    "_validate_recurring_dimension_mentions",
]
