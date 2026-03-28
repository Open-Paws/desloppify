"""Direct coverage tests for holistic dependency cluster builders."""

from __future__ import annotations

from desloppify.intelligence.review.context_holistic.clusters.dependency import (
    _build_boundary_violations,
    _build_dead_code,
    _build_deferred_import_density,
    _build_private_crossings,
)


def test_build_boundary_violations_uses_detail_fallback_fields() -> None:
    by_detector = {
        "coupling": [
            {
                "file": "src/a.py",
                "detail": {"target": "src/b.py", "direction": "a->b"},
            }
        ],
        "layer_violation": [
            {
                "file": "src/c.py",
                "detail": {"imported_from": "src/d.py", "violation": "upward"},
            }
        ],
    }

    rows = _build_boundary_violations(by_detector)
    assert rows == [
        {"file": "src/a.py", "target": "src/b.py", "direction": "a->b"},
        {"file": "src/c.py", "target": "src/d.py", "direction": "upward"},
    ]


def test_build_dead_code_aggregates_orphaned_and_uncalled_with_numeric_guards() -> None:
    by_detector = {
        "orphaned": [
            {"file": "dead/orphaned.py", "detail": {"signals": {"loc": 13}}},
            {"file": "dead/unknown.py", "detail": "bad"},
        ],
        "uncalled_functions": [
            {"file": "dead/unused.py", "detail": {"loc": 7}},
            {"file": "dead/bad.py", "detail": "bad"},
        ],
    }

    rows = _build_dead_code(by_detector)
    assert rows == [
        {"file": "dead/orphaned.py", "kind": "orphaned", "loc": 13},
        {"file": "dead/unknown.py", "kind": "orphaned", "loc": 0},
        {"file": "dead/unused.py", "kind": "uncalled", "loc": 7},
        {"file": "dead/bad.py", "kind": "uncalled", "loc": 0},
    ]


def test_build_private_crossings_uses_symbol_source_target_fallbacks() -> None:
    by_detector = {
        "private_imports": [
            {
                "file": "src/a.py",
                "detail": {"symbol": "_secret", "source": "src/lib.py", "target": "src/t.py"},
            },
            {
                "file": "src/b.py",
                "detail": {"name": "_alt", "imported_from": "src/core.py"},
            },
        ]
    }

    rows = _build_private_crossings(by_detector)
    assert rows == [
        {
            "file": "src/a.py",
            "symbol": "_secret",
            "source": "src/lib.py",
            "target": "src/t.py",
        },
        {
            "file": "src/b.py",
            "symbol": "_alt",
            "source": "src/core.py",
            "target": "src/b.py",
        },
    ]


def test_build_deferred_import_density_filters_sorts_and_limits() -> None:
    by_file: dict[str, list[dict]] = {
        "src/top.py": [
            {"detector": "smells", "detail": {"smell_id": "deferred_import"}},
            {"detector": "smells", "detail": {"smell_id": "deferred_import"}},
            {"detector": "smells", "detail": {"smell_id": "deferred_import"}},
        ],
        "src/mid.py": [
            {"detector": "smells", "detail": {"smell_id": "deferred_import"}},
            {"detector": "smells", "detail": {"smell_id": "deferred_import"}},
        ],
        "src/low.py": [
            {"detector": "smells", "detail": {"smell_id": "deferred_import"}},
            {"detector": "unused", "detail": {}},
        ],
    }

    for index in range(30):
        by_file[f"src/f{index}.py"] = [
            {"detector": "smells", "detail": {"smell_id": "deferred_import"}},
            {"detector": "smells", "detail": {"smell_id": "deferred_import"}},
        ]

    rows = _build_deferred_import_density(by_file)
    assert len(rows) == 20
    assert rows[0] == {"file": "src/top.py", "count": 3}
    assert {"file": "src/mid.py", "count": 2} in rows
    assert {"file": "src/low.py", "count": 1} not in rows
