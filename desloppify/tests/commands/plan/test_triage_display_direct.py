"""Direct coverage tests for triage display helpers."""

from __future__ import annotations

from types import SimpleNamespace

import desloppify.app.commands.plan.triage.display.dashboard as display_mod
import desloppify.app.commands.plan.triage.display.layout as layout_mod
import desloppify.app.commands.plan.triage.display.primitives as primitives_mod
import desloppify.engine.plan_triage as triage_mod


def test_print_stage_progress_shows_enrichment_gap(monkeypatch, capsys) -> None:
    monkeypatch.setattr(primitives_mod, "colorize", lambda text, _style: text)
    monkeypatch.setattr(primitives_mod, "unenriched_clusters", lambda _plan: [("cluster-a", ["steps"])])
    monkeypatch.setattr(primitives_mod, "manual_clusters_with_issues", lambda _plan: ["cluster-a"])

    display_mod.print_stage_progress({"reflect": {}}, plan={"clusters": {}})

    out = capsys.readouterr().out
    assert "cluster(s) need enrichment" in out
    assert "cluster-a" in out


def test_print_progress_reports_unclustered_issues(monkeypatch, capsys) -> None:
    monkeypatch.setattr(display_mod, "colorize", lambda text, _style: text)
    monkeypatch.setattr(display_mod, "short_issue_id", lambda fid: fid.split("::")[-1])

    plan = {
        "clusters": {
            "cluster-a": {
                "issue_ids": ["review::aaa111"],
                "description": "desc",
                "action_steps": ["step 1"],
                "auto": False,
            }
        }
    }
    open_issues = {
        "review::aaa111": {"summary": "clustered", "detail": {"dimension": "design"}},
        "review::bbb222": {"summary": "unclustered", "detail": {"dimension": "tests"}},
    }

    display_mod.print_progress(plan, open_issues)

    out = capsys.readouterr().out
    assert "1 issues not yet in a cluster" in out
    assert "[bbb222] [tests] unclustered" in out
    assert "Current clusters:" in out


# ---------------------------------------------------------------------------
# print_action_guidance — post-completion state
# ---------------------------------------------------------------------------


def _stub_si(*, new_since_last=None, resolved_since_last=None, **kwargs):
    """Build a minimal triage-input stub for layout tests."""
    return SimpleNamespace(
        new_since_last=new_since_last or set(),
        resolved_since_last=resolved_since_last or {},
        open_issues=kwargs.get("open_issues", {}),
        existing_epics=[],
    )


def test_action_guidance_shows_execution_after_completion(monkeypatch, capsys) -> None:
    """After triage completion (empty stages, triaged_ids present, no new issues),
    guidance should say 'Triage complete' not 'start with observe'."""
    monkeypatch.setattr(layout_mod, "colorize", lambda text, _style: text)

    stages: dict = {}
    meta = {
        "triaged_ids": ["review::aaa111", "review::bbb222"],
        "triage_stages": {},
    }
    si = _stub_si()
    plan: dict = {"clusters": {}, "queue_order": []}

    layout_mod.print_action_guidance(stages, meta, si, plan)

    out = capsys.readouterr().out
    assert "Triage complete" in out
    assert "desloppify next" in out
    assert "observe" not in out.lower() or "observe" not in out


def test_action_guidance_shows_observe_when_never_triaged(monkeypatch, capsys) -> None:
    """When triaged_ids is absent (never triaged), should show observe guidance."""
    monkeypatch.setattr(layout_mod, "colorize", lambda text, _style: text)
    monkeypatch.setattr(layout_mod, "triage_runner_commands", lambda only_stages=None: [("runner", "cmd")])

    stages: dict = {}
    meta: dict = {}
    si = _stub_si()
    plan: dict = {"clusters": {}, "queue_order": []}

    layout_mod.print_action_guidance(stages, meta, si, plan)

    out = capsys.readouterr().out
    assert "Triage complete" not in out
    assert "Next step" in out


def test_action_guidance_shows_retriage_when_new_issues(monkeypatch, capsys) -> None:
    """When triage completed but new issues appeared, should NOT short-circuit
    to 'complete' — should show two-paths or observe guidance."""
    monkeypatch.setattr(layout_mod, "colorize", lambda text, _style: text)
    monkeypatch.setattr(layout_mod, "triage_runner_commands", lambda only_stages=None: [("runner", "cmd")])

    stages: dict = {}
    meta = {
        "triaged_ids": ["review::aaa111"],
        "triage_stages": {},
    }
    # review::new123 is not in triaged_ids → new issue
    si = _stub_si(new_since_last={"review::new123"})
    plan: dict = {"clusters": {}, "queue_order": []}

    layout_mod.print_action_guidance(stages, meta, si, plan)

    out = capsys.readouterr().out
    assert "Triage complete" not in out


def test_action_guidance_shows_resolved_count_after_completion(monkeypatch, capsys) -> None:
    """Post-completion with only resolutions should mention resolved count."""
    monkeypatch.setattr(layout_mod, "colorize", lambda text, _style: text)

    stages: dict = {}
    meta = {
        "triaged_ids": ["review::aaa111", "review::old1", "review::old2"],
        "triage_stages": {},
    }
    si = _stub_si(resolved_since_last={"review::old1": {}, "review::old2": {}})
    plan: dict = {"clusters": {}, "queue_order": []}

    layout_mod.print_action_guidance(stages, meta, si, plan)

    out = capsys.readouterr().out
    assert "Triage complete" in out
    assert "2 issue(s) resolved" in out


def test_triage_phase_banner_reports_recovery_gap() -> None:
    plan = {
        "queue_order": [],
        "epic_triage_meta": {
            "undispositioned_issue_count": 3,
        },
    }

    banner = triage_mod.triage_phase_banner(plan, state=None)

    assert "TRIAGE RECOVERY NEEDED" in banner
    assert "3 review issue(s)" in banner
