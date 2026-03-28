"""Regression tests for issue #181: subjective nudges gated on objective backlog.

When the objective queue is non-empty, subjective refresh commands are
suppressed entirely — the queue already surfaces them when actionable.
When the objective queue is empty, actionable commands appear normally.
Integrity warnings always render regardless of backlog.
"""

from __future__ import annotations

from types import SimpleNamespace

from desloppify.app.commands.helpers import subjective as subjective_mod
from desloppify.app.commands.status import render as status_render

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_followup(**overrides):
    payload = {
        "low_assessed": True,
        "threshold_label": "95",
        "rendered": "dim_a, dim_b",
        "command": "desloppify review --prepare --dimensions dim_a",
        "integrity_lines": [],
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _subjective_entry(dimension_key: str, *, stale: bool = False, score: float = 80.0):
    return {
        "name": dimension_key.replace("_", " ").title(),
        "dimension_key": dimension_key,
        "score": score,
        "strict": score,
        "stale": stale,
        "placeholder": False,
    }


# ---------------------------------------------------------------------------
# print_subjective_followup — suppressed vs actionable
# ---------------------------------------------------------------------------

class TestPrintSubjectiveFollowup:
    """Test the shared subjective followup renderer."""

    def test_actionable_when_no_backlog(self, monkeypatch, capsys):
        monkeypatch.setattr(subjective_mod, "colorize", lambda text, _s: text)
        followup = _make_followup()
        subjective_mod.print_subjective_followup(followup, objective_backlog=0)
        out = capsys.readouterr().out
        assert "Next command to improve subjective scores" in out

    def test_suppressed_when_backlog_exists(self, monkeypatch, capsys):
        monkeypatch.setattr(subjective_mod, "colorize", lambda text, _s: text)
        followup = _make_followup()
        subjective_mod.print_subjective_followup(followup, objective_backlog=100)
        out = capsys.readouterr().out
        assert "Next command to improve subjective scores" not in out
        assert "Subjective quality" not in out

    def test_integrity_lines_always_shown(self, monkeypatch, capsys):
        """Integrity warnings must appear regardless of backlog."""
        monkeypatch.setattr(subjective_mod, "colorize", lambda text, _s: text)
        followup = _make_followup(
            low_assessed=False,
            integrity_lines=[("yellow", "Integrity alert: check review coverage")],
        )
        subjective_mod.print_subjective_followup(followup, objective_backlog=500)
        out = capsys.readouterr().out
        assert "Integrity alert" in out

    def test_default_backlog_zero_backward_compat(self, monkeypatch, capsys):
        """Calling without objective_backlog should behave as before (actionable)."""
        monkeypatch.setattr(subjective_mod, "colorize", lambda text, _s: text)
        followup = _make_followup()
        subjective_mod.print_subjective_followup(followup)
        out = capsys.readouterr().out
        assert "Next command to improve subjective scores" in out


# ---------------------------------------------------------------------------
# _render_dimension_legend — stale commands gated
# ---------------------------------------------------------------------------

class TestRenderDimensionLegend:
    """Test the stale-dimension legend in the status dimension table."""

    def test_stale_command_shown_when_no_backlog(self, monkeypatch, capsys):
        monkeypatch.setattr(status_render, "colorize", lambda text, _s: text)
        entries = [_subjective_entry("design_coherence", stale=True)]
        status_render._render_dimension_legend(entries, objective_backlog=0)
        out = capsys.readouterr().out
        assert "force-review-rerun" in out

    def test_stale_tag_only_when_backlog_exists(self, monkeypatch, capsys):
        monkeypatch.setattr(status_render, "colorize", lambda text, _s: text)
        entries = [_subjective_entry("design_coherence", stale=True)]
        status_render._render_dimension_legend(entries, objective_backlog=1900)
        out = capsys.readouterr().out
        # Tag explanation present
        assert "[stale] = assessment outdated" in out
        # No actionable rerun command
        assert "force-review-rerun" not in out

    def test_no_stale_no_stale_output(self, monkeypatch, capsys):
        monkeypatch.setattr(status_render, "colorize", lambda text, _s: text)
        entries = [_subjective_entry("design_coherence", stale=False)]
        status_render._render_dimension_legend(entries, objective_backlog=0)
        out = capsys.readouterr().out
        assert "[stale]" not in out
        # Legend lines still present
        assert "Health = open penalized" in out

    def test_multiple_stale_command_shown_when_clear(self, monkeypatch, capsys):
        monkeypatch.setattr(status_render, "colorize", lambda text, _s: text)
        entries = [
            _subjective_entry("design_coherence", stale=True),
            _subjective_entry("naming_quality", stale=True),
        ]
        status_render._render_dimension_legend(entries, objective_backlog=0)
        out = capsys.readouterr().out
        assert "2 stale dimensions" in out
        assert "force-review-rerun" in out

    def test_multiple_stale_no_command_when_backlog(self, monkeypatch, capsys):
        monkeypatch.setattr(status_render, "colorize", lambda text, _s: text)
        entries = [
            _subjective_entry("design_coherence", stale=True),
            _subjective_entry("naming_quality", stale=True),
        ]
        status_render._render_dimension_legend(entries, objective_backlog=50)
        out = capsys.readouterr().out
        assert "[stale] = assessment outdated" in out
        assert "force-review-rerun" not in out
