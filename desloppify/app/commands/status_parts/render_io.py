"""I/O-oriented status render helpers."""

from __future__ import annotations

from desloppify import state as state_mod
from desloppify.app.commands.helpers.query import write_query
from desloppify.core.output_api import colorize, print_table
from desloppify.scoring import compute_health_breakdown


def show_tier_progress_table(by_tier: dict) -> None:
    """Fallback display when dimension scores are unavailable."""
    rows = []
    for tier_num in [1, 2, 3, 4]:
        ts = by_tier.get(str(tier_num), {})
        t_open = ts.get("open", 0)
        t_fixed = ts.get("fixed", 0) + ts.get("auto_resolved", 0)
        t_wontfix = ts.get("wontfix", 0)
        t_total = sum(ts.values())
        strict_pct = round((t_fixed + ts.get("false_positive", 0)) / t_total * 100) if t_total else 100
        bar_len = 20
        filled = round(strict_pct / 100 * bar_len)
        bar = colorize("█" * filled, "green") + colorize("░" * (bar_len - filled), "dim")
        rows.append(
            [
                f"Tier {tier_num}",
                bar,
                f"{strict_pct}%",
                str(t_open),
                str(t_fixed),
                str(t_wontfix),
            ]
        )
    print_table(
        ["Tier", "Strict Progress", "%", "Open", "Fixed", "Debt"],
        rows,
        [40, 22, 5, 6, 6, 6],
    )


def status_next_command(narrative: dict) -> str:
    actions = narrative.get("actions", [])
    return actions[0]["command"] if actions else "desloppify next --count 20"


def write_status_query(
    *,
    state: dict,
    stats: dict,
    by_tier: dict,
    dim_scores: dict,
    scorecard_dims: list[dict],
    subjective_measures: list[dict],
    suppression: dict,
    narrative: dict,
    ignores: list[str],
    overall_score: float | None,
    objective_score: float | None,
    strict_score: float | None,
    verified_strict_score: float | None,
    plan: dict | None = None,
) -> None:
    issues = state.get("issues", {})
    open_scope = (
        state_mod.open_scope_breakdown(issues, state.get("scan_path"))
        if isinstance(issues, dict)
        else None
    )
    write_query(
        {
            "command": "status",
            "overall_score": overall_score,
            "objective_score": objective_score,
            "strict_score": strict_score,
            "verified_strict_score": verified_strict_score,
            "dimension_scores": dim_scores,
            "scorecard_dimensions": scorecard_dims,
            "subjective_measures": subjective_measures,
            "stats": stats,
            "scan_count": state.get("scan_count", 0),
            "last_scan": state.get("last_scan"),
            "by_tier": by_tier,
            "ignores": ignores,
            "suppression": suppression,
            "potentials": state.get("potentials"),
            "codebase_metrics": state.get("codebase_metrics"),
            "open_scope": open_scope,
            "score_breakdown": compute_health_breakdown(dim_scores) if dim_scores else None,
            "next_command": status_next_command(narrative),
            "narrative": narrative,
            **(
                {
                    "plan": {
                        "active": True,
                        "focus": plan.get("active_cluster"),
                        "total_ordered": len(plan.get("queue_order", [])),
                        "total_skipped": len(plan.get("skipped", {})),
                        "plan_overrides_narrative": True,
                    }
                }
                if plan and (plan.get("queue_order") or plan.get("clusters") or plan.get("skipped"))
                else {}
            ),
        }
    )


def show_ignore_summary(ignores: list[str], suppression: dict) -> None:
    """Show ignore list plus suppression accountability from recent scans."""
    print(colorize(f"\n  Ignore list ({len(ignores)}):", "dim"))
    for pattern in ignores[:10]:
        print(colorize(f"    {pattern}", "dim"))

    last_ignored = int(suppression.get("last_ignored", 0) or 0)
    last_raw = int(suppression.get("last_raw_issues", 0) or 0)
    last_pct = float(suppression.get("last_suppressed_pct", 0.0) or 0.0)

    if last_raw > 0:
        style = "red" if last_pct >= 30 else "yellow" if last_pct >= 10 else "dim"
        print(
            colorize(
                f"  Ignore suppression (last scan): {last_ignored}/{last_raw} issues hidden ({last_pct:.1f}%)",
                style,
            )
        )
    elif suppression.get("recent_scans", 0):
        print(colorize("  Ignore suppression (last scan): 0 issues hidden", "dim"))

    recent_scans = int(suppression.get("recent_scans", 0) or 0)
    recent_raw = int(suppression.get("recent_raw_issues", 0) or 0)
    if recent_scans > 1 and recent_raw > 0:
        recent_ignored = int(suppression.get("recent_ignored", 0) or 0)
        recent_pct = float(suppression.get("recent_suppressed_pct", 0.0) or 0.0)
        print(
            colorize(
                f"    Recent ({recent_scans} scans): {recent_ignored}/{recent_raw} issues hidden ({recent_pct:.1f}%)",
                "dim",
            )
        )


__all__ = [
    "show_ignore_summary",
    "show_tier_progress_table",
    "status_next_command",
    "write_status_query",
]

