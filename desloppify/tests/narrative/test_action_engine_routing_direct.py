"""Direct coverage tests for narrative action routing helpers."""

from __future__ import annotations

from types import SimpleNamespace

import desloppify.intelligence.narrative.action_engine_routing as routing_mod


def test_dimension_name_returns_dimension_or_unknown(monkeypatch) -> None:
    monkeypatch.setattr(
        routing_mod,
        "get_dimension_for_detector",
        lambda detector: SimpleNamespace(name="Complexity") if detector == "large" else None,
    )

    assert routing_mod._dimension_name("large") == "Complexity"
    assert routing_mod._dimension_name("missing") == "Unknown"


def test_append_reorganize_actions_appends_matching_detectors(monkeypatch) -> None:
    monkeypatch.setattr(
        routing_mod,
        "DETECTOR_TOOLS",
        {
            "large": {"action_type": "reorganize", "guidance": "split file"},
            "unused": {"action_type": "auto_fix", "guidance": "autofix"},
        },
    )
    monkeypatch.setattr(
        routing_mod,
        "get_dimension_for_detector",
        lambda _detector: SimpleNamespace(name="File health"),
    )

    actions: list[dict] = []
    routing_mod._append_reorganize_actions(
        actions,
        by_detector={"large": 2, "unused": 5},
        impact_for=lambda detector, count: 1.5 * count,
    )

    assert len(actions) == 1
    action = actions[0]
    assert action["type"] == "reorganize"
    assert action["detector"] == "large"
    assert action["command"] == "desloppify show large --status open"
    assert action["impact"] == 3.0


def test_build_refactor_entry_handles_special_detectors(monkeypatch) -> None:
    monkeypatch.setattr(
        routing_mod,
        "get_dimension_for_detector",
        lambda _detector: SimpleNamespace(name="Design"),
    )

    subjective = routing_mod._build_refactor_entry(
        "subjective_review",
        {"action_type": "manual_fix"},
        4,
        lambda _detector, _count: 0.8,
    )
    assert subjective["command"] == "desloppify review --prepare"
    assert "design review" in subjective["description"]

    review = routing_mod._build_refactor_entry(
        "review",
        {"action_type": "manual_fix", "guidance": "inspect"},
        1,
        lambda _detector, _count: 0.5,
    )
    assert review["type"] == "refactor"
    assert review["command"] == "desloppify show review --status open"

    generic = routing_mod._build_refactor_entry(
        "smells",
        {"action_type": "manual_fix", "guidance": "clean up"},
        2,
        lambda _detector, _count: 1.2,
    )
    assert generic["description"] == "2 smells issues — clean up"


def test_append_refactor_actions_and_debt_action(monkeypatch) -> None:
    monkeypatch.setattr(
        routing_mod,
        "DETECTOR_TOOLS",
        {
            "smells": {"action_type": "refactor", "guidance": "extract helpers"},
            "review": {"action_type": "manual_fix", "guidance": "inspect"},
            "unused": {"action_type": "auto_fix", "guidance": "autofix"},
        },
    )
    monkeypatch.setattr(
        routing_mod,
        "get_dimension_for_detector",
        lambda _detector: SimpleNamespace(name="Dimension"),
    )

    actions: list[dict] = []
    routing_mod._append_refactor_actions(
        actions,
        by_detector={"smells": 3, "review": 2, "unused": 9},
        impact_for=lambda _detector, count: count / 10,
    )
    routing_mod._append_debt_action(actions, {"overall_gap": 2.0})
    routing_mod._append_debt_action(actions, {"overall_gap": 2.4})

    detectors = {a.get("detector") for a in actions}
    assert detectors == {"smells", "review", None}
    debt = next(action for action in actions if action["type"] == "debt_review")
    assert debt["gap"] == 2.4


def test_assign_priorities_and_cluster_annotation() -> None:
    actions = [
        {"type": "manual_fix", "detector": "smells", "impact": 2.0, "count": 2},
        {"type": "auto_fix", "detector": "unused", "impact": 1.0, "count": 1},
        {"type": "reorganize", "detector": "large", "impact": 4.0, "count": 3},
    ]

    prioritized = routing_mod._assign_priorities(actions)
    assert [a["type"] for a in prioritized] == ["auto_fix", "reorganize", "manual_fix"]
    assert [a["priority"] for a in prioritized] == [1, 2, 3]

    routing_mod._annotate_with_clusters(
        prioritized,
        {
            "clusterA": {"auto": True, "cluster_key": "detector::unused"},
            "clusterB": {"auto": True, "name": "auto/smells-hotspot"},
        },
    )

    auto = prioritized[0]
    assert auto["clusters"] == ["clusterA"]
    assert auto["command"] == "desloppify next"
    assert "cluster(s)" in auto["description"]


