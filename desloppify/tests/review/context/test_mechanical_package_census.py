"""Tests for package size census in mechanical evidence.

Phase 3D: _build_package_size_census groups files by top-level package,
sums LOC, and flags packages >15% of codebase.
"""

from __future__ import annotations

from desloppify.intelligence.review.context_holistic.mechanical import (
    _build_package_size_census,
)


def _issue(
    *,
    detector: str = "structural",
    file: str,
    detail: dict | None = None,
    status: str = "open",
) -> dict:
    return {
        "id": f"{detector}::{file}",
        "detector": detector,
        "file": file,
        "detail": detail or {},
        "status": status,
    }


class TestBuildPackageSizeCensus:

    def test_single_package(self):
        by_file = {
            "pkg/a.py": [_issue(file="pkg/a.py", detail={"loc": 100})],
            "pkg/b.py": [_issue(file="pkg/b.py", detail={"loc": 200})],
        }
        result = _build_package_size_census(by_file)
        assert len(result) == 1
        assert result[0]["package"] == "pkg"
        assert result[0]["loc"] == 300
        assert result[0]["pct_of_total"] == 100.0
        assert result[0]["disproportionate"] is True

    def test_multiple_packages_sorted_by_loc(self):
        by_file = {
            "big/a.py": [_issue(file="big/a.py", detail={"loc": 800})],
            "small/b.py": [_issue(file="small/b.py", detail={"loc": 200})],
        }
        result = _build_package_size_census(by_file)
        assert len(result) == 2
        assert result[0]["package"] == "big"
        assert result[1]["package"] == "small"

    def test_disproportionate_flag(self):
        # 80% / 20% split — both are >15%
        by_file = {
            "big/a.py": [_issue(file="big/a.py", detail={"loc": 800})],
            "small/b.py": [_issue(file="small/b.py", detail={"loc": 200})],
        }
        result = _build_package_size_census(by_file)
        by_pkg = {r["package"]: r for r in result}
        assert by_pkg["big"]["pct_of_total"] == 80.0
        assert by_pkg["big"]["disproportionate"] is True
        assert by_pkg["small"]["pct_of_total"] == 20.0
        assert by_pkg["small"]["disproportionate"] is True

    def test_balanced_packages_not_disproportionate(self):
        # 7 equal packages → each ~14.3% → none >15%
        by_file = {}
        for i in range(7):
            key = f"pkg{i}/mod.py"
            by_file[key] = [_issue(file=key, detail={"loc": 100})]
        result = _build_package_size_census(by_file)
        assert all(not r["disproportionate"] for r in result)

    def test_falls_back_to_1_loc_for_non_structural(self):
        by_file = {
            "pkg/a.py": [_issue(file="pkg/a.py", detector="smells", detail={"smell_id": "broad_except"})],
        }
        result = _build_package_size_census(by_file)
        assert len(result) == 1
        assert result[0]["loc"] == 1  # fallback minimum

    def test_empty_by_file(self):
        assert _build_package_size_census({}) == []

    def test_uses_structural_loc_over_fallback(self):
        by_file = {
            "app/big.py": [
                _issue(file="app/big.py", detail={"loc": 500}),
                _issue(file="app/big.py", detector="smells", detail={"smell_id": "x"}),
            ],
        }
        result = _build_package_size_census(by_file)
        assert result[0]["loc"] == 500

    def test_takes_max_loc_from_multiple_structural(self):
        by_file = {
            "app/big.py": [
                _issue(file="app/big.py", detail={"loc": 200}),
                _issue(file="app/big.py", detail={"loc": 500}),
            ],
        }
        result = _build_package_size_census(by_file)
        assert result[0]["loc"] == 500

    def test_top_level_file_uses_filename_as_package(self):
        by_file = {
            "script.py": [_issue(file="script.py", detail={"loc": 100})],
        }
        result = _build_package_size_census(by_file)
        assert result[0]["package"] == "script.py"

    def test_deeply_nested_uses_first_component(self):
        by_file = {
            "a/b/c/d.py": [_issue(file="a/b/c/d.py", detail={"loc": 100})],
        }
        result = _build_package_size_census(by_file)
        assert result[0]["package"] == "a"
