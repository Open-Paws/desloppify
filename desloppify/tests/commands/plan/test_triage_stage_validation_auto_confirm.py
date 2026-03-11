"""Characterization tests for triage auto-confirm helper behavior."""

from __future__ import annotations

import argparse
from types import SimpleNamespace

from desloppify.app.commands.plan.triage.validation import core as validation


def _triage_input(*, dimension: str = "naming") -> SimpleNamespace:
    return SimpleNamespace(
        open_issues={
            "review::test.py::abc12345": {
                "detail": {"dimension": dimension},
            }
        },
        resolved_issues={},
    )


def test_auto_confirm_observe_requires_attestation(capsys) -> None:
    """Observe auto-confirm blocks when attestation is missing."""
    plan = {}
    stages = {"observe": {"stage": "observe"}}

    ok = validation._auto_confirm_observe_if_attested(
        plan=plan,
        stages=stages,
        attestation=None,
        triage_input=_triage_input(),
    )

    assert ok is False
    assert "confirmed_at" not in stages["observe"]
    out = capsys.readouterr().out
    assert "Cannot reflect" in out


def test_auto_confirm_observe_records_confirmation(monkeypatch) -> None:
    """Observe auto-confirm writes confirmation fields when attestation is valid."""
    plan = {}
    stages = {"observe": {"stage": "observe"}}
    saved: list[dict] = []
    monkeypatch.setattr(validation, "save_plan", lambda p: saved.append(p))
    monkeypatch.setattr(validation, "utc_now", lambda: "2026-03-08T00:00:00Z")

    attestation = (
        "I have thoroughly reviewed the naming dimension issues and confirmed "
        "the analysis reflects the actual code evidence in this triage."
    )
    ok = validation._auto_confirm_observe_if_attested(
        plan=plan,
        stages=stages,
        attestation=attestation,
        triage_input=_triage_input(),
    )

    assert ok is True
    assert stages["observe"]["confirmed_at"] == "2026-03-08T00:00:00Z"
    assert stages["observe"]["confirmed_text"] == attestation
    assert saved == [plan]


def test_auto_confirm_reflect_for_organize_records_confirmation(monkeypatch) -> None:
    """Reflect auto-confirm validates attestation and writes confirmation fields."""
    plan = {
        "clusters": {
            "fix-naming": {
                "auto": False,
                "issue_ids": ["review::test.py::abc12345"],
            }
        }
    }
    stages = {
        "reflect": {
            "stage": "reflect",
            "report": "Cluster fix-naming handles review::test.py::abc12345 after code review.",
        }
    }
    saved: list[dict] = []

    monkeypatch.setattr(validation, "command_runtime", lambda _args: SimpleNamespace(state={}))
    monkeypatch.setattr(validation, "collect_triage_input", lambda _plan, _state: _triage_input())
    monkeypatch.setattr(validation, "detect_recurring_patterns", lambda _open, _resolved: {})
    monkeypatch.setattr(validation, "save_plan", lambda p: saved.append(p))
    monkeypatch.setattr(validation, "utc_now", lambda: "2026-03-08T00:00:00Z")

    attestation = (
        "I have thoroughly reviewed the naming dimension and the fix-naming "
        "cluster strategy is consistent with current code evidence and priorities."
    )
    ok = validation._auto_confirm_reflect_for_organize(
        args=argparse.Namespace(),
        plan=plan,
        stages=stages,
        attestation=attestation,
        deps=validation.ReflectAutoConfirmDeps(
            collect_triage_input_fn=lambda _plan, _state: _triage_input(),
        ),
    )

    assert ok is True
    assert stages["reflect"]["confirmed_at"] == "2026-03-08T00:00:00Z"
    assert stages["reflect"]["confirmed_text"] == attestation
    assert saved == [plan]


def test_auto_confirm_reflect_for_organize_blocks_incomplete_accounting(monkeypatch, capsys) -> None:
    plan = {"clusters": {}}
    stages = {
        "reflect": {
            "stage": "reflect",
            "report": "Cluster alpha handles review::test.py::abc12345 only.",
        }
    }

    monkeypatch.setattr(validation, "command_runtime", lambda _args: SimpleNamespace(state={}))
    monkeypatch.setattr(
        validation,
        "collect_triage_input",
        lambda _plan, _state: SimpleNamespace(
            open_issues={
                "review::test.py::abc12345": {"detail": {"dimension": "naming"}},
                "review::test.py::def45678": {"detail": {"dimension": "naming"}},
            },
            resolved_issues={},
        ),
    )
    monkeypatch.setattr(validation, "detect_recurring_patterns", lambda _open, _resolved: {})

    ok = validation._auto_confirm_reflect_for_organize(
        args=argparse.Namespace(),
        plan=plan,
        stages=stages,
        attestation=(
            "I have thoroughly reviewed the naming dimension and the strategy "
            "is consistent with current code evidence and priorities."
        ),
        deps=validation.ReflectAutoConfirmDeps(
            collect_triage_input_fn=lambda _plan, _state: SimpleNamespace(
                open_issues={
                    "review::test.py::abc12345": {"detail": {"dimension": "naming"}},
                    "review::test.py::def45678": {"detail": {"dimension": "naming"}},
                },
                resolved_issues={},
            ),
        ),
    )

    assert ok is False
    assert "confirmed_at" not in stages["reflect"]
    out = capsys.readouterr().out
    assert "account for every open review issue exactly once" in out
