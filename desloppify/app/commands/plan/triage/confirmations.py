"""Attestation and confirmation handlers for plan triage."""

from __future__ import annotations

import argparse

from desloppify.base.output.terminal import colorize
from desloppify.base.output.user_message import print_user_message
from desloppify.state import utc_now

from .display import show_plan_summary
from .helpers import (
    count_log_activity_since,
    observe_dimension_breakdown,
    open_review_ids_from_state,
    purge_triage_stage,
    triage_coverage,
)
from .services import TriageServices, default_triage_services

_MIN_ATTESTATION_LEN = 80


def _validate_attestation(
    attestation: str,
    stage: str,
    *,
    dimensions: list[str] | None = None,
    cluster_names: list[str] | None = None,
) -> str | None:
    """Return error message if attestation doesn't reference required data, else None."""
    text = attestation.lower()

    if stage == "observe":
        if dimensions:
            found = [d for d in dimensions if d.lower().replace("_", " ") in text or d.lower() in text]
            if not found:
                dim_list = ", ".join(dimensions[:6])
                return f"Attestation must reference at least one dimension from the summary. Mention one of: {dim_list}"

    elif stage == "reflect":
        refs: list[str] = []
        if dimensions:
            refs.extend(d for d in dimensions if d.lower().replace("_", " ") in text or d.lower() in text)
        if cluster_names:
            refs.extend(n for n in cluster_names if n.lower() in text)
        if not refs and (dimensions or cluster_names):
            return (
                f"Attestation must reference at least one dimension or cluster name.\n"
                f"  Valid dimensions: {', '.join((dimensions or [])[:6])}\n"
                f"  Valid clusters: {', '.join((cluster_names or [])[:6]) if cluster_names else '(none yet)'}"
            )

    elif stage == "organize":
        if cluster_names:
            found = [n for n in cluster_names if n.lower() in text]
            if not found:
                names = ", ".join(cluster_names[:6])
                return f"Attestation must reference at least one cluster from the plan. Mention one of: {names}"

    elif stage == "enrich":
        if cluster_names:
            found = [n for n in cluster_names if n.lower() in text]
            if not found:
                names = ", ".join(cluster_names[:6])
                return f"Attestation must reference at least one cluster you enriched. Mention one of: {names}"

    return None

def _confirm_observe(
    args: argparse.Namespace,
    plan: dict,
    stages: dict,
    attestation: str | None,
    *,
    services: TriageServices | None = None,
) -> None:
    """Show observe summary and record confirmation if attestation is valid."""
    resolved_services = services or default_triage_services()
    if "observe" not in stages:
        print(colorize("  Cannot confirm: observe stage not recorded.", "red"))
        print(colorize('  Run: desloppify plan triage --stage observe --report "..."', "dim"))
        return
    if stages["observe"].get("confirmed_at"):
        print(colorize("  Observe stage already confirmed.", "green"))
        return

    # Show summary
    runtime = resolved_services.command_runtime(args)
    si = resolved_services.collect_triage_input(plan, runtime.state)
    obs = stages["observe"]

    print(colorize("  Stage: OBSERVE — Analyse issues & spot contradictions", "bold"))
    print(colorize("  " + "─" * 54, "dim"))

    # Dimension breakdown
    by_dim, dim_names = observe_dimension_breakdown(si)

    issue_count = obs.get("issue_count", len(si.open_issues))
    print(f"  Your analysis covered {issue_count} issues across {len(by_dim)} dimensions:")
    for dim in dim_names:
        print(f"    {dim}: {by_dim[dim]} issues")

    cited = obs.get("cited_ids", [])
    if cited:
        print(f"  You cited {len(cited)} issue IDs in your report.")

    # Gate: must cite a meaningful fraction of issues
    min_citations = min(5, max(1, issue_count // 10))  # at least 10% or 5, whichever is smaller
    if len(cited) < min_citations:
        print(colorize(
            f"\n  Cannot confirm: only {len(cited)} issue ID(s) cited in report (need {min_citations}+).",
            "red",
        ))
        print(colorize(
            "  Your observe report should reference specific issues by their hash IDs to prove",
            "dim",
        ))
        print(colorize(
            "  you actually read them. Cite at least 10% of issues or 5, whichever is smaller.",
            "dim",
        ))
        print(colorize(
            "  Re-record observe with more issue citations, then re-confirm.",
            "dim",
        ))
        return

    if not attestation or len(attestation.strip()) < _MIN_ATTESTATION_LEN:
        if attestation:
            print(colorize(
                f"\n  Attestation too short ({len(attestation.strip())} chars, min {_MIN_ATTESTATION_LEN}).",
                "red",
            ))
        print(colorize("\n  If satisfied, confirm:", "dim"))
        print(colorize('    desloppify plan triage --confirm observe --attestation "I have thoroughly reviewed..."', "dim"))
        print(colorize("  If not, continue reviewing issues before reflecting.", "dim"))
        return

    # Validate attestation references actual data
    validation_err = _validate_attestation(attestation.strip(), "observe", dimensions=dim_names)
    if validation_err:
        print(colorize(f"\n  {validation_err}", "red"))
        return

    # Record confirmation
    stages["observe"]["confirmed_at"] = utc_now()
    stages["observe"]["confirmed_text"] = attestation.strip()
    purge_triage_stage(plan, "observe")
    resolved_services.save_plan(plan)
    resolved_services.append_log_entry(
        plan,
        "triage_confirm_observe",
        actor="user",
        detail={"attestation": attestation.strip()},
    )
    resolved_services.save_plan(plan)
    print(colorize(f'  ✓ Observe confirmed: "{attestation.strip()}"', "green"))
    print_user_message(
        "Hey — observe is confirmed. Run `desloppify plan triage"
        " --stage reflect --report \"...\"` next. No need to reply,"
        " just keep going."
    )

def _confirm_reflect(
    args: argparse.Namespace,
    plan: dict,
    stages: dict,
    attestation: str | None,
    *,
    services: TriageServices | None = None,
) -> None:
    """Show reflect summary and record confirmation if attestation is valid."""
    resolved_services = services or default_triage_services()
    if "reflect" not in stages:
        print(colorize("  Cannot confirm: reflect stage not recorded.", "red"))
        print(colorize('  Run: desloppify plan triage --stage reflect --report "..."', "dim"))
        return
    if stages["reflect"].get("confirmed_at"):
        print(colorize("  Reflect stage already confirmed.", "green"))
        return

    runtime = resolved_services.command_runtime(args)
    si = resolved_services.collect_triage_input(plan, runtime.state)
    ref = stages["reflect"]

    print(colorize("  Stage: REFLECT — Form strategy & present to user", "bold"))
    print(colorize("  " + "─" * 50, "dim"))

    # Recurring dimensions
    recurring = resolved_services.detect_recurring_patterns(
        si.open_issues,
        si.resolved_issues,
    )
    if recurring:
        print(f"  Your strategy identified {len(recurring)} recurring dimension(s):")
        for dim, info in sorted(recurring.items()):
            resolved_count = len(info["resolved"])
            open_count = len(info["open"])
            label = "potential loop" if open_count >= resolved_count else "root cause unaddressed"
            print(f"    {dim}: {resolved_count} resolved, {open_count} still open — {label}")
    else:
        print("  No recurring patterns detected.")

    # Strategy briefing excerpt
    report = ref.get("report", "")
    if report:
        print()
        print(colorize("  ┌─ Your strategy briefing ───────────────────────┐", "cyan"))
        for line in report.strip().splitlines()[:8]:
            print(colorize(f"  │ {line}", "cyan"))
        if len(report.strip().splitlines()) > 8:
            print(colorize("  │ ...", "cyan"))
        print(colorize("  └" + "─" * 51 + "┘", "cyan"))

    # Collect data references for validation — include observe-stage dimensions
    _by_dim, observe_dims = observe_dimension_breakdown(si)
    reflect_dims = sorted(set((list(recurring.keys()) if recurring else []) + observe_dims))
    reflect_clusters = [n for n in plan.get("clusters", {}) if not plan["clusters"][n].get("auto")]

    if not attestation or len(attestation.strip()) < _MIN_ATTESTATION_LEN:
        if attestation:
            print(colorize(
                f"\n  Attestation too short ({len(attestation.strip())} chars, min {_MIN_ATTESTATION_LEN}).",
                "red",
            ))
        print(colorize("\n  If satisfied, confirm:", "dim"))
        print(colorize('    desloppify plan triage --confirm reflect --attestation "My strategy accounts for..."', "dim"))
        print(colorize("  If not, refine your strategy before organizing.", "dim"))
        return

    # Validate attestation references actual data
    validation_err = _validate_attestation(
        attestation.strip(), "reflect",
        dimensions=reflect_dims, cluster_names=reflect_clusters,
    )
    if validation_err:
        print(colorize(f"\n  {validation_err}", "red"))
        return

    stages["reflect"]["confirmed_at"] = utc_now()
    stages["reflect"]["confirmed_text"] = attestation.strip()
    purge_triage_stage(plan, "reflect")
    resolved_services.save_plan(plan)
    resolved_services.append_log_entry(
        plan,
        "triage_confirm_reflect",
        actor="user",
        detail={"attestation": attestation.strip()},
    )
    resolved_services.save_plan(plan)
    print(colorize(f'  ✓ Reflect confirmed: "{attestation.strip()}"', "green"))
    print_user_message(
        "Hey — reflect is confirmed. Now create clusters, enrich"
        " them with action steps, then run `desloppify plan triage"
        " --stage organize --report \"...\"`. No need to reply,"
        " just keep going."
    )

def _confirm_organize(
    args: argparse.Namespace,
    plan: dict,
    stages: dict,
    attestation: str | None,
    *,
    services: TriageServices | None = None,
) -> None:
    """Show full plan summary and record confirmation if attestation is valid."""
    resolved_services = services or default_triage_services()
    if "organize" not in stages:
        print(colorize("  Cannot confirm: organize stage not recorded.", "red"))
        print(colorize('  Run: desloppify plan triage --stage organize --report "..."', "dim"))
        return
    if stages["organize"].get("confirmed_at"):
        print(colorize("  Organize stage already confirmed.", "green"))
        return

    runtime = resolved_services.command_runtime(args)
    state = runtime.state

    print(colorize("  Stage: ORGANIZE — Defer contradictions, cluster, & prioritize", "bold"))
    print(colorize("  " + "─" * 63, "dim"))

    # Activity since reflect
    reflect_ts = stages.get("reflect", {}).get("timestamp", "")
    if reflect_ts:
        activity = count_log_activity_since(plan, reflect_ts)
        if activity:
            print("  Since reflect, you have:")
            for action, count in sorted(activity.items()):
                print(f"    {action}: {count}")
        else:
            print("  No logged plan operations since reflect.")

    # Show full plan
    print(colorize("\n  Plan:", "bold"))
    show_plan_summary(plan, state)

    organize_clusters = [n for n in plan.get("clusters", {}) if not plan["clusters"][n].get("auto")]

    # Re-validate enrichment at confirm time
    from .stage_helpers import _unclustered_review_issues, _unenriched_clusters

    gaps = _unenriched_clusters(plan)
    if gaps:
        print(colorize(f"\n  Cannot confirm: {len(gaps)} cluster(s) still need enrichment.", "red"))
        for name, missing in gaps:
            print(colorize(f"    {name}: missing {', '.join(missing)}", "yellow"))
        print(colorize("  Small clusters (<5 issues) need at least 1 action step per issue.", "dim"))
        print(
            colorize(
                '  Fix: desloppify plan cluster update <name> --steps "step1" "step2"',
                "dim",
            )
        )
        return

    unclustered = _unclustered_review_issues(plan, state)
    if unclustered:
        print(colorize(f"\n  Cannot confirm: {len(unclustered)} review issue(s) have no action plan.", "red"))
        for fid in unclustered[:5]:
            short = fid.rsplit("::", 2)[-2] if "::" in fid else fid
            print(colorize(f"    {short}", "yellow"))
        if len(unclustered) > 5:
            print(colorize(f"    ... and {len(unclustered) - 5} more", "yellow"))
        print(colorize("  Add each to a cluster or wontfix it before confirming.", "dim"))
        return

    # Advisory: directory scatter warning (theme-grouping instead of area-grouping)
    from ._stage_validation import (
        _cluster_file_overlaps,
        _clusters_with_directory_scatter,
        _clusters_with_high_step_ratio,
    )
    scattered = _clusters_with_directory_scatter(plan)
    if scattered:
        print(colorize(f"\n  Warning: {len(scattered)} cluster(s) span many unrelated directories:", "yellow"))
        for name, dir_count, sample_dirs in scattered:
            print(colorize(f"    {name}: {dir_count} directories — likely grouped by theme, not area", "yellow"))
            for d in sample_dirs[:3]:
                print(colorize(f"      {d}", "dim"))
        print(colorize("  Consider splitting into area-focused clusters (same files in same PR).", "dim"))

    # Advisory: high step-to-issue ratio (1:1 mapping instead of consolidation)
    high_ratio = _clusters_with_high_step_ratio(plan)
    if high_ratio:
        print(colorize(f"\n  Warning: {len(high_ratio)} cluster(s) have step count ≥ issue count:", "yellow"))
        for name, steps, issues, ratio in high_ratio:
            print(colorize(f"    {name}: {steps} steps for {issues} issues ({ratio:.1f}x)", "yellow"))
        print(colorize("  Steps should consolidate changes to the same file. 1:1 means each issue is its own step.", "dim"))

    # Advisory: cross-cluster file overlap warning with specific suggestions
    overlaps = _cluster_file_overlaps(plan)
    if overlaps:
        clusters = plan.get("clusters", {})
        print(colorize(f"\n  Note: {len(overlaps)} cluster pair(s) reference the same files:", "yellow"))
        for a, b, files in overlaps[:5]:
            print(colorize(f"    {a} ↔ {b}: {len(files)} shared file(s)", "yellow"))
        # Suggest specific --depends-on for pairs that don't already have a dependency
        needs_dep = []
        for a, b, files in overlaps:
            a_deps = set(clusters.get(a, {}).get("depends_on_clusters", []))
            b_deps = set(clusters.get(b, {}).get("depends_on_clusters", []))
            if b not in a_deps and a not in b_deps:
                needs_dep.append((a, b, files))
        if needs_dep:
            print(colorize("  These pairs have no dependency relationship — add one to prevent merge conflicts:", "dim"))
            for a, b, _files in needs_dep[:5]:
                print(colorize(f"    desloppify plan cluster update {b} --depends-on {a}", "dim"))
                print(colorize(f"    # or: desloppify plan cluster update {a} --depends-on {b}", "dim"))

    # Advisory: dependency self-references
    clusters = plan.get("clusters", {})
    for cname, c in clusters.items():
        deps = c.get("depends_on_clusters", [])
        if cname in deps:
            print(colorize(f"  Warning: {cname} depends on itself.", "yellow"))

    # Advisory: clusters with steps but no issues (may need cleanup)
    orphaned = [
        (n, len(c.get("action_steps", [])))
        for n, c in clusters.items()
        if not c.get("auto") and not c.get("issue_ids") and c.get("action_steps")
    ]
    if orphaned:
        print(colorize(f"\n  Note: {len(orphaned)} cluster(s) have steps but no issues:", "yellow"))
        for name, step_count in orphaned:
            print(colorize(f"    {name}: {step_count} steps, 0 issues", "yellow"))
        print(colorize("  These may need issues added, or may be leftover from resolved work.", "dim"))

    if not attestation or len(attestation.strip()) < _MIN_ATTESTATION_LEN:
        if attestation:
            print(colorize(
                f"\n  Attestation too short ({len(attestation.strip())} chars, min {_MIN_ATTESTATION_LEN}).",
                "red",
            ))
        print(colorize("\n  If satisfied, confirm:", "dim"))
        print(colorize('    desloppify plan triage --confirm organize --attestation "This plan is correct..."', "dim"))
        print(colorize("  If not, adjust clusters, priorities, or queue order before completing.", "dim"))
        return

    # Validate attestation references actual data
    validation_err = _validate_attestation(
        attestation.strip(), "organize", cluster_names=organize_clusters,
    )
    if validation_err:
        print(colorize(f"\n  {validation_err}", "red"))
        return

    organized, total, _ = triage_coverage(
        plan, open_review_ids=open_review_ids_from_state(state),
    )
    stages["organize"]["confirmed_at"] = utc_now()
    stages["organize"]["confirmed_text"] = attestation.strip()
    purge_triage_stage(plan, "organize")
    resolved_services.save_plan(plan)
    resolved_services.append_log_entry(
        plan,
        "triage_confirm_organize",
        actor="user",
        detail={
            "attestation": attestation.strip(),
            "coverage": f"{organized}/{total}",
        },
    )
    resolved_services.save_plan(plan)
    print(colorize(f'  ✓ Organize confirmed: "{attestation.strip()}"', "green"))
    print_user_message(
        "Hey — organize is confirmed. Next: enrich your steps"
        " with detail and issue_refs so they're executor-ready."
        " Run `desloppify plan triage --stage enrich --report \"...\"`."
        " You can still reorganize (add/remove clusters, reorder)"
        " during the enrich stage."
    )

def _confirm_enrich(
    args: argparse.Namespace,
    plan: dict,
    stages: dict,
    attestation: str | None,
    *,
    services: TriageServices | None = None,
) -> None:
    """Show enrich summary and record confirmation if attestation is valid."""
    resolved_services = services or default_triage_services()
    if "enrich" not in stages:
        print(colorize("  Cannot confirm: enrich stage not recorded.", "red"))
        print(colorize('  Run: desloppify plan triage --stage enrich --report "..."', "dim"))
        return
    if stages["enrich"].get("confirmed_at"):
        print(colorize("  Enrich stage already confirmed.", "green"))
        return

    from ._stage_validation import (
        _shallow_steps,
        _steps_missing_issue_refs,
        _steps_referencing_skipped_issues,
        _steps_with_bad_paths,
        _steps_with_vague_detail,
        _steps_without_effort,
    )

    print(colorize("  Stage: ENRICH — Make steps executor-ready (detail, refs)", "bold"))
    print(colorize("  " + "─" * 54, "dim"))

    shallow = _shallow_steps(plan)
    if shallow:
        total_bare = sum(n for _, n, _ in shallow)
        print(colorize(f"  Cannot confirm: {total_bare} step(s) still lack detail or issue_refs.", "red"))
        for name, bare, total in shallow[:5]:
            print(colorize(f"    {name}: {bare}/{total} steps", "yellow"))
        print()
        print(colorize("  Every step needs --detail (sub-points) or --issue-refs (for auto-completion).", "dim"))
        print(colorize("  Fix:", "dim"))
        print(colorize('    desloppify plan cluster update <name> --update-step N --detail "sub-details"', "dim"))
        return
    else:
        print(colorize("  All steps have detail or issue_refs.", "green"))

    # Block on bad file paths at confirm time
    from desloppify.base.discovery.paths import get_project_root
    bad_paths = _steps_with_bad_paths(plan, get_project_root())
    if bad_paths:
        total_bad = sum(len(bp) for _, _, bp in bad_paths)
        print(colorize(f"\n  Cannot confirm: {total_bad} file path(s) in step details don't exist on disk.", "red"))
        for name, step_num, paths in bad_paths:
            for p in paths:
                print(colorize(f"    {name} step {step_num}: {p}", "yellow"))
        print(colorize("  Fix paths with: desloppify plan cluster update <name> --update-step N --detail '...'", "dim"))
        return

    # Block on missing effort tags (was advisory, now blocking)
    untagged = _steps_without_effort(plan)
    if untagged:
        total_missing = sum(n for _, n, _ in untagged)
        print(colorize(f"\n  Cannot confirm: {total_missing} step(s) have no effort tag.", "red"))
        for name, missing, total in untagged[:5]:
            print(colorize(f"    {name}: {missing}/{total} steps missing effort", "yellow"))
        print(colorize("  Every step needs --effort (trivial/small/medium/large).", "dim"))
        print(colorize("  Fix: desloppify plan cluster update <name> --update-step N --effort small", "dim"))
        return

    # Block on missing issue_refs (traceability)
    no_refs = _steps_missing_issue_refs(plan)
    if no_refs:
        total_missing = sum(n for _, n, _ in no_refs)
        print(colorize(f"\n  Cannot confirm: {total_missing} step(s) have no issue_refs.", "red"))
        for name, missing, total in no_refs[:5]:
            print(colorize(f"    {name}: {missing}/{total} steps missing refs", "yellow"))
        print(colorize("  Every step needs --issue-refs linking it to the review issue(s) it addresses.", "dim"))
        print(colorize("  Fix: desloppify plan cluster update <name> --update-step N --issue-refs <hash1> <hash2>", "dim"))
        return

    # Block on vague detail (too short, no file paths)
    vague = _steps_with_vague_detail(plan, get_project_root())
    if vague:
        print(colorize(f"\n  Cannot confirm: {len(vague)} step(s) have vague detail (< 80 chars, no file paths).", "red"))
        for name, step_num, title in vague[:5]:
            print(colorize(f"    {name} step {step_num}: {title}", "yellow"))
        print(colorize("  Executor-ready means: someone with zero context knows which file to open and what to change.", "dim"))
        print(colorize("  Add file paths and specific instructions to each step's --detail.", "dim"))
        return

    # Warn on steps referencing skipped/wontfixed issues
    stale_refs = _steps_referencing_skipped_issues(plan)
    if stale_refs:
        total_stale = sum(len(ids) for _, _, ids in stale_refs)
        print(colorize(f"\n  Warning: {total_stale} step issue_ref(s) point to skipped/wontfixed issues.", "yellow"))
        for name, step_num, ids in stale_refs[:5]:
            print(colorize(f"    {name} step {step_num}: {', '.join(ids[:3])}", "yellow"))
        print(colorize("  Consider removing stale refs or removing the step if it's no longer needed.", "dim"))

    enrich_clusters = [n for n in plan.get("clusters", {}) if not plan["clusters"][n].get("auto")]

    if not attestation or len(attestation.strip()) < _MIN_ATTESTATION_LEN:
        if attestation:
            print(colorize(
                f"\n  Attestation too short ({len(attestation.strip())} chars, min {_MIN_ATTESTATION_LEN}).",
                "red",
            ))
        print(colorize("\n  If satisfied, confirm:", "dim"))
        print(colorize('    desloppify plan triage --confirm enrich --attestation "Steps are executor-ready..."', "dim"))
        return

    validation_err = _validate_attestation(
        attestation.strip(), "enrich", cluster_names=enrich_clusters,
    )
    if validation_err:
        print(colorize(f"\n  {validation_err}", "red"))
        return

    stages["enrich"]["confirmed_at"] = utc_now()
    stages["enrich"]["confirmed_text"] = attestation.strip()
    purge_triage_stage(plan, "enrich")
    resolved_services.save_plan(plan)
    resolved_services.append_log_entry(
        plan,
        "triage_confirm_enrich",
        actor="user",
        detail={"attestation": attestation.strip()},
    )
    resolved_services.save_plan(plan)
    print(colorize(f'  ✓ Enrich confirmed: "{attestation.strip()}"', "green"))
    print_user_message(
        "Hey — enrich is confirmed. Run `desloppify plan triage"
        " --complete --strategy \"...\"` to finish triage."
    )


def _cmd_confirm_stage(
    args: argparse.Namespace,
    *,
    services: TriageServices | None = None,
) -> None:
    """Router for ``--confirm observe/reflect/organize/enrich``."""
    resolved_services = services or default_triage_services()
    confirm_stage = getattr(args, "confirm", None)
    attestation = getattr(args, "attestation", None)
    plan = resolved_services.load_plan()
    meta = plan.get("epic_triage_meta", {})
    stages = meta.get("triage_stages", {})

    if confirm_stage == "observe":
        _confirm_observe(args, plan, stages, attestation, services=resolved_services)
    elif confirm_stage == "reflect":
        _confirm_reflect(args, plan, stages, attestation, services=resolved_services)
    elif confirm_stage == "organize":
        _confirm_organize(args, plan, stages, attestation, services=resolved_services)
    elif confirm_stage == "enrich":
        _confirm_enrich(args, plan, stages, attestation, services=resolved_services)


MIN_ATTESTATION_LEN = _MIN_ATTESTATION_LEN
validate_attestation = _validate_attestation


def cmd_confirm_stage(
    args: argparse.Namespace,
    *,
    services: TriageServices | None = None,
) -> None:
    """Public triage confirmation entrypoint."""
    _cmd_confirm_stage(args, services=services)

__all__ = [
    "MIN_ATTESTATION_LEN",
    "cmd_confirm_stage",
    "validate_attestation",
    "_MIN_ATTESTATION_LEN",
    "_cmd_confirm_stage",
    "_confirm_enrich",
    "_confirm_observe",
    "_confirm_organize",
    "_confirm_reflect",
    "_validate_attestation",
]
