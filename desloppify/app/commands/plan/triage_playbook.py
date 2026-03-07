"""Shared triage workflow labels and canonical command snippets."""

from __future__ import annotations

TRIAGE_STAGE_LABELS: tuple[tuple[str, str], ...] = (
    ("observe", "Analyse issues & spot contradictions"),
    ("reflect", "Form strategy & present to user"),
    ("organize", "Defer contradictions, cluster, & prioritize"),
    ("enrich", "Make steps executor-ready (detail, refs)"),
    ("commit", "Write strategy & confirm"),
)

TRIAGE_STAGE_DEPENDENCIES: dict[str, set[str]] = {
    "observe": set(),
    "reflect": {"observe"},
    "organize": {"reflect"},
    "enrich": {"organize"},
    "commit": {"enrich"},
}

TRIAGE_CMD_OBSERVE = (
    'desloppify plan triage --stage observe --report '
    '"analysis of themes and root causes..."'
)
TRIAGE_CMD_REFLECT = (
    'desloppify plan triage --stage reflect --report '
    '"comparison against completed work..."'
)
TRIAGE_CMD_ORGANIZE = (
    'desloppify plan triage --stage organize --report '
    '"summary of organization and priorities..."'
)
TRIAGE_CMD_ENRICH = (
    'desloppify plan triage --stage enrich --report '
    '"summary of enrichment work done..."'
)
TRIAGE_CMD_COMPLETE = (
    'desloppify plan triage --complete --strategy "execution plan..."'
)
TRIAGE_CMD_COMPLETE_VERBOSE = (
    "desloppify plan triage --complete --strategy "
    '"execution plan with priorities and verification..."'
)
TRIAGE_CMD_CONFIRM_EXISTING = (
    'desloppify plan triage --confirm-existing --note "..." --strategy "..."'
)
TRIAGE_CMD_CLUSTER_CREATE = (
    'desloppify plan cluster create <name> --description "..."'
)
TRIAGE_CMD_CLUSTER_ADD = "desloppify plan cluster add <name> <issue-patterns>"
TRIAGE_CMD_CLUSTER_ENRICH = (
    'desloppify plan cluster update <name> --description "..." --steps '
    '"step 1" "step 2"'
)
TRIAGE_CMD_CLUSTER_ENRICH_COMPACT = (
    'desloppify plan cluster update <name> --description "..." --steps '
    '"step1" "step2"'
)
TRIAGE_CMD_CLUSTER_STEPS = (
    'desloppify plan cluster update <name> --steps "step 1" "step 2"'
)

__all__ = [
    "TRIAGE_STAGE_DEPENDENCIES",
    "TRIAGE_STAGE_LABELS",
    "TRIAGE_CMD_CLUSTER_ADD",
    "TRIAGE_CMD_CLUSTER_CREATE",
    "TRIAGE_CMD_CLUSTER_ENRICH",
    "TRIAGE_CMD_CLUSTER_ENRICH_COMPACT",
    "TRIAGE_CMD_CLUSTER_STEPS",
    "TRIAGE_CMD_COMPLETE",
    "TRIAGE_CMD_COMPLETE_VERBOSE",
    "TRIAGE_CMD_CONFIRM_EXISTING",
    "TRIAGE_CMD_ENRICH",
    "TRIAGE_CMD_OBSERVE",
    "TRIAGE_CMD_ORGANIZE",
    "TRIAGE_CMD_REFLECT",
]
