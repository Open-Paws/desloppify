"""Integration/regression tests for security detector registration and scoring behavior."""

from __future__ import annotations

from desloppify.base.registry import _DISPLAY_ORDER, DETECTORS, dimension_action_type
from desloppify.engine._scoring.policy.core import (
    DIMENSIONS,
    FILE_BASED_DETECTORS,
    SECURITY_EXCLUDED_ZONES,
)
from desloppify.engine._scoring.results.core import compute_dimension_scores
from desloppify.engine.policy.zones import ZONE_POLICIES, Zone
from desloppify.intelligence.narrative.headline import compute_headline


# ═══════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════


class TestSecurityRegistry:
    """Verify security detector is properly registered."""

    def test_detector_in_registry(self):
        assert "security" in DETECTORS
        meta = DETECTORS["security"]
        assert meta.dimension == "Security"
        assert meta.action_type == "manual_fix"

    def test_detector_in_display_order(self):
        assert "security" in _DISPLAY_ORDER

    def test_security_in_file_based_detectors(self):
        assert "security" in FILE_BASED_DETECTORS

    def test_security_dimension_exists(self):
        dim_names = [d.name for d in DIMENSIONS]
        assert "Security" in dim_names
        security_dim = [d for d in DIMENSIONS if d.name == "Security"][0]
        assert security_dim.tier == 4
        assert "security" in security_dim.detectors

    def test_dimension_action_type(self):
        """dimension_action_type returns correct labels for known dimensions."""
        assert dimension_action_type("Code quality") == "autofix"
        assert dimension_action_type("File health") == "refactor"
        assert (
            dimension_action_type("Security") == "move"
        )  # cycles detector is reorganize


class TestSecurityDimensionScoring:
    """Verify security issues affect the Security dimension score."""

    def test_security_dimension_scoring(self):
        issues = {}
        for i in range(5):
            fid = f"security::test{i}.py::security::check::{i}"
            issues[fid] = {
                "id": fid,
                "detector": "security",
                "file": f"test{i}.py",
                "tier": 2,
                "confidence": "high",
                "status": "open",
                "zone": "production",
            }
        potentials = {"security": 100}
        scores = compute_dimension_scores(issues, potentials)
        assert "Security" in scores
        assert scores["Security"]["score"] < 100.0
        assert scores["Security"]["failing"] == 5

    def test_security_zone_test_excluded(self):
        """Security issues in test zone are skipped from scoring."""
        fid = "security::test_file.py::security::check::1"
        issues = {
            fid: {
                "id": fid,
                "detector": "security",
                "file": "test_file.py",
                "tier": 2,
                "confidence": "high",
                "status": "open",
                "zone": "test",
            },
        }
        potentials = {"security": 10}
        scores = compute_dimension_scores(issues, potentials)
        assert "Security" in scores
        assert scores["Security"]["failing"] == 0
        assert scores["Security"]["score"] == 100.0

    def test_security_zone_config_excluded(self):
        """Security issues in config zone are skipped from scoring."""
        fid = "security::config.py::security::check::1"
        issues = {
            fid: {
                "id": fid,
                "detector": "security",
                "file": "config.py",
                "tier": 2,
                "confidence": "high",
                "status": "open",
                "zone": "config",
            },
        }
        potentials = {"security": 10}
        scores = compute_dimension_scores(issues, potentials)
        assert "Security" in scores
        assert scores["Security"]["failing"] == 0
        assert scores["Security"]["score"] == 100.0

    def test_security_zone_vendor_excluded(self):
        """Security issues in vendor zone ARE skipped from scoring."""
        fid = "security::vendor/lib.py::security::check::1"
        issues = {
            fid: {
                "id": fid,
                "detector": "security",
                "file": "vendor/lib.py",
                "tier": 2,
                "confidence": "high",
                "status": "open",
                "zone": "vendor",
            },
        }
        potentials = {"security": 10}
        scores = compute_dimension_scores(issues, potentials)
        assert "Security" in scores
        assert scores["Security"]["failing"] == 0
        assert scores["Security"]["score"] == 100.0

    def test_security_zone_generated_excluded(self):
        """Security issues in generated zone ARE skipped from scoring."""
        fid = "security::gen.py::security::check::1"
        issues = {
            fid: {
                "id": fid,
                "detector": "security",
                "file": "gen.py",
                "tier": 2,
                "confidence": "high",
                "status": "open",
                "zone": "generated",
            },
        }
        potentials = {"security": 10}
        scores = compute_dimension_scores(issues, potentials)
        assert "Security" in scores
        assert scores["Security"]["failing"] == 0

    def test_security_excluded_zones_constant(self):
        assert SECURITY_EXCLUDED_ZONES == {"test", "config", "generated", "vendor"}


class TestSecurityZonePolicy:
    """Verify zone policies for security detector."""

    def test_security_skipped_in_test_zone(self):
        policy = ZONE_POLICIES[Zone.TEST]
        assert "security" in policy.skip_detectors

    def test_security_skipped_in_config_zone(self):
        policy = ZONE_POLICIES[Zone.CONFIG]
        assert "security" in policy.skip_detectors

    def test_security_not_skipped_in_script_zone(self):
        policy = ZONE_POLICIES[Zone.SCRIPT]
        assert "security" not in policy.skip_detectors

    def test_security_skipped_in_generated_zone(self):
        policy = ZONE_POLICIES[Zone.GENERATED]
        assert "security" in policy.skip_detectors

    def test_security_skipped_in_vendor_zone(self):
        policy = ZONE_POLICIES[Zone.VENDOR]
        assert "security" in policy.skip_detectors


class TestSecurityInNarrative:
    """Verify security issues appear in narrative headline."""

    def test_security_in_narrative_headline(self):
        result = compute_headline(
            "middle_grind",
            {"lowest_dimensions": []},
            {},
            None,
            None,
            85.0,
            85.0,
            {"open": 5},
            [],
            open_by_detector={"security": 3},
        )
        assert result is not None
        assert "\u26a0 3 security issues" in result

    def test_no_security_no_prefix(self):
        result = compute_headline(
            "first_scan",
            {},
            {},
            None,
            None,
            85.0,
            85.0,
            {"open": 5},
            [],
            open_by_detector={"unused": 5},
        )
        assert result is not None
        assert "\u26a0" not in result

    def test_security_with_milestone(self):
        result = compute_headline(
            "middle_grind",
            {},
            {},
            "Great job!",
            None,
            85.0,
            85.0,
            {"open": 5},
            [],
            open_by_detector={"security": 1},
        )
        assert result is not None
        assert "\u26a0 1 security issue" in result
        assert "Great job!" in result

    def test_security_singular(self):
        result = compute_headline(
            "middle_grind",
            {"lowest_dimensions": []},
            {},
            None,
            None,
            85.0,
            85.0,
            {"open": 1},
            [],
            open_by_detector={"security": 1},
        )
        assert result is not None
        assert "1 security issue " in result
        assert "issues" not in result.split("security issue")[0]
