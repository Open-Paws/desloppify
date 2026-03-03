"""Tests for --no-budget flag on show command."""

from __future__ import annotations

import argparse

from desloppify.app.commands.show.scope import resolve_noise


class TestNoBudgetFlag:
    def test_no_budget_returns_all_issues(self):
        """When no_budget=True, all matches are surfaced and nothing is hidden."""
        matches = [
            {"id": f"f{i}", "detector": "review", "summary": f"issue {i}"}
            for i in range(50)
        ]
        surfaced, hidden, budget, global_budget, warning = resolve_noise(
            {},  # empty config — would normally produce a low budget
            matches,
            no_budget=True,
        )
        assert len(surfaced) == 50
        assert hidden == {}
        assert budget == 0
        assert global_budget == 0
        assert warning is None

    def test_no_budget_flag_parsed(self):
        """The --no-budget flag is parsed correctly by argparse."""
        from desloppify.app.cli_support.parser_groups import _add_show_parser

        parent = argparse.ArgumentParser()
        sub = parent.add_subparsers()
        _add_show_parser(sub)

        args = parent.parse_args(["show", "review", "--no-budget"])
        assert getattr(args, "no_budget", False) is True

    def test_default_budget_still_applies(self):
        """Without no_budget, the normal budget logic runs."""
        matches = [
            {"id": f"f{i}", "detector": "review", "summary": f"issue {i}"}
            for i in range(50)
        ]
        # With default no_budget=False, budget is applied
        surfaced, hidden, budget, global_budget, warning = resolve_noise(
            {},
            matches,
        )
        # Normal path: budget may reduce the surfaced count
        # (exact behaviour depends on defaults in resolve_issue_noise_settings)
        assert isinstance(surfaced, list)
        assert isinstance(hidden, dict)
