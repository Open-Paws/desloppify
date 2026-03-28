"""Tests for boilerplate-duplication zone filtering in shared phases."""

from __future__ import annotations

from desloppify.engine.policy.zones import Zone
from desloppify.languages._framework.base.shared_phases import (
    _filter_boilerplate_entries_by_zone,
)


class _ZoneMapStub:
    def __init__(self, mapping: dict[str, Zone]):
        self._mapping = mapping

    def get(self, path: str) -> Zone:
        return self._mapping.get(path, Zone.PRODUCTION)

    def all_files(self) -> list[str]:
        return list(self._mapping.keys())


def test_boilerplate_filter_drops_unknown_artifact_locations() -> None:
    zone_map = _ZoneMapStub({"src/a.py": Zone.PRODUCTION})
    entries = [
        {
            "id": "dup-1",
            "distinct_files": 2,
            "window_size": 10,
            "locations": [
                {"file": "build/lib/src/a.py", "line": 20},
                {"file": "src/a.py", "line": 12},
            ],
            "sample": [],
        }
    ]
    assert _filter_boilerplate_entries_by_zone(entries, zone_map) == []


def test_boilerplate_filter_drops_test_zone_clusters() -> None:
    zone_map = _ZoneMapStub(
        {
            "src/a.py": Zone.PRODUCTION,
            "tests/test_a.py": Zone.TEST,
        }
    )
    entries = [
        {
            "id": "dup-2",
            "distinct_files": 2,
            "window_size": 10,
            "locations": [
                {"file": "src/a.py", "line": 10},
                {"file": "tests/test_a.py", "line": 18},
            ],
            "sample": [],
        }
    ]
    assert _filter_boilerplate_entries_by_zone(entries, zone_map) == []


def test_boilerplate_filter_keeps_two_production_files() -> None:
    zone_map = _ZoneMapStub(
        {
            "src/a.py": Zone.PRODUCTION,
            "src/b.py": Zone.PRODUCTION,
            "tests/test_a.py": Zone.TEST,
        }
    )
    entries = [
        {
            "id": "dup-3",
            "distinct_files": 3,
            "window_size": 10,
            "locations": [
                {"file": "src/a.py", "line": 10},
                {"file": "tests/test_a.py", "line": 18},
                {"file": "src/b.py", "line": 22},
            ],
            "sample": [],
        }
    ]
    filtered = _filter_boilerplate_entries_by_zone(entries, zone_map)
    assert len(filtered) == 1
    assert filtered[0]["distinct_files"] == 2
    assert [loc["file"] for loc in filtered[0]["locations"]] == ["src/a.py", "src/b.py"]
