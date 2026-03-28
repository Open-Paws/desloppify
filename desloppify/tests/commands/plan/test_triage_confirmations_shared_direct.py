"""Direct tests for triage confirmation shared helpers."""

from __future__ import annotations

from types import SimpleNamespace

import desloppify.app.commands.plan.triage.confirmations.shared as shared_mod


def test_ensure_stage_is_confirmable_guards_missing_and_already_confirmed(capsys) -> None:
    assert shared_mod.ensure_stage_is_confirmable({}, stage="observe") is False
    missing_out = capsys.readouterr().out
    assert "Cannot confirm: observe stage not recorded" in missing_out

    stages = {"observe": {"confirmed_at": "2026-01-01T00:00:00Z"}}
    assert shared_mod.ensure_stage_is_confirmable(stages, stage="observe") is False
    confirmed_out = capsys.readouterr().out
    assert "Observe stage already confirmed" in confirmed_out


def test_ensure_stage_is_confirmable_accepts_unconfirmed_stage() -> None:
    stages = {"observe": {"confirmed_at": None}}
    assert shared_mod.ensure_stage_is_confirmable(stages, stage="observe") is True


def test_finalize_stage_confirmation_rejects_short_attestation(capsys) -> None:
    services = SimpleNamespace(
        append_log_entry=lambda *_a, **_k: None,
        save_plan=lambda *_a, **_k: None,
    )
    ok = shared_mod.finalize_stage_confirmation(
        plan={"queue_order": []},
        stages={"observe": {}},
        request=shared_mod.StageConfirmationRequest(
            stage="observe",
            attestation="short",
            min_attestation_len=10,
            command_hint="desloppify plan triage --confirm observe ...",
            validation_stage="observe",
            validate_attestation_fn=lambda *_a, **_k: None,
            log_action="triage_confirm_observe",
            not_satisfied_hint="Re-run observe first.",
        ),
        services=services,
    )
    assert ok is False
    out = capsys.readouterr().out
    assert "Attestation too short" in out
    assert "If satisfied, confirm" in out


def test_finalize_stage_confirmation_sets_state_and_logs(monkeypatch, capsys) -> None:
    logs: list[dict] = []
    saved: list[dict] = []
    purged: list[str] = []
    monkeypatch.setattr(shared_mod, "purge_triage_stage", lambda _plan, stage: purged.append(stage))
    services = SimpleNamespace(
        append_log_entry=lambda _plan, action, **kwargs: logs.append(
            {"action": action, "kwargs": kwargs}
        ),
        save_plan=lambda plan: saved.append(plan),
    )

    stages = {"reflect": {}}
    plan = {"queue_order": ["workflow::reflect"]}
    ok = shared_mod.finalize_stage_confirmation(
        plan=plan,
        stages=stages,
        request=shared_mod.StageConfirmationRequest(
            stage="reflect",
            attestation="validated the reflect strategy and conflict resolution path",
            min_attestation_len=10,
            command_hint="desloppify plan triage --confirm reflect ...",
            validation_stage="reflect",
            validate_attestation_fn=lambda *_a, **_k: None,
            validation_kwargs={"cluster_names": ["epic/a"]},
            log_action="triage_confirm_reflect",
            log_detail={"cluster_count": 1},
        ),
        services=services,
    )

    assert ok is True
    assert stages["reflect"]["confirmed_text"].startswith("validated the reflect")
    assert "confirmed_at" in stages["reflect"]
    assert purged == ["reflect"]
    assert logs and logs[0]["action"] == "triage_confirm_reflect"
    assert saved and saved[0] is plan
    out = capsys.readouterr().out
    assert "Reflect confirmed" in out
