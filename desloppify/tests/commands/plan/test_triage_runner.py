"""Tests for triage runner: stage prompts, validation, and orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from desloppify.app.commands.plan.triage.runner.stage_prompts import build_stage_prompt
from desloppify.app.commands.plan.triage.runner.stage_validation import (
    build_auto_attestation,
    validate_completion,
    validate_stage,
)
from desloppify.engine._plan.epic_triage_prompt import TriageInput


def _make_triage_input(n_issues: int = 5) -> TriageInput:
    """Create a minimal TriageInput for testing."""
    issues = {}
    for i in range(n_issues):
        fid = f"review::src/foo{i}.ts::issue_{i}::abcd{i:04d}"
        issues[fid] = {
            "status": "open",
            "detector": "review",
            "file": f"src/foo{i}.ts",
            "summary": f"Issue {i} summary",
            "detail": {"dimension": f"dim_{i % 3}", "suggestion": "Fix it"},
        }
    return TriageInput(
        open_issues=issues,
        mechanical_issues={},
        existing_epics={},
        dimension_scores={"dim_0": {"score": 70, "strict": 65, "failing": 2}},
        new_since_last=set(),
        resolved_since_last=set(),
        previously_dismissed=[],
        triage_version=1,
        resolved_issues={},
        completed_clusters=[],
    )


# ---------- Stage prompts ----------


def test_build_observe_prompt(tmp_path: Path) -> None:
    si = _make_triage_input()
    prompt = build_stage_prompt("observe", si, {}, repo_root=tmp_path)
    assert "OBSERVE" in prompt
    assert "desloppify plan triage --stage observe" in prompt
    assert "src/foo0.ts" in prompt  # issue data included


def test_build_reflect_prompt_includes_prior(tmp_path: Path) -> None:
    si = _make_triage_input()
    prior = {"observe": "My observation report about themes and root causes."}
    prompt = build_stage_prompt("reflect", si, prior, repo_root=tmp_path)
    assert "REFLECT" in prompt
    assert "My observation report" in prompt


def test_build_organize_prompt(tmp_path: Path) -> None:
    si = _make_triage_input()
    prior = {"observe": "obs", "reflect": "ref"}
    prompt = build_stage_prompt("organize", si, prior, repo_root=tmp_path)
    assert "ORGANIZE" in prompt
    assert "desloppify plan cluster create" in prompt
    assert "--depends-on" in prompt
    assert "--effort" in prompt


def test_build_enrich_prompt(tmp_path: Path) -> None:
    si = _make_triage_input()
    prior = {"observe": "obs", "reflect": "ref", "organize": "org"}
    prompt = build_stage_prompt("enrich", si, prior, repo_root=tmp_path)
    assert "ENRICH" in prompt
    assert "--issue-refs" in prompt
    assert "exist on disk" in prompt


# ---------- Stage validation ----------


def _plan_with_stages(**kwargs: dict) -> dict:
    """Create a plan with triage stages."""
    return {
        "epic_triage_meta": {
            "triage_stages": kwargs,
        },
        "clusters": {},
        "queue_order": [],
    }


def test_validate_observe_missing(tmp_path: Path) -> None:
    plan = _plan_with_stages()
    ok, msg = validate_stage("observe", plan, {}, tmp_path)
    assert not ok
    assert "not recorded" in msg


def test_validate_observe_short_report(tmp_path: Path) -> None:
    plan = _plan_with_stages(observe={"report": "too short"})
    ok, msg = validate_stage("observe", plan, {}, tmp_path)
    assert not ok
    assert "too short" in msg


def test_validate_observe_ok(tmp_path: Path) -> None:
    plan = _plan_with_stages(observe={"report": "x" * 150, "cited_ids": ["a", "b", "c", "d", "e"], "issue_count": 10})
    ok, msg = validate_stage("observe", plan, {}, tmp_path)
    assert ok


def test_validate_observe_low_citations(tmp_path: Path) -> None:
    """Observe with too few issue citations should fail."""
    plan = _plan_with_stages(observe={"report": "x" * 150, "cited_ids": ["a"], "issue_count": 50})
    ok, msg = validate_stage("observe", plan, {}, tmp_path)
    assert not ok
    assert "cites only" in msg


def test_validate_organize_no_clusters(tmp_path: Path) -> None:
    plan = _plan_with_stages(organize={"report": "x" * 150})
    ok, msg = validate_stage("organize", plan, {}, tmp_path)
    assert not ok
    assert "No manual clusters" in msg


def test_validate_enrich_bad_paths(tmp_path: Path) -> None:
    plan = _plan_with_stages(enrich={"report": "x" * 150})
    plan["clusters"] = {
        "test-cluster": {
            "issue_ids": ["review::a::b"],
            "description": "test",
            "action_steps": [
                {"title": "fix", "detail": "Update src/nonexistent.ts and fix the imports. " + "x" * 40, "effort": "small", "issue_refs": ["review::a::b"]}
            ],
        }
    }
    ok, msg = validate_stage("enrich", plan, {}, tmp_path)
    assert not ok
    assert "file path" in msg


def test_validate_enrich_missing_effort(tmp_path: Path) -> None:
    """Enrich should block on missing effort tags."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.ts").write_text("export {}")
    plan = _plan_with_stages(enrich={"report": "x" * 150})
    plan["clusters"] = {
        "test-cluster": {
            "issue_ids": ["review::a::b"],
            "description": "test",
            "action_steps": [
                {"title": "fix", "detail": "Update src/foo.ts to remove dead code and fix the pattern. " + "x" * 30, "issue_refs": ["review::a::b"]}
            ],
        }
    }
    ok, msg = validate_stage("enrich", plan, {}, tmp_path)
    assert not ok
    assert "effort" in msg


def test_validate_enrich_missing_issue_refs(tmp_path: Path) -> None:
    """Enrich should block on missing issue_refs."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.ts").write_text("export {}")
    plan = _plan_with_stages(enrich={"report": "x" * 150})
    plan["clusters"] = {
        "test-cluster": {
            "issue_ids": ["review::a::b"],
            "description": "test",
            "action_steps": [
                {"title": "fix", "detail": "Update src/foo.ts to remove dead code and fix the pattern. " + "x" * 30, "effort": "small"}
            ],
        }
    }
    ok, msg = validate_stage("enrich", plan, {}, tmp_path)
    assert not ok
    assert "issue_refs" in msg


def test_validate_enrich_vague_detail(tmp_path: Path) -> None:
    """Enrich should block on steps with vague detail (short, no paths)."""
    plan = _plan_with_stages(enrich={"report": "x" * 150})
    plan["clusters"] = {
        "test-cluster": {
            "issue_ids": ["review::a::b"],
            "description": "test",
            "action_steps": [
                {"title": "fix", "detail": "Fix the thing", "effort": "small", "issue_refs": ["review::a::b"]}
            ],
        }
    }
    ok, msg = validate_stage("enrich", plan, {}, tmp_path)
    assert not ok
    assert "vague" in msg


# ---------- Auto attestation ----------


def test_auto_attestation_observe() -> None:
    si = _make_triage_input()
    plan = {}
    att = build_auto_attestation("observe", plan, si)
    assert len(att) >= 80
    assert "dim_" in att


def test_auto_attestation_organize() -> None:
    si = _make_triage_input()
    plan = {
        "clusters": {
            "fix-naming": {"issue_ids": ["review::a::b"]},
        }
    }
    att = build_auto_attestation("organize", plan, si)
    assert len(att) >= 80
    assert "fix-naming" in att


# ---------- Completion validation ----------


def test_validate_completion_missing_stages(tmp_path: Path) -> None:
    plan = _plan_with_stages(observe={"report": "x" * 150, "confirmed_at": "2024-01-01"})
    ok, msg = validate_completion(plan, {}, tmp_path)
    assert not ok
    assert "reflect" in msg


def test_validate_completion_self_dependency(tmp_path: Path) -> None:
    plan = _plan_with_stages(
        observe={"report": "x" * 150, "confirmed_at": "t"},
        reflect={"report": "x" * 150, "confirmed_at": "t"},
        organize={"report": "x" * 150, "confirmed_at": "t"},
        enrich={"report": "x" * 150, "confirmed_at": "t"},
    )
    plan["clusters"] = {
        "self-dep": {
            "issue_ids": ["review::a::b"],
            "description": "test",
            "action_steps": [{"title": "fix", "detail": "d", "issue_refs": ["review::a::b"]}],
            "depends_on_clusters": ["self-dep"],
        }
    }
    ok, msg = validate_completion(plan, {"issues": {"review::a::b": {"status": "open", "detector": "review"}}}, tmp_path)
    assert not ok
    assert "depends on itself" in msg
