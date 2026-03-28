"""Tests for the unified SubjectiveVisibility policy."""

from __future__ import annotations

from desloppify.engine._plan.policy.subjective import (
    SubjectiveVisibility,
    compute_subjective_visibility,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue(fid: str, detector: str = "unused", status: str = "open",
             suppressed: bool = False) -> dict:
    f: dict = {"id": fid, "detector": detector, "status": status}
    if suppressed:
        f["suppressed"] = True
    return f


def _state_with_issues(*issues: dict) -> dict:
    return {
        "issues": {f["id"]: f for f in issues},
        "scan_count": 5,
    }


def _unscored_state(*dim_keys: str) -> dict:
    dim_scores: dict = {}
    assessments: dict = {}
    for dk in dim_keys:
        dim_scores[dk] = {
            "score": 0, "strict": 0, "checks": 1, "failing": 0,
            "detectors": {
                "subjective_assessment": {"dimension_key": dk, "placeholder": True},
            },
        }
        assessments[dk] = {"score": 0.0, "placeholder": True}
    return {
        "issues": {},
        "scan_count": 1,
        "dimension_scores": dim_scores,
        "subjective_assessments": assessments,
    }


def _stale_state(*dim_keys: str, score: float = 50.0) -> dict:
    dim_scores: dict = {}
    assessments: dict = {}
    for dk in dim_keys:
        dim_scores[dk] = {
            "score": score, "strict": score, "checks": 1, "failing": 0,
            "detectors": {
                "subjective_assessment": {"dimension_key": dk, "placeholder": False},
            },
        }
        assessments[dk] = {
            "score": score,
            "needs_review_refresh": True,
            "stale_since": "2025-01-01T00:00:00+00:00",
        }
    return {
        "issues": {},
        "scan_count": 5,
        "dimension_scores": dim_scores,
        "subjective_assessments": assessments,
    }


def _under_target_state(*dim_keys: str, score: float = 70.0) -> dict:
    dim_scores: dict = {}
    assessments: dict = {}
    for dk in dim_keys:
        dim_scores[dk] = {
            "score": score, "strict": score, "checks": 1, "failing": 0,
            "detectors": {
                "subjective_assessment": {"dimension_key": dk, "placeholder": False},
            },
        }
        assessments[dk] = {"score": score}
    return {
        "issues": {},
        "scan_count": 5,
        "dimension_scores": dim_scores,
        "subjective_assessments": assessments,
    }


# ---------------------------------------------------------------------------
# Factory: basic counting
# ---------------------------------------------------------------------------

def test_empty_state_has_no_backlog():
    policy = compute_subjective_visibility({})
    assert policy.has_objective_backlog is False
    assert policy.objective_count == 0
    assert policy.unscored_ids == frozenset()
    assert policy.stale_ids == frozenset()
    assert policy.under_target_ids == frozenset()


def test_objective_issues_counted():
    state = _state_with_issues(
        _issue("u1", "unused"),
        _issue("u2", "unused"),
        _issue("r1", "review"),  # non-objective
    )
    policy = compute_subjective_visibility(
        state,
        plan={"queue_order": ["u1", "u2", "r1"], "skipped": {}},
    )
    assert policy.has_objective_backlog is True
    assert policy.objective_count == 2


def test_suppressed_issues_excluded():
    state = _state_with_issues(
        _issue("u1", "unused", suppressed=True),
    )
    policy = compute_subjective_visibility(
        state,
        plan={"queue_order": ["u1"], "skipped": {}},
    )
    assert policy.has_objective_backlog is False
    assert policy.objective_count == 0


def test_closed_issues_excluded():
    state = _state_with_issues(
        _issue("u1", "unused", status="resolved"),
    )
    policy = compute_subjective_visibility(
        state,
        plan={"queue_order": ["u1"], "skipped": {}},
    )
    assert policy.has_objective_backlog is False


def test_non_objective_detectors_excluded():
    state = _state_with_issues(
        _issue("r1", "review"),
        _issue("c1", "concerns"),
        _issue("sr1", "subjective_review"),
        _issue("sa1", "subjective_assessment"),
    )
    policy = compute_subjective_visibility(
        state,
        plan={"queue_order": ["r1", "c1", "sr1", "sa1"], "skipped": {}},
    )
    assert policy.has_objective_backlog is False
    assert policy.objective_count == 0


# ---------------------------------------------------------------------------
# Factory: subjective ID sets
# ---------------------------------------------------------------------------

def test_unscored_ids_populated():
    state = _unscored_state("design_coherence", "error_consistency")
    policy = compute_subjective_visibility(state)
    assert "subjective::design_coherence" in policy.unscored_ids
    assert "subjective::error_consistency" in policy.unscored_ids


def test_stale_ids_populated():
    state = _stale_state("design_coherence")
    policy = compute_subjective_visibility(state)
    assert "subjective::design_coherence" in policy.stale_ids


def test_under_target_ids_populated():
    state = _under_target_state("design_coherence", score=70.0)
    policy = compute_subjective_visibility(state, target_strict=95.0)
    assert "subjective::design_coherence" in policy.under_target_ids


# ---------------------------------------------------------------------------
# should_inject_to_plan / should_evict_from_plan
# ---------------------------------------------------------------------------

def test_inject_unscored_always():
    policy = SubjectiveVisibility(
        has_objective_backlog=True,
        objective_count=5,
        unscored_ids=frozenset({"subjective::foo"}),
        stale_ids=frozenset(),
        under_target_ids=frozenset(),
    )
    assert policy.should_inject_to_plan("subjective::foo") is True
    assert policy.should_evict_from_plan("subjective::foo") is False


def test_inject_stale_only_when_drained():
    with_backlog = SubjectiveVisibility(
        has_objective_backlog=True, objective_count=3,
        unscored_ids=frozenset(), stale_ids=frozenset({"subjective::bar"}),
        under_target_ids=frozenset(),
    )
    assert with_backlog.should_inject_to_plan("subjective::bar") is False
    assert with_backlog.should_evict_from_plan("subjective::bar") is True

    without_backlog = SubjectiveVisibility(
        has_objective_backlog=False, objective_count=0,
        unscored_ids=frozenset(), stale_ids=frozenset({"subjective::bar"}),
        under_target_ids=frozenset(),
    )
    assert without_backlog.should_inject_to_plan("subjective::bar") is True
    assert without_backlog.should_evict_from_plan("subjective::bar") is False


def test_inject_under_target_only_when_drained():
    with_backlog = SubjectiveVisibility(
        has_objective_backlog=True, objective_count=3,
        unscored_ids=frozenset(), stale_ids=frozenset(),
        under_target_ids=frozenset({"subjective::baz"}),
    )
    assert with_backlog.should_inject_to_plan("subjective::baz") is False
    assert with_backlog.should_evict_from_plan("subjective::baz") is True

    without_backlog = SubjectiveVisibility(
        has_objective_backlog=False, objective_count=0,
        unscored_ids=frozenset(), stale_ids=frozenset(),
        under_target_ids=frozenset({"subjective::baz"}),
    )
    assert without_backlog.should_inject_to_plan("subjective::baz") is True
    assert without_backlog.should_evict_from_plan("subjective::baz") is False


def test_unknown_id_never_injected_or_evicted():
    policy = SubjectiveVisibility(
        has_objective_backlog=True, objective_count=3,
        unscored_ids=frozenset(), stale_ids=frozenset(),
        under_target_ids=frozenset(),
    )
    assert policy.should_inject_to_plan("subjective::unknown") is False
    assert policy.should_evict_from_plan("subjective::unknown") is False


# ---------------------------------------------------------------------------
# backlog_blocks_rerun
# ---------------------------------------------------------------------------

def test_backlog_blocks_rerun():
    with_backlog = SubjectiveVisibility(
        has_objective_backlog=True, objective_count=3,
        unscored_ids=frozenset(), stale_ids=frozenset(),
        under_target_ids=frozenset(),
    )
    assert with_backlog.backlog_blocks_rerun is True

    without_backlog = SubjectiveVisibility(
        has_objective_backlog=False, objective_count=0,
        unscored_ids=frozenset(), stale_ids=frozenset(),
        under_target_ids=frozenset(),
    )
    assert without_backlog.backlog_blocks_rerun is False


# ---------------------------------------------------------------------------
# sync_dimensions does not re-export subjective policy internals
# ---------------------------------------------------------------------------

def test_non_objective_detectors_not_reexported_from_sync_dimensions():
    import desloppify.engine._plan.sync.dimensions as sync_mod

    assert not hasattr(sync_mod, "NON_OBJECTIVE_DETECTORS")


# ---------------------------------------------------------------------------
# Frozen dataclass
# ---------------------------------------------------------------------------

def test_policy_is_frozen():
    import dataclasses
    policy = SubjectiveVisibility(
        has_objective_backlog=False, objective_count=0,
        unscored_ids=frozenset(), stale_ids=frozenset(),
        under_target_ids=frozenset(),
    )
    assert dataclasses.is_dataclass(policy)
    try:
        policy.objective_count = 99  # type: ignore[misc]
        raise AssertionError("Should be frozen")
    except (AttributeError, dataclasses.FrozenInstanceError):
        pass
