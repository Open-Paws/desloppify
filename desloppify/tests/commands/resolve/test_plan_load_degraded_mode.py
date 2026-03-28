"""Tests for resolve degraded-mode behavior when plan loading fails."""

from __future__ import annotations

from unittest.mock import MagicMock

import desloppify.app.commands.resolve.apply as apply_mod
import desloppify.app.commands.resolve.plan_load as plan_load_mod
import desloppify.app.commands.resolve.queue_guard as queue_guard_mod


def test_try_expand_cluster_warns_when_plan_load_is_degraded(monkeypatch) -> None:
    monkeypatch.setattr(
        apply_mod,
        "load_resolve_plan_access",
        lambda: plan_load_mod.ResolvePlanAccess(
            plan=None,
            degraded=True,
            error_kind="JSONDecodeError",
            warning_state=plan_load_mod.DegradedPlanWarningState(),
        ),
    )
    warn = MagicMock()
    monkeypatch.setattr(plan_load_mod, "warn_plan_load_degraded_once", warn)

    assert apply_mod._try_expand_cluster("cluster-a") is None
    warn.assert_called_once()
    kwargs = warn.call_args.kwargs
    assert kwargs["error_kind"] == "JSONDecodeError"
    assert "Cluster-name pattern expansion is disabled" in kwargs["behavior"]


def test_queue_order_guard_warns_when_plan_load_is_degraded(monkeypatch) -> None:
    monkeypatch.setattr(
        queue_guard_mod,
        "load_resolve_plan_access",
        lambda: plan_load_mod.ResolvePlanAccess(
            plan=None,
            degraded=True,
            error_kind="OSError",
            warning_state=plan_load_mod.DegradedPlanWarningState(),
        ),
    )
    warn = MagicMock()
    monkeypatch.setattr(plan_load_mod, "warn_plan_load_degraded_once", warn)

    blocked = queue_guard_mod._check_queue_order_guard(
        state={"issues": {}},
        patterns=["smells::src/app.py::x"],
        status="fixed",
    )
    assert blocked is False
    warn.assert_called_once()
    kwargs = warn.call_args.kwargs
    assert kwargs["error_kind"] == "OSError"
    assert "Queue-order enforcement is disabled" in kwargs["behavior"]


def test_shared_plan_access_warns_once_across_resolve_helpers(capsys) -> None:
    access = plan_load_mod.ResolvePlanAccess(
        plan=None,
        degraded=True,
        error_kind="RuntimeError",
        warning_state=plan_load_mod.DegradedPlanWarningState(),
    )

    assert apply_mod._try_expand_cluster("cluster-a", plan_access=access) is None
    assert (
        queue_guard_mod._check_queue_order_guard(
            state={"issues": {}},
            patterns=["review::a"],
            status="fixed",
            plan_access=access,
            )
            is False
        )
    err = capsys.readouterr().err
    assert err.count("Warning: resolve is running in degraded mode") == 1


def test_plan_load_warning_prints_once(capsys) -> None:
    warning_state = plan_load_mod.DegradedPlanWarningState()
    plan_load_mod.warn_plan_load_degraded_once(
        error_kind="RuntimeError",
        behavior="Queue-order enforcement is disabled until recovery.",
        warning_state=warning_state,
    )
    plan_load_mod.warn_plan_load_degraded_once(
        error_kind="RuntimeError",
        behavior="Cluster expansion is disabled until recovery.",
        warning_state=warning_state,
    )
    err = capsys.readouterr().err
    assert err.count("Warning: resolve is running in degraded mode") == 1
    assert "Queue-order enforcement is disabled until recovery." in err


def test_plan_load_warning_dedupe_does_not_leak_across_attempts(capsys) -> None:
    plan_load_mod.warn_plan_load_degraded_once(
        error_kind="RuntimeError",
        behavior="Queue-order enforcement is disabled until recovery.",
        warning_state=plan_load_mod.DegradedPlanWarningState(),
    )
    plan_load_mod.warn_plan_load_degraded_once(
        error_kind="RuntimeError",
        behavior="Cluster expansion is disabled until recovery.",
        warning_state=plan_load_mod.DegradedPlanWarningState(),
    )
    err = capsys.readouterr().err
    assert err.count("Warning: resolve is running in degraded mode") == 2
