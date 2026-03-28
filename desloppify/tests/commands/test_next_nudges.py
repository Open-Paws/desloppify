"""Direct tests for next-part nudge rendering helpers."""

from __future__ import annotations

from types import SimpleNamespace

import desloppify.app.commands.next.render_nudges as nudges_mod


def test_render_uncommitted_reminder_prints_when_enabled(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        nudges_mod, "load_config", lambda: {"commit_tracking_enabled": True}
    )
    monkeypatch.setattr(nudges_mod, "colorize", lambda text, _style: text)

    nudges_mod.render_uncommitted_reminder(
        {"uncommitted_issues": ["issue::1", "issue::2"]}
    )

    out = capsys.readouterr().out
    assert "2 resolved issues uncommitted" in out


def test_render_single_item_resolution_hint_for_auto_fix(monkeypatch, capsys) -> None:
    monkeypatch.setattr(nudges_mod, "colorize", lambda text, _style: text)

    nudges_mod.render_single_item_resolution_hint(
        [
                {
                    "id": "smells::src/a.py::x",
                    "kind": "issue",
                    "detector": "smells",
                    "primary_command": "desloppify autofix debug-logs --dry-run",
                }
            ]
        )

    out = capsys.readouterr().out
    assert "Fix with:" in out
    assert "desloppify autofix debug-logs --dry-run" in out
    assert "desloppify plan resolve" in out


def test_render_followup_nudges_prints_subjective_summary(monkeypatch, capsys) -> None:
    monkeypatch.setattr(nudges_mod, "colorize", lambda text, _style: text)
    monkeypatch.setattr(nudges_mod, "scorecard_subjective", lambda *_args, **_kwargs: [{"stale": True}])
    monkeypatch.setattr(
        nudges_mod,
        "build_subjective_followup",
        lambda *_args, **_kwargs: SimpleNamespace(
            low_assessed=["naming_quality"],
            integrity_lines=[("yellow", "integrity check")],
        ),
    )
    monkeypatch.setattr(
        nudges_mod, "unassessed_subjective_dimensions", lambda *_args, **_kwargs: ["logic_clarity"]
    )
    monkeypatch.setattr(
        nudges_mod, "subjective_coverage_breakdown", lambda *_args, **_kwargs: (2, [], [])
    )

    nudges_mod.render_followup_nudges(
        state={},
        dim_scores={},
        issues_scoped={"review::x": {"status": "open", "detector": "review"}},
        strict_score=90.0,
        target_strict_score=95.0,
        queue_total=0,
    )

    out = capsys.readouterr().out
    assert "North star: strict 90.0/100" in out
    assert "integrity check" in out
    assert "Subjective:" in out
    assert "below target" in out
    assert "stale" in out
    assert "unassessed" in out
    assert "need review" in out
