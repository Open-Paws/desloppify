"""Direct behavior tests for review merge command flow."""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

from desloppify import state as state_mod
import desloppify.app.commands.review.merge as merge_mod


def _holistic_review_issue(
    *,
    name: str,
    summary: str,
    related_files: list[str],
    file_path: str = "src/sample.py",
    dimension: str = "api_surface_coherence",
) -> dict:
    return state_mod.make_issue(
        "review",
        file_path,
        name,
        tier=1,
        confidence="high",
        summary=summary,
        detail={
            "holistic": True,
            "dimension": dimension,
            "related_files": related_files,
            "evidence": [f"evidence::{name}"],
            "suggestion": f"suggestion::{name}",
        },
    )


def _runtime_with_state(state: dict, state_path: Path) -> SimpleNamespace:
    return SimpleNamespace(state=state, state_path=state_path)


def test_do_merge_dry_run_reports_groups_without_persisting(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    first = _holistic_review_issue(
        name="issue-a",
        summary="Command helper error contract drift",
        related_files=["desloppify/app/commands/helpers/runtime.py"],
    )
    second = _holistic_review_issue(
        name="issue-b",
        summary="Command helper failure contract drift",
        related_files=["desloppify/app/commands/helpers/runtime.py"],
    )
    state = state_mod.empty_state()
    state["work_items"] = {first["id"]: first, second["id"]: second}
    runtime = _runtime_with_state(state, tmp_path / "state.json")

    monkeypatch.setattr(merge_mod, "command_runtime", lambda _args: runtime)
    monkeypatch.setattr(merge_mod, "compute_narrative", lambda *_a, **_k: {})
    monkeypatch.setattr(merge_mod, "show_score_with_plan_context", lambda *_a, **_k: None)
    monkeypatch.setattr(merge_mod, "write_query", lambda *_a, **_k: None)
    monkeypatch.setattr(merge_mod, "save_state", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("dry-run must not save state")))

    args = argparse.Namespace(similarity=0.3, dry_run=True)
    merge_mod.do_merge(args)

    assert state["work_items"][first["id"]]["status"] == "open"
    assert state["work_items"][second["id"]]["status"] == "open"
    assert "Dry run only" in capsys.readouterr().out


def test_do_merge_marks_duplicates_and_persists_state(monkeypatch, tmp_path: Path) -> None:
    first = _holistic_review_issue(
        name="issue-a",
        summary="Resolve command helper error contract drift",
        related_files=["desloppify/app/commands/resolve/plan_load.py"],
    )
    second = _holistic_review_issue(
        name="issue-b",
        summary="Resolve command helper contract drift",
        related_files=["desloppify/app/commands/resolve/plan_load.py"],
    )
    state = state_mod.empty_state()
    state["work_items"] = {first["id"]: first, second["id"]: second}
    runtime = _runtime_with_state(state, tmp_path / "state.json")
    saved: list[tuple[dict, Path | None]] = []
    query_payloads: list[dict] = []

    monkeypatch.setattr(merge_mod, "command_runtime", lambda _args: runtime)
    monkeypatch.setattr(merge_mod, "compute_narrative", lambda *_a, **_k: {"summary": "narrative"})
    monkeypatch.setattr(merge_mod, "show_score_with_plan_context", lambda *_a, **_k: None)
    monkeypatch.setattr(
        merge_mod,
        "save_state",
        lambda st, path: saved.append((st, path)),
    )
    monkeypatch.setattr(merge_mod, "write_query", lambda payload: query_payloads.append(payload))
    monkeypatch.setattr(merge_mod, "utc_now", lambda: "2026-03-10T12:00:00+00:00")

    args = argparse.Namespace(similarity=0.3, dry_run=False)
    merge_mod.do_merge(args)

    assert saved == [(state, runtime.state_path)]
    assert query_payloads and query_payloads[0]["duplicates_merged"] == 1

    open_issues = [issue for issue in state["work_items"].values() if issue["status"] == "open"]
    auto_resolved = [
        issue for issue in state["work_items"].values() if issue["status"] == "auto_resolved"
    ]
    assert len(open_issues) == 1
    assert len(auto_resolved) == 1

    primary = open_issues[0]
    duplicate = auto_resolved[0]
    assert duplicate["note"] == f"merged into {primary['id']}"
    assert duplicate["resolution_attestation"]["kind"] == "issue_merge"
    assert primary["detail"]["merged_at"] == "2026-03-10T12:00:00+00:00"
    assert primary["detail"]["merged_from"] == [duplicate["id"]]
