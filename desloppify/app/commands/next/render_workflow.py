"""Workflow item rendering helpers for next terminal output."""

from __future__ import annotations


def step_text(step: str | dict) -> str:
    """Extract display text from an action step (string or dict with title)."""
    if isinstance(step, dict):
        return step.get("title", str(step))
    return str(step)


def render_workflow_stage(item: dict, *, colorize_fn, workflow_stage_name_fn) -> None:
    """Render a triage workflow stage item."""
    blocked = item.get("is_blocked", False)
    detail = item.get("detail", {})
    stage = workflow_stage_name_fn(item)
    tag = " [blocked]" if blocked else ""
    style = "dim" if blocked else "bold"
    print(colorize_fn(f"  (Planning stage: {stage}{tag})", style))
    print(colorize_fn("  " + "─" * 60, "dim"))
    print(f"  {colorize_fn(item.get('summary', ''), 'yellow')}")
    total = detail.get("total_review_issues", 0)
    if total:
        print(colorize_fn(f"  {total} review issues to analyze", "dim"))
    if blocked:
        blocked_by = item.get("blocked_by", [])
        deps = ", ".join(dep.replace("triage::", "") for dep in blocked_by)
        print(colorize_fn(f"  Blocked by: {deps}", "dim"))
        first_dep = blocked_by[0] if blocked_by else ""
        dep_name = first_dep.replace("triage::", "")
        if dep_name:
            print(colorize_fn(f"  Next step: desloppify plan triage --stage {dep_name}", "dim"))
    else:
        print(colorize_fn(f"\n  Action: {item.get('primary_command', '')}", "cyan"))


def _render_workflow_action(item: dict, *, colorize_fn) -> None:
    """Render a workflow action item (e.g. create-plan)."""
    print(colorize_fn("  (Workflow step)", "bold"))
    print(colorize_fn("  " + "─" * 60, "dim"))
    print(f"  {colorize_fn(item.get('summary', ''), 'yellow')}")
    print(colorize_fn(f"\n  Action: {item.get('primary_command', '')}", "cyan"))


def render_workflow_action(item: dict, *, colorize_fn) -> None:
    """Public compatibility wrapper for workflow-action rendering."""
    _render_workflow_action(item, colorize_fn=colorize_fn)


__all__ = ["render_workflow_action", "render_workflow_stage", "step_text"]
