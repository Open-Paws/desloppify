"""Direct coverage tests for test-coverage issue facade aliases."""

from __future__ import annotations

import desloppify.engine.detectors.test_coverage._issue_gaps as gaps_mod
import desloppify.engine.detectors.test_coverage._issue_generation as gen_mod
import desloppify.engine.detectors.test_coverage._issue_quality as quality_mod
import desloppify.engine.detectors.test_coverage.issues as issues_mod


def test_issue_facade_aliases_point_to_underlying_helpers() -> None:
    assert issues_mod._generate_issues is gen_mod.generate_issues
    assert issues_mod._quality_issue_item is quality_mod.quality_issue_item
    assert issues_mod._quality_issue_rank is quality_mod.quality_issue_rank
    assert issues_mod._select_direct_test_quality_issue is quality_mod.select_direct_test_quality_issue
    assert issues_mod._transitive_coverage_gap_issue is gaps_mod.transitive_coverage_gap_issue
    assert issues_mod._untested_module_issue is gaps_mod.untested_module_issue


def test_quality_issue_alias_helpers_generate_expected_issue() -> None:
    issue = issues_mod._quality_issue_item(
        prod_file="src/mod.py",
        test_file="tests/test_mod.py",
        quality={"quality": "assertion_free", "test_functions": 2, "assertions": 0},
        loc_weight=3.1,
    )

    assert issue is not None
    assert issue["name"].startswith("assertion_free::")
    assert issue["detail"]["kind"] == "assertion_free_test"
    assert issues_mod._quality_issue_rank("assertion_free") > issues_mod._quality_issue_rank("smoke")


def test_gap_issue_alias_helpers_build_expected_payloads() -> None:
    transitive = issues_mod._transitive_coverage_gap_issue(
        file_path="src/a.py",
        loc=120,
        importer_count=4,
        loc_weight=10.0,
        complexity=0.0,
    )
    untested = issues_mod._untested_module_issue(
        file_path="src/b.py",
        loc=95,
        importer_count=12,
        loc_weight=9.0,
        complexity=0.0,
    )

    assert transitive["name"] == "transitive_only"
    assert transitive["detail"]["kind"] == "transitive_only"
    assert untested["name"] == "untested_critical"
    assert untested["tier"] == 2


def test_select_direct_test_quality_issue_alias_prefers_most_severe() -> None:
    issue = issues_mod._select_direct_test_quality_issue(
        prod_file="src/a.py",
        related_tests=["tests/a.test.ts", "tests/b.test.ts"],
        test_quality={
            "tests/a.test.ts": {
                "quality": "smoke",
                "assertions": 1,
                "test_functions": 2,
                "mocks": 0,
                "snapshots": 0,
            },
            "tests/b.test.ts": {
                "quality": "placeholder_smoke",
                "assertions": 1,
                "test_functions": 3,
                "mocks": 0,
                "snapshots": 0,
            },
        },
        loc_weight=8.0,
    )

    assert issue is not None
    assert issue["detail"]["kind"] == "placeholder_test"
