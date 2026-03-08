"""Attestation and confirmation handlers for plan triage."""

from __future__ import annotations

import argparse

from .confirmations_enrich import confirm_enrich as _confirm_enrich_impl
from .confirmations_enrich import confirm_sense_check as _confirm_sense_check_impl
from .confirmations_organize import confirm_organize as _confirm_organize_impl
from .confirmations_basic import MIN_ATTESTATION_LEN as _MIN_ATTESTATION_LEN
from .confirmations_basic import confirm_observe as _confirm_observe_impl
from .confirmations_basic import confirm_reflect as _confirm_reflect_impl
from .confirmations_basic import validate_attestation as _validate_attestation
from .helpers import (
    count_log_activity_since,
    observe_dimension_breakdown,
    open_review_ids_from_state,
    purge_triage_stage,
    triage_coverage,
)
from .services import TriageServices, default_triage_services
from .display import show_plan_summary


def _confirm_observe(
    args: argparse.Namespace,
    plan: dict,
    stages: dict,
    attestation: str | None,
    *,
    services: TriageServices | None = None,
) -> None:
    _confirm_observe_impl(args, plan, stages, attestation, services=services)


def _confirm_reflect(
    args: argparse.Namespace,
    plan: dict,
    stages: dict,
    attestation: str | None,
    *,
    services: TriageServices | None = None,
) -> None:
    _confirm_reflect_impl(args, plan, stages, attestation, services=services)


def _confirm_organize(
    args: argparse.Namespace,
    plan: dict,
    stages: dict,
    attestation: str | None,
    *,
    services: TriageServices | None = None,
) -> None:
    _confirm_organize_impl(args, plan, stages, attestation, services=services)


def _confirm_enrich(
    args: argparse.Namespace,
    plan: dict,
    stages: dict,
    attestation: str | None,
    *,
    services: TriageServices | None = None,
) -> None:
    _confirm_enrich_impl(args, plan, stages, attestation, services=services)


def _confirm_sense_check(
    args: argparse.Namespace,
    plan: dict,
    stages: dict,
    attestation: str | None,
    *,
    services: TriageServices | None = None,
) -> None:
    _confirm_sense_check_impl(args, plan, stages, attestation, services=services)


def _cmd_confirm_stage(
    args: argparse.Namespace,
    *,
    services: TriageServices | None = None,
) -> None:
    """Router for ``--confirm observe/reflect/organize/enrich/sense-check``."""
    resolved_services = services or default_triage_services()
    confirm_stage = getattr(args, "confirm", None)
    attestation = getattr(args, "attestation", None)
    plan = resolved_services.load_plan()
    meta = plan.get("epic_triage_meta", {})
    stages = meta.get("triage_stages", {})

    if confirm_stage == "observe":
        _confirm_observe(args, plan, stages, attestation, services=resolved_services)
    elif confirm_stage == "reflect":
        _confirm_reflect(args, plan, stages, attestation, services=resolved_services)
    elif confirm_stage == "organize":
        _confirm_organize(args, plan, stages, attestation, services=resolved_services)
    elif confirm_stage == "enrich":
        _confirm_enrich(args, plan, stages, attestation, services=resolved_services)
    elif confirm_stage == "sense-check":
        _confirm_sense_check(args, plan, stages, attestation, services=resolved_services)


MIN_ATTESTATION_LEN = _MIN_ATTESTATION_LEN
validate_attestation = _validate_attestation


def cmd_confirm_stage(
    args: argparse.Namespace,
    *,
    services: TriageServices | None = None,
) -> None:
    """Public triage confirmation entrypoint."""
    _cmd_confirm_stage(args, services=services)


__all__ = [
    "MIN_ATTESTATION_LEN",
    "cmd_confirm_stage",
    "validate_attestation",
    "_MIN_ATTESTATION_LEN",
    "_cmd_confirm_stage",
    "_confirm_enrich",
    "_confirm_observe",
    "_confirm_organize",
    "_confirm_reflect",
    "_confirm_sense_check",
    "_validate_attestation",
]
