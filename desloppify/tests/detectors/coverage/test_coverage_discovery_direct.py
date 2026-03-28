"""Direct coverage tests for test-coverage discovery helpers."""

from __future__ import annotations


import desloppify.engine.detectors.test_coverage.discovery as discovery_mod
from desloppify.engine.policy.zones import Zone


class _FakeZoneMap:
    def __init__(self, files_by_zone: dict[Zone, set[str]]) -> None:
        self._files_by_zone = files_by_zone

    def all_files(self) -> set[str]:
        out: set[str] = set()
        for files in self._files_by_zone.values():
            out |= files
        return out

    def include_only(self, files: set[str], *zones: Zone) -> set[str]:
        del files
        out: set[str] = set()
        for zone in zones:
            out |= self._files_by_zone.get(zone, set())
        return out


def test_discover_scorable_and_tests_filters_by_loc_and_logic(monkeypatch) -> None:
    root = str(discovery_mod.get_project_root())
    prod_keep = f"{root}/src/keep.py"
    prod_small = f"{root}/src/small.py"
    script_keep = f"{root}/scripts/run.py"
    test_file = f"{root}/tests/test_keep.py"

    zone_map = _FakeZoneMap(
        {
            Zone.PRODUCTION: {prod_keep, prod_small},
            Zone.SCRIPT: {script_keep},
            Zone.TEST: {test_file},
        }
    )

    loc_map = {
        prod_keep: discovery_mod._MIN_LOC + 1,
        prod_small: discovery_mod._MIN_LOC - 1,
        script_keep: discovery_mod._MIN_LOC + 2,
    }
    monkeypatch.setattr(discovery_mod, "_file_loc", lambda path: loc_map.get(path, 0))
    monkeypatch.setattr(
        discovery_mod,
        "_has_testable_logic",
        lambda path, lang_name: lang_name == "python" and path != script_keep,
    )

    production, tests, scorable, potential = discovery_mod._discover_scorable_and_tests(
        graph={},
        zone_map=zone_map,
        lang_name="python",
        extra_test_files=None,
    )

    assert production == {prod_keep, prod_small, script_keep}
    assert tests == {test_file}
    assert scorable == {prod_keep}
    assert potential > 0


def test_discover_scorable_and_tests_normalizes_extra_test_files(monkeypatch) -> None:
    root = str(discovery_mod.get_project_root())
    prod = f"{root}/src/a.py"
    zone_map = _FakeZoneMap(
        {
            Zone.PRODUCTION: {prod},
            Zone.SCRIPT: set(),
            Zone.TEST: set(),
        }
    )

    monkeypatch.setattr(discovery_mod, "_file_loc", lambda _path: discovery_mod._MIN_LOC + 1)
    monkeypatch.setattr(discovery_mod, "_has_testable_logic", lambda _path, _lang: True)

    _production, tests, _scorable, _potential = discovery_mod._discover_scorable_and_tests(
        graph={},
        zone_map=zone_map,
        lang_name="python",
        extra_test_files={f"{root}/tests/test_a.py", "tests/test_b.py"},
    )

    assert "tests/test_a.py" in tests
    assert "tests/test_b.py" in tests


def test_normalize_graph_paths_rewrites_absolute_import_sets() -> None:
    root = str(discovery_mod.get_project_root())
    graph = {
        f"{root}/src/mod.py": {
            "imports": {f"{root}/src/other.py", "src/third.py"},
            "importer_count": 1,
        }
    }

    normalized = discovery_mod._normalize_graph_paths(graph)

    assert "src/mod.py" in normalized
    assert normalized["src/mod.py"]["imports"] == {"src/other.py", "src/third.py"}
    assert normalized["src/mod.py"]["importer_count"] == 1
