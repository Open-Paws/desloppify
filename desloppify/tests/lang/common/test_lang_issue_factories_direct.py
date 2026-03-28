"""Direct coverage tests for issue factory helpers."""

from __future__ import annotations

from desloppify.languages._framework.issue_factories import (
    make_single_use_issues,
    make_unused_issues,
)


def test_make_unused_issues_shapes_entries():
    logs: list[str] = []
    entries = [
        {"file": "src/a.py", "name": "x", "line": 3, "category": "imports"},
        {"file": "src/b.py", "name": "y", "line": 6, "category": "vars"},
    ]
    issues = make_unused_issues(entries, logs.append)

    assert len(issues) == 2
    assert issues[0]["tier"] == 1
    assert issues[1]["tier"] == 2
    assert issues[0]["detector"] == "unused"
    assert logs and "2 issues" in logs[-1]


def test_make_single_use_issues_applies_loc_filtering():
    logs: list[str] = []
    entries = [
        {"file": "src/low.py", "loc": 80, "sole_importer": "src/app.py"},
        {"file": "src/high.py", "loc": 320, "sole_importer": "src/app.py"},
    ]

    def _area(path: str) -> str:
        if "high.py" in path:
            return "feature"
        return "app"

    issues = make_single_use_issues(entries, get_area=_area, stderr_fn=logs.append)

    assert len(issues) == 1
    assert issues[0]["file"] == "src/high.py"
    assert issues[0]["detector"] == "single_use"
    assert logs and "single-use" in logs[-1]
