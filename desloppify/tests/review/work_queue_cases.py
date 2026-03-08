"""Tests for shared queue selection in desloppify.work_queue."""

from __future__ import annotations

from desloppify.engine._work_queue.core import QueueBuildOptions
from desloppify.engine._work_queue.core import build_work_queue as _build_work_queue


def build_work_queue(state, **kwargs):
    return _build_work_queue(state, options=QueueBuildOptions(**kwargs))


def _issue(
    fid: str,
    *,
    detector: str = "smells",
    file: str = "src/a.py",
    tier: int = 3,
    confidence: str = "medium",
    status: str = "open",
    detail: dict | None = None,
) -> dict:
    return {
        "id": fid,
        "detector": detector,
        "file": file,
        "tier": tier,
        "confidence": confidence,
        "summary": fid,
        "status": status,
        "detail": detail or {},
    }


def _state(issues: list[dict], *, dimension_scores: dict | None = None) -> dict:
    return {
        "issues": {f["id"]: f for f in issues},
        "dimension_scores": dimension_scores or {},
    }


def test_review_issue_uses_natural_tier():
    review = _issue(
        "review::src/a.py::naming",
        detector="review",
        tier=2,
        detail={"dimension": "naming_quality"},
    )
    mechanical = _issue("smells::src/a.py::x", detector="smells", tier=3)
    state = _state(
        [review, mechanical],
        dimension_scores={
            "Naming quality": {"score": 94.0, "strict": 94.0, "failing": 1}
        },
    )

    queue = build_work_queue(state, count=None, include_subjective=False)
    by_id = {item["id"]: item for item in queue["items"] if item["kind"] == "issue"}
    assert "review::src/a.py::naming" in by_id
    assert "smells::src/a.py::x" in by_id


def test_review_items_ranked_alongside_mechanical():
    urgent = _issue(
        "security::src/a.py::x", detector="security", tier=1, confidence="high"
    )
    review = _issue(
        "review::src/a.py::naming",
        detector="review",
        tier=2,
        confidence="high",
        detail={"dimension": "naming_quality"},
    )
    state = _state(
        [urgent, review],
        dimension_scores={
            "Naming quality": {"score": 92.0, "strict": 92.0, "failing": 2}
        },
    )

    queue = build_work_queue(state, count=None, include_subjective=False)
    ids = {item["id"] for item in queue["items"]}
    # Both items appear in the queue
    assert "security::src/a.py::x" in ids
    assert "review::src/a.py::naming" in ids


def test_review_items_sort_by_issue_weight_within_tier():
    standard = _issue(
        "review::src/a.py::naming",
        detector="review",
        tier=2,
        confidence="high",
        detail={"dimension": "naming_quality"},
    )
    holistic = _issue(
        "review::src/a.py::logic",
        detector="review",
        tier=2,
        confidence="high",
        detail={"dimension": "logic_clarity", "holistic": True},
    )
    state = _state(
        [standard, holistic],
        dimension_scores={
            "Naming quality": {"score": 92.0, "strict": 92.0, "failing": 2},
            "Logic clarity": {"score": 88.0, "strict": 88.0, "failing": 3},
        },
    )

    queue = build_work_queue(state, count=None, include_subjective=False)
    # Within same tier and confidence, holistic (higher review_weight) sorts first
    assert [item["id"] for item in queue["items"][:2]] == [
        "review::src/a.py::logic",
        "review::src/a.py::naming",
    ]


def test_queue_contains_mechanical_and_synthetic_subjective_items():
    # When no objective backlog exists, stale subjective items appear alongside mechanical.
    state = _state(
        [],
        dimension_scores={
            "Naming quality": {"score": 94.0, "strict": 94.0, "failing": 2, "stale": True},
            "Logic clarity": {"score": 100.0, "strict": 100.0, "failing": 0},
        },
    )

    queue = build_work_queue(state, count=None, include_subjective=True)
    ids = {item["id"] for item in queue["items"]}
    assert "subjective::naming_quality" in ids


def test_subjective_items_do_not_starve_objective_queue_head():
    """Non-initial subjective items are excluded when objective backlog exists."""
    review = _issue(
        "review::.::holistic::naming_quality::abc12345",
        detector="review",
        tier=3,
        detail={"holistic": True, "dimension": "naming_quality"},
    )
    state = _state(
        [
            _issue("security::src/a.py::x", detector="security", tier=1, confidence="high"),
            _issue("smells::src/a.py::y", detector="smells", tier=2, confidence="medium"),
            review,
        ],
        dimension_scores={
            "Naming quality": {"score": 92.0, "strict": 92.0, "failing": 3},
        },
    )

    queue = build_work_queue(state, count=None, include_subjective=True)
    ids = [item["id"] for item in queue["items"]]
    # Objective items present
    assert "security::src/a.py::x" in ids
    # Subjective items blocked while objective backlog exists
    assert not any(item_id.startswith("subjective::") for item_id in ids)


def test_impact_sort_with_count_limit():
    """With count=1 and no dimension scores, tiebreakers apply: high
    confidence mechanical leads."""
    state = _state(
        [
            _issue("security::src/a.py::x", detector="security", tier=1, confidence="high"),
        ],
        dimension_scores={
            "Naming quality": {"score": 80.0, "strict": 80.0, "failing": 5},
        },
    )

    queue = build_work_queue(state, count=1, include_subjective=True)
    assert queue["items"][0]["id"] == "security::src/a.py::x"


def test_explain_payload_added_when_requested():
    state = _state(
        [
            _issue(
                "smells::src/a.py::x", tier=3, confidence="medium", detail={"count": 7}
            )
        ]
    )

    queue = build_work_queue(state, count=None, explain=True)
    item = queue["items"][0]
    assert "explain" in item
    assert item["explain"]["ranking_factors"] == [
        "estimated_impact desc",
        "confidence asc",
        "count desc",
        "id asc",
    ]
    assert "estimated_impact" in item["explain"]


def test_subjective_items_respect_target_threshold():
    state = _state(
        [],
        dimension_scores={
            "Naming quality": {"score": 94.0, "strict": 94.0, "failing": 2, "stale": True},
            "AI generated debt": {"score": 96.0, "strict": 96.0, "failing": 1, "stale": True},
        },
    )

    queue = build_work_queue(
        state, count=None, include_subjective=True, subjective_threshold=95
    )
    ids = {item["id"] for item in queue["items"]}
    assert "subjective::naming_quality" in ids
    assert "subjective::ai_generated_debt" not in ids


def test_subjective_item_uses_show_review_when_matching_review_issues_exist():
    review = _issue(
        "review::.::holistic::mid_level_elegance::split::abc12345",
        detector="review",
        tier=3,
        detail={"holistic": True, "dimension": "mid_level_elegance"},
    )
    state = _state(
        [review],
        dimension_scores={
            "Mid elegance": {"score": 70.0, "strict": 70.0, "failing": 1},
        },
    )

    queue = build_work_queue(
        state, count=None, include_subjective=True, subjective_threshold=95
    )
    subj = next(
        item for item in queue["items"] if item["kind"] == "subjective_dimension"
    )
    assert subj["id"] == "subjective::mid_level_elegance"
    assert subj["primary_command"] == "desloppify show review --status open"
    assert subj["detail"]["open_review_issues"] == 1


def test_stale_subjective_item_uses_show_review_when_matching_review_issues_exist():
    review = _issue(
        "review::.::holistic::initialization_coupling::abc12345",
        detector="review",
        tier=3,
        detail={"holistic": True, "dimension": "initialization_coupling"},
    )
    state = _state(
        [review],
        dimension_scores={
            "Init coupling": {
                "score": 42.2,
                "strict": 42.2,
                "failing": 1,
                "checks": 1,
                "detectors": {
                    "subjective_assessment": {
                        "dimension_key": "initialization_coupling",
                    }
                },
            },
        },
    )
    state["subjective_assessments"] = {
        "initialization_coupling": {
            "score": 42.2,
            "needs_review_refresh": True,
            "stale_since": "2026-01-01T00:00:00+00:00",
        }
    }

    queue = build_work_queue(
        state, count=None, include_subjective=True, subjective_threshold=95
    )
    subj = next(
        item for item in queue["items"] if item["kind"] == "subjective_dimension"
    )
    assert "[stale — re-review]" in subj["summary"]
    assert subj["primary_command"] == "desloppify show review --status open"
    assert subj["detail"]["open_review_issues"] == 1


def test_unassessed_subjective_item_points_to_holistic_refresh():
    state = _state(
        [],
        dimension_scores={
            "High elegance": {"score": 0.0, "strict": 0.0, "failing": 0},
        },
    )

    queue = build_work_queue(
        state, count=None, include_subjective=True, subjective_threshold=95
    )
    subj = next(
        item for item in queue["items"] if item["kind"] == "subjective_dimension"
    )
    assert subj["id"] == "subjective::high_level_elegance"
    assert subj["primary_command"] == "desloppify review --prepare --dimensions high_level_elegance"


def test_subjective_review_issue_points_to_review_triage():
    coverage = _issue(
        "subjective_review::src/a.py::changed",
        detector="subjective_review",
        tier=4,
        detail={"reason": "changed"},
    )
    state = _state([coverage])

    queue = build_work_queue(state, count=None, include_subjective=False)
    item = queue["items"][0]
    assert item["primary_command"] == "desloppify show subjective"


def test_holistic_subjective_review_issue_points_to_holistic_refresh():
    holistic = _issue(
        "subjective_review::.::holistic_unreviewed",
        detector="subjective_review",
        file=".",
        tier=4,
        detail={"reason": "unreviewed"},
    )
    state = _state([holistic])

    queue = build_work_queue(state, count=None, include_subjective=False)
    item = queue["items"][0]
    assert item["primary_command"] == "desloppify review --prepare"


# ── QueueBuildOptions defaults ────────────────────────────


def test_queue_build_options_defaults():
    opts = QueueBuildOptions()
    assert opts.count == 1
    from desloppify.engine._work_queue.core import _SCAN_PATH_FROM_STATE
    assert opts.scan_path is _SCAN_PATH_FROM_STATE
    assert opts.scope is None
    assert opts.status == "open"
    assert opts.include_subjective is True
    assert opts.subjective_threshold == 100.0
    assert opts.chronic is False
    assert opts.explain is False


# ── Invalid status raises ValueError ─────────────────────


def test_invalid_status_raises_value_error():
    import pytest

    state = _state([_issue("a")])
    with pytest.raises(ValueError, match="Unsupported status filter"):
        build_work_queue(state, status="bogus")


def test_legacy_string_detail_does_not_crash_queue_build():
    """Queue building should tolerate issues whose detail is a plain string."""
    review = _issue(
        "review::src/a.py::legacy",
        detector="review",
        detail={"dimension": "naming_quality"},
    )
    weird = _issue("responsibility_cohesion::src/a.py::legacy", detector="smells")
    weird["detail"] = "Clusters: alpha, beta"

    state = _state(
        [review, weird],
        dimension_scores={
            "Naming quality": {"score": 92.0, "strict": 92.0, "failing": 1}
        },
    )
    queue = build_work_queue(state, count=None, include_subjective=False)
    ids = [item["id"] for item in queue["items"]]
    assert "review::src/a.py::legacy" in ids
    assert "responsibility_cohesion::src/a.py::legacy" in ids


# ── Subjective threshold clamping ─────────────────────────


def test_subjective_threshold_clamped_to_valid_range():
    """Threshold values outside [0, 100] are clamped, not rejected."""
    state = _state(
        [],
        dimension_scores={
            "Naming quality": {"score": 50.0, "strict": 50.0, "failing": 1, "stale": True},
        },
    )
    # threshold=-10 clamps to 0.0 -> score 50 >= 0 -> item excluded
    queue = build_work_queue(
        state, count=None, include_subjective=True, subjective_threshold=-10
    )
    subj_items = [item for item in queue["items"] if item["kind"] == "subjective_dimension"]
    assert subj_items == []

    # threshold=200 clamps to 100.0 -> score 50 < 100 -> item included
    queue2 = build_work_queue(
        state, count=None, include_subjective=True, subjective_threshold=200
    )
    subj_items2 = [item for item in queue2["items"] if item["kind"] == "subjective_dimension"]
    assert len(subj_items2) >= 1


# ── Count limiting ────────────────────────────────────────


def test_count_limits_returned_items():
    state = _state(
        [
            _issue("a", detector="unused", tier=2, confidence="high"),
            _issue("b", detector="unused", tier=2, confidence="medium"),
            _issue("c", detector="unused", tier=2, confidence="low"),
        ]
    )

    queue = build_work_queue(state, count=2, include_subjective=False)
    assert len(queue["items"]) == 2
    assert queue["total"] == 3


def test_count_none_returns_all_items():
    state = _state(
        [_issue("a", tier=2), _issue("b", tier=3), _issue("c", tier=4)]
    )

    queue = build_work_queue(state, count=None, include_subjective=False)
    assert len(queue["items"]) == 3
    assert queue["total"] == 3


def test_default_count_is_1():
    state = _state(
        [_issue("a", tier=2), _issue("b", tier=3)]
    )

    queue = build_work_queue(state, include_subjective=False)
    assert len(queue["items"]) == 1


# ── Empty state ───────────────────────────────────────────


def test_empty_state_returns_empty_queue():
    queue = build_work_queue({}, count=None, include_subjective=False)
    assert queue["items"] == []
    assert queue["total"] == 0


# ── Grouped output ────────────────────────────────────────


def test_grouped_output_groups_by_item():
    state = _state(
        [
            _issue("a", file="src/a.py"),
            _issue("b", file="src/b.py"),
        ]
    )

    queue = build_work_queue(state, count=None, include_subjective=False)
    grouped = queue["grouped"]
    # Default grouping is "item", which groups by file
    assert isinstance(grouped, dict)


# ── Status filter ─────────────────────────────────────────


def test_status_filter_fixed():
    state = _state(
        [
            _issue("open_one", status="open"),
            _issue("fixed_one", status="fixed"),
        ]
    )

    queue = build_work_queue(state, status="fixed", count=None, include_subjective=False)
    assert all(item["status"] == "fixed" for item in queue["items"])
    assert len(queue["items"]) == 1


def test_status_filter_all():
    state = _state(
        [
            _issue("open_one", status="open"),
            _issue("fixed_one", status="fixed"),
        ]
    )

    queue = build_work_queue(state, status="all", count=None, include_subjective=False)
    assert len(queue["items"]) == 2


# ── Chronic mode ──────────────────────────────────────────


def test_chronic_mode_filters_reopened_issues():
    issues = [
        {**_issue("chronic_one"), "reopen_count": 3},
        {**_issue("normal_one"), "reopen_count": 0},
        {**_issue("once_reopened"), "reopen_count": 1},
    ]
    state = _state(issues)

    queue = build_work_queue(state, chronic=True, count=None, include_subjective=False)
    ids = {item["id"] for item in queue["items"]}
    assert "chronic_one" in ids
    assert "normal_one" not in ids
    assert "once_reopened" not in ids


# ── Subjective exclusion from chronic mode ────────────────


def test_chronic_mode_excludes_subjective_items():
    state = _state(
        [],
        dimension_scores={
            "Naming quality": {"score": 50.0, "strict": 50.0, "failing": 1},
        },
    )

    queue = build_work_queue(
        state, chronic=True, count=None, include_subjective=True
    )
    subj_items = [item for item in queue["items"] if item["kind"] == "subjective_dimension"]
    assert subj_items == []


# ── Subjective items appear alongside mechanical ──────────


def test_stale_subjective_gated_when_objective_backlog_exists():
    """Stale subjective items are suppressed while objective backlog exists."""
    objective_issues = [
        _issue(f"smells::src/{c}.py::x", detector="smells", tier=3)
        for c in "abcd"
    ]
    state = _state(
        objective_issues,
        dimension_scores={
            "Naming quality": {
                "score": 70.0,
                "strict": 70.0,
                "failing": 1,
                "detectors": {
                    "subjective_assessment": {"dimension_key": "naming_quality"},
                },
            },
        },
    )
    state["subjective_assessments"] = {
        "naming_quality": {
            "score": 70.0,
            "needs_review_refresh": True,
            "stale_since": "2026-01-01T00:00:00+00:00",
        }
    }

    queue = build_work_queue(state, count=None, include_subjective=True)
    ids = [item["id"] for item in queue["items"]]
    subj_ids = [i for i in ids if i.startswith("subjective::")]

    # Stale subjective items are gated when objective backlog > 0
    assert len(subj_ids) == 0
    assert len(ids) == 4  # 4 objective only


def test_stale_subjective_appear_when_no_objective_backlog():
    """Stale subjective items surface when no objective issues remain."""
    state = _state(
        [],
        dimension_scores={
            "Naming quality": {
                "score": 70.0,
                "strict": 70.0,
                "failing": 1,
                "detectors": {
                    "subjective_assessment": {"dimension_key": "naming_quality"},
                },
            },
        },
    )
    state["subjective_assessments"] = {
        "naming_quality": {
            "score": 70.0,
            "needs_review_refresh": True,
            "stale_since": "2026-01-01T00:00:00+00:00",
        }
    }

    queue = build_work_queue(state, count=None, include_subjective=True)
    ids = [item["id"] for item in queue["items"]]
    subj_ids = [i for i in ids if i.startswith("subjective::")]

    assert len(subj_ids) == 1
    assert "subjective::naming_quality" in ids


def test_unassessed_subjective_visible_with_objective_backlog():
    """When initial reviews exist, only they are shown — objective items hidden.

    Initial reviews are the first phase: scan → review → score → plan.
    Objective work becomes visible only after initial reviews are done.
    """
    objective_issues = [
        _issue(f"smells::src/{c}.py::x", detector="smells", tier=3)
        for c in "abcd"
    ]
    state = _state(
        objective_issues,
        dimension_scores={
            "Naming quality": {
                "score": 0.0,
                "strict": 0.0,
                "failing": 0,
                "detectors": {
                    "subjective_assessment": {
                        "dimension_key": "naming_quality",
                        "placeholder": True,
                    },
                },
            },
        },
    )
    state["subjective_assessments"] = {
        "naming_quality": {
            "score": 0.0,
            "placeholder": True,
        }
    }

    queue = build_work_queue(state, count=None, include_subjective=True)
    ids = [item["id"] for item in queue["items"]]
    subj_ids = [i for i in ids if i.startswith("subjective::")]

    # Initial reviews gate: only subjective items visible, objective hidden
    assert len(subj_ids) == 1
    assert "subjective::naming_quality" in ids
    assert len(ids) == 1  # only initial review — objective items hidden


# ── Impact-based ordering ──────────────────────────────────


def test_high_impact_subjective_before_low_impact_mechanical():
    """A subjective dimension with high headroom sorts before a mechanical
    issue in a near-perfect dimension."""
    from desloppify.engine._work_queue.ranking import enrich_with_impact, item_sort_key

    subj_item = {
        "id": "subjective::naming",
        "kind": "subjective_dimension",
        "detail": {"dimension_name": "Naming quality", "strict_score": 43.0},
        "confidence": "medium",
    }
    mech_item = {
        "id": "smells::src/a.py::x",
        "kind": "issue",
        "detector": "smells",
        "confidence": "high",
        "detail": {"count": 1},
    }

    dimension_scores = {
        "Naming quality": {
            "score": 43.0,
            "strict": 43.0,
            "failing": 3,
            "detectors": {
                "subjective_assessment": {"dimension_key": "naming_quality"},
            },
        },
        "Code quality": {
            "score": 97.0,
            "strict": 97.0,
            "checks": 200,
            "failing": 1,
            "detectors": {
                "smells": {"weighted_failures": 1, "potential": 200},
            },
        },
    }

    enrich_with_impact([subj_item, mech_item], dimension_scores)

    # Naming quality has much more headroom (57) than Code quality (3)
    assert subj_item["estimated_impact"] > mech_item["estimated_impact"]
    assert item_sort_key(subj_item) < item_sort_key(mech_item)


def test_impact_fallback_when_no_dimension_scores():
    """When no dimension_scores exist, all items get impact 0.0 and
    tiebreakers provide default ordering."""
    from desloppify.engine._work_queue.ranking import enrich_with_impact, item_sort_key

    items = [
        {
            "id": "smells::src/a.py::x",
            "kind": "issue",
            "detector": "smells",
            "confidence": "high",
            "detail": {"count": 5},
        },
        {
            "id": "smells::src/b.py::y",
            "kind": "issue",
            "detector": "smells",
            "confidence": "medium",
            "detail": {"count": 2},
        },
    ]

    enrich_with_impact(items, {})

    assert all(item["estimated_impact"] == 0.0 for item in items)
    # High confidence sorts before medium when impact is equal
    assert item_sort_key(items[0]) < item_sort_key(items[1])


# ── Evidence-only filtering ──────────────────────────────


def test_low_confidence_props_excluded_from_queue():
    """Low-confidence issues from detectors with standalone_threshold are filtered."""
    state = _state(
        [_issue("props::src/a.tsx::big", detector="props", confidence="low")]
    )
    queue = build_work_queue(state, count=None, include_subjective=False)
    assert len(queue["items"]) == 0


def test_medium_confidence_props_included_in_queue():
    """Medium-confidence issues pass the standalone_threshold='medium' check."""
    state = _state(
        [_issue("props::src/a.tsx::big", detector="props", confidence="medium")]
    )
    queue = build_work_queue(state, count=None, include_subjective=False)
    ids = {item["id"] for item in queue["items"]}
    assert "props::src/a.tsx::big" in ids


def test_high_confidence_always_passes():
    """High-confidence issues always pass any standalone threshold."""
    state = _state(
        [_issue("props::src/a.tsx::huge", detector="props", confidence="high")]
    )
    queue = build_work_queue(state, count=None, include_subjective=False)
    ids = {item["id"] for item in queue["items"]}
    assert "props::src/a.tsx::huge" in ids


def test_detector_without_threshold_unaffected():
    """Detectors without standalone_threshold (e.g. unused) pass at any confidence."""
    state = _state(
        [_issue("unused::src/a.py::x", detector="unused", confidence="low")]
    )
    queue = build_work_queue(state, count=None, include_subjective=False)
    ids = {item["id"] for item in queue["items"]}
    assert "unused::src/a.py::x" in ids


def test_evidence_only_issue_still_in_state():
    """Evidence-only issues are filtered from queue but remain in state (scoring intact)."""
    issues = [_issue("props::src/a.tsx::big", detector="props", confidence="low")]
    state = _state(issues)
    # Issue exists in state
    assert "props::src/a.tsx::big" in state["issues"]
    # But not in queue
    queue = build_work_queue(state, count=None, include_subjective=False)
    assert len(queue["items"]) == 0


def test_evidence_only_items_dont_block_subjective():
    """Evidence-only items (filtered before lifecycle) don't block subjective items.

    The lifecycle filter operates on the actual queue contents after all prior
    filters. If evidence-only items are the only objective issues and they get
    filtered out, subjective items surface because nothing objective remains.
    """
    # All issues are low-confidence smells (below standalone_threshold)
    issues = [
        _issue(f"smells::src/{c}.py::x", detector="smells", confidence="low")
        for c in "abcd"
    ]
    state = _state(
        issues,
        dimension_scores={
            "Naming quality": {"score": 70.0, "strict": 70.0, "failing": 1, "stale": True},
        },
    )

    queue = build_work_queue(state, count=None, include_subjective=True)
    subj_ids = [
        item["id"] for item in queue["items"]
        if item["kind"] == "subjective_dimension"
    ]
    # Evidence-only items filtered before lifecycle → no objective items remain
    # → subjective items surface
    assert len(subj_ids) == 1


def test_low_impact_items_preserved_in_queue():
    """All open issues remain in queue regardless of impact score.

    The impact floor was removed — triage/skip is the authority on what matters.
    """
    state = _state(
        [_issue("unused::src/a.py::x", detector="unused", confidence="high")],
        dimension_scores={
            "Code quality": {"score": 99.99, "strict": 99.99, "checks": 10000, "failing": 1},
        },
    )
    queue = build_work_queue(state, count=None, include_subjective=False)
    ids = {item["id"] for item in queue["items"]}
    assert "unused::src/a.py::x" in ids


def test_registry_standalone_threshold_count():
    """Exactly 7 detectors have standalone_threshold='medium'."""
    from desloppify.base.registry import DETECTORS

    threshold_detectors = [
        name for name, meta in DETECTORS.items()
        if meta.standalone_threshold == "medium"
    ]
    assert sorted(threshold_detectors) == sorted([
        "props", "patterns", "naming", "react", "smells", "dupes", "dict_keys",
    ])


# ── Cluster collapse ─────────────────────────────────────


def test_collapse_clusters_preserves_order():
    """Cluster meta-item appears at position of first member, not re-sorted."""
    from desloppify.engine._work_queue.plan_order import collapse_clusters

    plan: dict = {
        "queue_order": [],
        "skipped": {},
        "overrides": {},
        "clusters": {},
        "active_cluster": None,
    }
    plan["clusters"]["auto/unused"] = {
        "name": "auto/unused",
        "auto": True,
        "cluster_key": "auto::unused",
        "issue_ids": ["u1", "u2"],
        "description": "Remove 2 unused issues",
        "action": "desloppify autofix unused-imports --dry-run",
        "user_modified": False,
    }

    # Place a non-cluster item first, then the two cluster members
    items = [
        {"id": "other", "kind": "issue", "detector": "structural",
         "confidence": "medium", "detail": {}},
        {"id": "u1", "kind": "issue", "detector": "unused",
         "confidence": "high", "detail": {}, "estimated_impact": 1.0},
        {"id": "u2", "kind": "issue", "detector": "unused",
         "confidence": "high", "detail": {}, "estimated_impact": 1.0},
    ]

    result = collapse_clusters(items, plan)
    # Non-cluster item stays at position 0
    assert result[0]["id"] == "other"
    # Cluster meta-item appears at position 1 (where first member was)
    assert result[1]["kind"] == "cluster"
    assert result[1]["id"] == "auto/unused"
    assert len(result) == 2  # other + cluster


# -- Plan-ordered subjective items surface despite objective backlog --------


def test_plan_ordered_stale_subjective_gated_with_objective_backlog():
    """Stale subjective items are gated by lifecycle filter while objective
    issues exist, even when the plan includes them in queue_order.
    """
    from desloppify.engine._plan.schema import empty_plan

    objective_issues = [
        _issue(f"smells::src/{c}.py::x", detector="smells", tier=3)
        for c in "abcd"
    ]
    state = _state(
        objective_issues,
        dimension_scores={
            "Naming quality": {
                "score": 70.0,
                "strict": 70.0,
                "failing": 1,
                "detectors": {
                    "subjective_assessment": {"dimension_key": "naming_quality"},
                },
            },
        },
    )
    state["subjective_assessments"] = {
        "naming_quality": {
            "score": 70.0,
            "needs_review_refresh": True,
            "stale_since": "2026-01-01T00:00:00+00:00",
        }
    }

    # Without plan: stale subjective item is gated
    queue_no_plan = build_work_queue(state, count=None, include_subjective=True)
    subj_no_plan = [
        i["id"] for i in queue_no_plan["items"] if i["id"].startswith("subjective::")
    ]
    assert len(subj_no_plan) == 0

    # With plan that includes the stale dim in queue_order: still gated
    plan = empty_plan()
    plan["queue_order"] = [
        "subjective::naming_quality",
        "smells::src/a.py::x",
        "smells::src/b.py::x",
        "smells::src/c.py::x",
        "smells::src/d.py::x",
    ]
    queue_with_plan = build_work_queue(
        state, count=None, include_subjective=True, plan=plan,
    )
    subj_with_plan = [
        i["id"] for i in queue_with_plan["items"] if i["id"].startswith("subjective::")
    ]
    # Stale subjective items gated by lifecycle filter even with plan ordering
    assert len(subj_with_plan) == 0


def test_triage_pending_does_not_unhide_stale_subjective_items():
    """Triage presence must not bypass stale-subjective gating."""
    from desloppify.engine._plan.schema import empty_plan

    state = _state(
        [
            _issue("smells::src/a.py::x", detector="smells", tier=3),
            _issue("smells::src/b.py::x", detector="smells", tier=3),
        ],
        dimension_scores={
            "Naming quality": {
                "score": 70.0,
                "strict": 70.0,
                "failing": 1,
                "detectors": {
                    "subjective_assessment": {"dimension_key": "naming_quality"},
                },
            },
            "Error consistency": {
                "score": 72.0,
                "strict": 72.0,
                "failing": 1,
                "detectors": {
                    "subjective_assessment": {"dimension_key": "error_consistency"},
                },
            },
        },
    )
    state["subjective_assessments"] = {
        "naming_quality": {
            "score": 70.0,
            "needs_review_refresh": True,
            "stale_since": "2026-01-01T00:00:00+00:00",
        },
        "error_consistency": {
            "score": 72.0,
            "needs_review_refresh": True,
            "stale_since": "2026-01-01T00:00:00+00:00",
        },
    }

    plan = empty_plan()
    plan["queue_order"] = [
        "triage::observe",
        "subjective::naming_quality",
        "subjective::error_consistency",
        "smells::src/a.py::x",
        "smells::src/b.py::x",
    ]

    queue = build_work_queue(
        state, count=None, include_subjective=True, plan=plan,
    )
    ids = [item["id"] for item in queue["items"]]
    assert "smells::src/a.py::x" in ids
    assert "smells::src/b.py::x" in ids
    assert "subjective::naming_quality" not in ids
    assert "subjective::error_consistency" not in ids


# ── Lifecycle filter runs after plan_presort ───────────


def test_skipped_objective_items_dont_block_subjective():
    """Plan-skipped objective items are removed before lifecycle filter,
    so they don't block subjective reassessment items.
    """
    from desloppify.engine._plan.schema import empty_plan

    objective_issues = [
        _issue(f"smells::src/{c}.py::x", detector="smells", tier=3)
        for c in "abcd"
    ]
    state = _state(
        objective_issues,
        dimension_scores={
            "Naming quality": {
                "score": 70.0,
                "strict": 70.0,
                "failing": 1,
                "detectors": {
                    "subjective_assessment": {"dimension_key": "naming_quality"},
                },
            },
        },
    )
    state["subjective_assessments"] = {
        "naming_quality": {
            "score": 70.0,
            "needs_review_refresh": True,
            "stale_since": "2026-01-01T00:00:00+00:00",
        }
    }

    # Skip ALL objective issues in the plan
    plan = empty_plan()
    plan["queue_order"] = [
        "subjective::naming_quality",
        "smells::src/a.py::x",
        "smells::src/b.py::x",
        "smells::src/c.py::x",
        "smells::src/d.py::x",
    ]
    plan["skipped"] = {
        "smells::src/a.py::x": {"reason": "deferred"},
        "smells::src/b.py::x": {"reason": "deferred"},
        "smells::src/c.py::x": {"reason": "deferred"},
        "smells::src/d.py::x": {"reason": "deferred"},
    }

    queue = build_work_queue(
        state, count=None, include_subjective=True, plan=plan,
    )
    subj_ids = [
        i["id"] for i in queue["items"] if i["id"].startswith("subjective::")
    ]
    # All objective items skipped → lifecycle filter sees no objective work
    # → stale subjective item surfaces
    assert len(subj_ids) == 1
    assert "subjective::naming_quality" in subj_ids


# ── Wontfix / resolved issues excluded (#193) ──────────


def test_wontfixed_issues_excluded_from_queue():
    """Issues with status 'wontfix' never appear in the default queue.

    Regression test for #193: wontfixed issues were leaking into the
    auto-generated queue because filtering was spread across multiple
    modules and easy to miss.
    """
    state = _state(
        [
            _issue("a", status="open"),
            _issue("b", status="wontfix"),
            _issue("c", status="fixed"),
            _issue("d", status="open"),
        ]
    )

    queue = build_work_queue(state, count=None, include_subjective=False)
    ids = {item["id"] for item in queue["items"]}
    assert "a" in ids
    assert "d" in ids
    assert "b" not in ids  # wontfix excluded
    assert "c" not in ids  # fixed excluded


def test_wontfixed_issues_excluded_with_plan():
    """Wontfixed issues stay out even when a plan is active."""
    from desloppify.engine._plan.schema import empty_plan

    plan = empty_plan()
    plan["queue_order"] = ["a", "b", "c", "d"]

    state = _state(
        [
            _issue("a", status="open"),
            _issue("b", status="wontfix"),
            _issue("c", status="fixed"),
            _issue("d", status="open"),
        ]
    )

    queue = build_work_queue(state, count=None, include_subjective=False, plan=plan)
    ids = {item["id"] for item in queue["items"]}
    assert "a" in ids
    assert "d" in ids
    assert "b" not in ids
    assert "c" not in ids


# ── Triage lifecycle ordering ────────────────────────────────


def test_triage_stages_hidden_during_initial_reviews():
    """Phase 1 hides triage stages and workflow actions — only initial reviews visible."""
    objective_issues = [
        _issue(f"smells::src/{c}.py::x", detector="smells", tier=3)
        for c in "ab"
    ]
    state = _state(
        objective_issues,
        dimension_scores={
            "Naming quality": {
                "score": 0.0,
                "strict": 0.0,
                "failing": 0,
                "detectors": {
                    "subjective_assessment": {
                        "dimension_key": "naming_quality",
                        "placeholder": True,
                    },
                },
            },
        },
    )
    state["subjective_assessments"] = {
        "naming_quality": {"score": 0.0, "placeholder": True}
    }

    # Inject a triage stage and a workflow action into queue_order so they
    # would appear if the lifecycle filter didn't hide them.
    plan = {
        "queue_order": [
            "triage::observe",
            "workflow::communicate-score",
            "subjective::naming_quality",
        ],
        "queue_skipped": {},
    }
    queue = build_work_queue(state, count=None, include_subjective=True, plan=plan)
    ids = [item["id"] for item in queue["items"]]

    # Only initial review visible — triage and workflow hidden
    assert ids == ["subjective::naming_quality"]


def test_triage_stages_sort_after_workflow_in_natural_ranking():
    """In natural ranking (no plan), workflow actions sort before triage stages."""
    from desloppify.engine._work_queue.ranking import item_sort_key

    workflow_item = {
        "id": "workflow::communicate-score",
        "kind": "workflow_action",
        "tier": 1,
        "confidence": "high",
        "detector": "workflow",
        "file": ".",
    }
    triage_item = {
        "id": "triage::observe",
        "kind": "workflow_stage",
        "tier": 1,
        "confidence": "high",
        "detector": "triage",
        "file": ".",
        "detail": {"stage": "observe"},
        "is_blocked": False,
    }

    wf_key = item_sort_key(workflow_item)
    tr_key = item_sort_key(triage_item)
    assert wf_key < tr_key, "workflow actions should sort before triage stages"
