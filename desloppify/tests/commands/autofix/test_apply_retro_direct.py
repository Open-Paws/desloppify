"""Direct tests for autofix apply_retro helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import desloppify.app.commands.autofix.apply_retro as retro_mod
from desloppify.languages._framework.base.types import FixResult


class _FakeFixer:
    detector = "unused"

    def __init__(self, entries: list[dict], results: list[dict] | FixResult):
        self._entries = entries
        self._results = results

    def detect(self, _path: Path) -> list[dict]:
        return list(self._entries)

    def fix(self, _entries: list[dict], *, dry_run: bool = False):
        assert dry_run is False
        return self._results


def _state_with_issue(issue_id: str) -> dict:
    return {
        "issues": {
            issue_id: {
                "id": issue_id,
                "status": "open",
                "note": None,
            }
        }
    }


def test_warn_uncommitted_changes_prints_git_checkpoint_hint(monkeypatch, capsys) -> None:
    monkeypatch.setattr(retro_mod.shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(
        retro_mod.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(stdout=" M app.py\n"),
    )

    retro_mod._warn_uncommitted_changes()
    out = capsys.readouterr().out
    assert "uncommitted changes" in out.lower()
    assert "pre-fix checkpoint" in out


def test_warn_uncommitted_changes_swallows_git_errors(monkeypatch) -> None:
    def _boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="git", timeout=5)

    monkeypatch.setattr(retro_mod.shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(retro_mod.subprocess, "run", _boom)
    retro_mod._warn_uncommitted_changes()


def test_cascade_unused_import_cleanup_handles_missing_fixer(capsys) -> None:
    retro_mod._cascade_unused_import_cleanup(
        Path("."),
        state={"issues": {}},
        _prev_score=0.0,
        dry_run=False,
        lang=SimpleNamespace(fixers={}),
    )
    out = capsys.readouterr().out
    assert "no unused-imports fixer" in out


def test_cascade_unused_import_cleanup_handles_no_detected_entries(capsys) -> None:
    fixer = _FakeFixer(entries=[], results=[])
    lang = SimpleNamespace(fixers={"unused-imports": fixer})

    retro_mod._cascade_unused_import_cleanup(
        Path("."),
        state={"issues": {}},
        _prev_score=0.0,
        dry_run=False,
        lang=lang,
    )
    out = capsys.readouterr().out
    assert "no orphaned imports found" in out


def test_cascade_unused_import_cleanup_resolves_cascade_issues(monkeypatch, capsys) -> None:
    monkeypatch.setattr(retro_mod, "rel", lambda value: str(value))

    results = FixResult(
        entries=[
            {
                "file": "src/a.ts",
                "removed": ["Foo"],
                "lines_removed": 2,
            }
        ]
    )
    fixer = _FakeFixer(entries=[{"file": "src/a.ts"}], results=results)
    lang = SimpleNamespace(fixers={"unused-imports": fixer})
    state = _state_with_issue("unused::src/a.ts::Foo")

    retro_mod._cascade_unused_import_cleanup(
        Path("."),
        state=state,
        _prev_score=0.0,
        dry_run=False,
        lang=lang,
    )

    issue = state["work_items"]["unused::src/a.ts::Foo"]
    assert issue["status"] == "fixed"
    assert "cascade-unused-imports" in str(issue["note"])

    out = capsys.readouterr().out
    assert "Cascade: removed 1 now-orphaned imports" in out
    assert "auto-resolved 1 import issues" in out


# -- Tests for generic fixer result shape (no "removed" key) --
# Bug found by @AugusteBalas in PR #484: generic fixers return {file, line}
# or {file, fixed} without a "removed" key, causing KeyError in the pipeline.


def test_resolve_fixer_results_handles_generic_fixer_shape() -> None:
    """Generic fixer results ({file, fixed} without 'removed') must not crash."""
    state = _state_with_issue("eslint-warning::src/a.ts::no-unused-vars")
    generic_results = [
        {"file": "src/a.ts", "fixed": True},
        {"file": "src/b.ts", "fixed": True},
    ]
    resolved = retro_mod._resolve_fixer_results(
        state, generic_results, "eslint-warning", "eslint-warning"
    )
    # No "removed" key means no symbols to match — nothing resolved, but no crash
    assert resolved == []


def test_generic_fixer_total_items_count() -> None:
    """The total_items count in cmd.py uses 'else 1' for results without 'removed'."""
    # This reproduces the exact pattern from cmd.py line 40:
    #   sum(len(r["removed"]) if "removed" in r else 1 for r in results)
    results = [
        {"file": "a.ts", "fixed": True},                          # generic: no "removed"
        {"file": "b.ts", "removed": ["x", "y"], "lines_removed": 3},  # native: has "removed"
    ]
    total = sum(len(r["removed"]) if "removed" in r else 1 for r in results)
    assert total == 3  # 1 (generic) + 2 (native)


def test_print_fix_retro_renders_skip_reason_labels(capsys) -> None:
    retro_mod._print_fix_retro(
        fixer_name="unused-vars",
        detected=6,
        fixed=4,
        resolved=3,
        skip_reasons={"rest_element": 2},
    )
    out = capsys.readouterr().out
    assert "Skip reasons (2 total)" in out
    assert "has ...rest" in out
