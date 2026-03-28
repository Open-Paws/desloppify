"""Direct coverage tests for holistic consistency cluster builders."""

from __future__ import annotations

from desloppify.intelligence.review.context_holistic.clusters.consistency import (
    _build_duplicate_clusters,
    _build_naming_drift,
)


def test_build_duplicate_clusters_handles_defaults_and_fallback_files() -> None:
    by_detector = {
        "dupes": [
            {
                "file": "src/a.py",
                "summary": "dup block",
                "detail": {"kind": "dupes", "name": "helper", "files": ["src/a.py", "src/b.py"]},
            }
        ],
        "boilerplate_duplication": [
            {
                "file": "src/c.py",
                "summary": "boilerplate",
                "detail": {"function": "render_row", "files": []},
            }
        ],
    }

    clusters = _build_duplicate_clusters(by_detector)
    assert len(clusters) == 2
    assert clusters[0]["cluster_size"] == 2
    assert clusters[1]["files"] == ["src/c.py"]


def test_build_naming_drift_groups_by_directory_and_counts_outliers() -> None:
    by_detector = {
        "naming": [
            {"file": "src/app/foo_bar.py", "detail": {"expected_convention": "snake_case"}},
            {"file": "src/app/FooBar.py", "detail": {"expected_convention": "snake_case"}},
            {"file": "src/lib/BadName.py", "detail": {"expected_convention": "snake_case"}},
        ]
    }

    drift = _build_naming_drift(by_detector)
    assert drift[0]["directory"] == "src/app/"
    assert drift[0]["minority_count"] == 2
    assert "src/app/FooBar.py" in drift[0]["outliers"]
    assert drift[1]["directory"] == "src/lib/"
