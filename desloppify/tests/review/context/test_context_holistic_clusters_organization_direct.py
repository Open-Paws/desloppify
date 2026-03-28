"""Direct coverage tests for holistic organization cluster builders."""

from __future__ import annotations

from desloppify.intelligence.review.context_holistic.clusters.organization import (
    _build_flat_dir_issues,
    _build_large_file_distribution,
)


def test_build_flat_dir_issues_uses_fallback_fields_sorts_and_limits() -> None:
    by_detector = {
        "flat_dirs": [
            {
                "file": "src/a/",
                "detail": {"kind": "overload", "file_count": 11, "score": 45},
            },
            {
                "file": "src/b/",
                "detail": {"reason": "too_many_files", "file_count": 9, "combined_score": 33},
            },
        ]
    }

    for idx in range(30):
        by_detector["flat_dirs"].append(
            {
                "file": f"src/f{idx}/",
                "detail": {"kind": "overload", "file_count": 10 + idx, "score": idx},
            }
        )

    rows = _build_flat_dir_issues(by_detector)
    assert len(rows) == 20
    assert rows[0] == {
        "directory": "src/a/",
        "kind": "overload",
        "file_count": 11,
        "combined_score": 45,
    }
    assert {"directory": "src/b/", "kind": "too_many_files", "file_count": 9, "combined_score": 33} in rows


def test_build_large_file_distribution_reads_loc_quantiles_and_handles_empty() -> None:
    by_detector = {
        "structural": [
            {"detail": {"signals": {"loc": loc}}}
            for loc in [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
        ]
    }

    dist = _build_large_file_distribution(by_detector)
    assert dist == {
        "count": 10,
        "median_loc": 600,
        "p90_loc": 1000,
        "p99_loc": 1000,
    }

    assert _build_large_file_distribution({"structural": [{"detail": {"signals": {"loc": 0}}}]}) is None
