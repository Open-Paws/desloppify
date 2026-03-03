"""Post-render nudges and resolution hints for the `next` command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from desloppify.app.commands.next_parts.render_support import (
    is_auto_fix_command,
    scorecard_subjective,
    subjective_coverage_breakdown,
)
from desloppify.app.commands.scan.scan_reporting_subjective import (
    build_subjective_followup,
)
from desloppify.engine.work_queue import ATTEST_EXAMPLE
from desloppify.intelligence.integrity import (
    is_holistic_subjective_issue,
    unassessed_subjective_dimensions,
)
from desloppify.core.output_api import colorize, log
from desloppify.scoring import compute_health_breakdown

if TYPE_CHECKING:
    from desloppify.app.commands.helpers.queue_progress import QueueBreakdown


def render_uncommitted_reminder(plan: dict | None) -> None:
    """Show a subtle reminder if there are uncommitted resolved issues."""
    if plan is None:
        return
    try:
        from desloppify.core.config import load_config

        config = load_config()
        if not config.get("commit_tracking_enabled", True):
            return

        uncommitted = plan.get("uncommitted_issues", [])
        if not uncommitted:
            return

        count = len(uncommitted)
        print(colorize(
            f"\n  {count} resolved issue{'s' if count != 1 else ''} uncommitted"
            " — `desloppify plan commit-log` to review",
            "dim",
        ))
    except (ImportError, OSError, ValueError, KeyError, TypeError) as exc:
        log(f"  uncommitted reminder skipped: {exc}")


def render_single_item_resolution_hint(items: list[dict]) -> None:
    if len(items) != 1:
        return
    kind = items[0].get("kind", "issue")
    if kind in ("cluster", "workflow_stage", "workflow_action"):
        return  # These kinds have their own resolution hints
    if kind != "issue":
        return
    item = items[0]
    detector_name = item.get("detector", "")
    if detector_name == "subjective_review":
        print(colorize("\n  Review with:", "dim"))
        primary = item.get(
            "primary_command", "desloppify show subjective"
        )
        print(f"    {primary}")
        if is_holistic_subjective_issue(item):
            print("    desloppify review --prepare")
        return

    primary = item.get("primary_command", "")
    if is_auto_fix_command(primary):
        print(colorize("\n  Fix with:", "dim"))
        print(f"    {primary}")
        print(colorize("  Or resolve individually:", "dim"))
    else:
        print(colorize("\n  Resolve with:", "dim"))

    print(
        f'    desloppify plan resolve "{item["id"]}" --note "<what you did>" --confirm'
    )
    print(
        f'    desloppify plan skip --permanent "{item["id"]}" --note "<why>" '
        f'--attest "{ATTEST_EXAMPLE}"'
    )


def render_followup_nudges(
    state: dict,
    dim_scores: dict,
    issues_scoped: dict,
    *,
    strict_score: float | None,
    target_strict_score: float,
    queue_total: int = 0,
    plan_start_strict: float | None = None,
    breakdown: "QueueBreakdown | None" = None,
) -> None:
    from desloppify.app.commands.helpers.queue_progress import (
        format_queue_block,
    )

    subjective_threshold = target_strict_score
    subjective_entries = scorecard_subjective(state, dim_scores)
    followup = build_subjective_followup(
        state,
        subjective_entries,
        threshold=subjective_threshold,
        max_quality_items=3,
        max_integrity_items=5,
    )
    unassessed_subjective = unassessed_subjective_dimensions(dim_scores)
    # Show frozen plan-start score + queue block when in an active cycle
    if queue_total > 0 and plan_start_strict is not None and breakdown is not None:
        frozen = plan_start_strict
        block = format_queue_block(breakdown, frozen_score=frozen, live_score=strict_score)
        print()
        for text, style in block:
            print(colorize(text, style))
        print(colorize(
            "  Score will not update until the queue is clear and you run `desloppify scan`.",
            "dim",
        ))
    elif queue_total > 0 and plan_start_strict is not None:
        from desloppify.app.commands.helpers.queue_progress import format_plan_delta
        delta_str = format_plan_delta(strict_score, plan_start_strict) if strict_score is not None else ""
        if delta_str:
            score_line = f"\n  Score: strict {strict_score:.1f}/100 (plan start: {plan_start_strict:.1f}, {delta_str})"
        else:
            score_line = f"\n  Score (frozen at plan start): strict {plan_start_strict:.1f}/100"
        print(colorize(score_line, "cyan"))
        print(
            colorize(
                f"  Queue: {queue_total} item{'s' if queue_total != 1 else ''}"
                " remaining. Score will not update until the queue is clear and you run `desloppify scan`.",
                "dim",
            )
        )
    elif strict_score is not None:
        gap = round(float(target_strict_score) - float(strict_score), 1)
        if gap > 0:
            print(
                colorize(
                    f"\n  North star: strict {strict_score:.1f}/100 → target {target_strict_score:.1f} (+{gap:.1f} needed)",
                    "cyan",
                )
            )
        else:
            print(
                colorize(
                    f"\n  North star: strict {strict_score:.1f}/100 meets target {target_strict_score:.1f}",
                    "green",
                )
            )
    # Show queue block after north star when no frozen score
    if breakdown is not None and queue_total > 0 and plan_start_strict is None:
        block = format_queue_block(breakdown)
        for text, style in block:
            print(colorize(text, style))

    # Subjective bottleneck banner — only shown when the objective queue is
    # clear.  While objective items remain, the queue is the single authority
    # on what to work on next; no need to distract with subjective advice.
    _objective_remaining = max(
        0,
        (breakdown.queue_total - breakdown.subjective) if breakdown else queue_total,
    )
    if strict_score is not None and dim_scores and _objective_remaining <= 0:
        try:
            health_breakdown = compute_health_breakdown(dim_scores)
            subjective_drag = sum(
                float(e.get("overall_drag", 0) or 0)
                for e in health_breakdown.get("entries", [])
                if isinstance(e, dict) and e.get("component") == "subjective"
            )
            mechanical_drag = sum(
                float(e.get("overall_drag", 0) or 0)
                for e in health_breakdown.get("entries", [])
                if isinstance(e, dict) and e.get("component") != "subjective"
            )
            if subjective_drag > mechanical_drag and subjective_drag > 5.0:
                print(colorize(
                    f"\n  Subjective dimensions are the main bottleneck "
                    f"(-{subjective_drag:.0f} pts vs -{mechanical_drag:.0f} pts mechanical).",
                    "yellow",
                ))
                print(colorize(
                    "  Code fixes alone won't close the gap — run "
                    "`desloppify review --run-batches --runner codex --parallel --scan-after-import` "
                    "to re-score.",
                    "yellow",
                ))
        except (ImportError, TypeError, ValueError, KeyError) as exc:
            log(f"  subjective bottleneck banner skipped: {exc}")

    # Integrity penalty/warn lines preserved (anti-gaming safeguard, must remain visible).
    for style, message in followup.integrity_lines:
        print(colorize(f"\n  {message}", style))

    # Rescan nudge after structural work
    if queue_total > 10:
        print(colorize(
            "\n  Tip: after structural fixes (splitting files, moving code), rescan to "
            "let cascade effects settle: `desloppify scan --path .`",
            "dim",
        ))

    # Collapsed subjective summary.
    coverage_open, _coverage_reasons, _holistic_reasons = subjective_coverage_breakdown(
        issues_scoped
    )
    parts: list[str] = []
    low_dims = len(followup.low_assessed)
    unassessed_count = len(unassessed_subjective)
    stale_count = sum(1 for e in subjective_entries if e.get("stale"))
    open_review = [
        f for f in issues_scoped.values()
        if f.get("status") == "open" and f.get("detector") == "review"
    ]
    if low_dims:
        parts.append(f"{low_dims} dimension{'s' if low_dims != 1 else ''} below target")
    if stale_count:
        parts.append(f"{stale_count} stale")
    if unassessed_count:
        parts.append(f"{unassessed_count} unassessed")
    if len(open_review):
        parts.append(f"{len(open_review)} review issue{'s' if len(open_review) != 1 else ''} open")
    if coverage_open > 0:
        parts.append(f"{coverage_open} file{'s' if coverage_open != 1 else ''} need review")

    if parts:
        print(colorize(f"\n  Subjective: {', '.join(parts)}.", "cyan"))
        print(colorize("  Run `desloppify show subjective` for details.", "dim"))
