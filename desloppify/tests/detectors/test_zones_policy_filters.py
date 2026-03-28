"""Zone policy filtering and potential-adjustment tests."""

import pytest

from desloppify.engine.policy.zones import (
    COMMON_ZONE_RULES,
    FileZoneMap,
    Zone,
    ZonePolicy,
    ZoneRule,
    adjust_potential,
    filter_entries,
    should_skip_issue,
)


class TestAdjustPotential:
    """Tests for the adjust_potential helper."""

    def test_with_zone_map(self):
        """Subtracts non-production count from total."""
        files = [
            "src/app.py",
            "tests/test_app.py",
            "vendor/lib.py",
        ]
        zm = FileZoneMap(files, COMMON_ZONE_RULES)
        # non_production = test(1) + vendor(1) = 2
        result = adjust_potential(zm, 10)
        assert result == 8

    def test_with_zone_map_all_production(self):
        """No adjustment when all files are production."""
        files = ["src/app.py", "src/utils.py"]
        zm = FileZoneMap(files, COMMON_ZONE_RULES)
        assert adjust_potential(zm, 5) == 5

    def test_with_zone_map_clamps_to_zero(self):
        """Result is clamped to 0 if non-production exceeds total."""
        files = ["tests/a.py", "tests/b.py", "vendor/c.py"]
        zm = FileZoneMap(files, COMMON_ZONE_RULES)
        # All 3 are non-production, total is 1
        assert adjust_potential(zm, 1) == 0

    def test_none_zone_map(self):
        """Returns total unchanged when zone_map is None."""
        assert adjust_potential(None, 42) == 42

    def test_zero_total(self):
        """Zero total stays zero."""
        files = ["src/app.py"]
        zm = FileZoneMap(files, COMMON_ZONE_RULES)
        assert adjust_potential(zm, 0) == 0


# ── should_skip_issue() ────────────────────────────────────


class TestShouldSkipIssue:
    """Tests for the should_skip_issue helper."""

    @pytest.fixture
    def zone_map(self):
        files = [
            "src/app.py",
            "tests/test_app.py",
            "scripts/deploy.sh",
            "vendor/lib.py",
        ]
        return FileZoneMap(files, COMMON_ZONE_RULES)

    def test_skip_in_test_zone(self, zone_map):
        """Detectors in TEST skip_detectors are skipped for test files."""
        assert should_skip_issue(zone_map, "tests/test_app.py", "dupes") is True
        assert should_skip_issue(zone_map, "tests/test_app.py", "coupling") is True
        assert (
            should_skip_issue(zone_map, "tests/test_app.py", "test_coverage") is True
        )
        assert should_skip_issue(zone_map, "tests/test_app.py", "security") is True

    def test_allow_in_test_zone(self, zone_map):
        """Detectors NOT in TEST skip_detectors are allowed for test files."""
        assert should_skip_issue(zone_map, "tests/test_app.py", "unused") is False
        assert should_skip_issue(zone_map, "tests/test_app.py", "logs") is False

    def test_production_never_skips(self, zone_map):
        """PRODUCTION zone never skips any detector."""
        assert should_skip_issue(zone_map, "src/app.py", "dupes") is False
        assert should_skip_issue(zone_map, "src/app.py", "smells") is False
        assert should_skip_issue(zone_map, "src/app.py", "coupling") is False

    def test_vendor_skips_most(self, zone_map):
        """VENDOR zone skips most detectors."""
        assert should_skip_issue(zone_map, "vendor/lib.py", "unused") is True
        assert should_skip_issue(zone_map, "vendor/lib.py", "smells") is True
        assert should_skip_issue(zone_map, "vendor/lib.py", "naming") is True
        assert should_skip_issue(zone_map, "vendor/lib.py", "test_coverage") is True

    def test_script_skips_subset(self, zone_map):
        """SCRIPT zone skips only its specific detectors."""
        assert should_skip_issue(zone_map, "scripts/deploy.sh", "coupling") is True
        assert should_skip_issue(zone_map, "scripts/deploy.sh", "facade") is True
        # But not smells
        assert should_skip_issue(zone_map, "scripts/deploy.sh", "smells") is False

    def test_none_zone_map_never_skips(self):
        """Returns False when zone_map is None (backward compat)."""
        assert should_skip_issue(None, "tests/test_app.py", "dupes") is False

    def test_unknown_file_defaults_production(self, zone_map):
        """File not in the map is treated as PRODUCTION (no skips)."""
        assert should_skip_issue(zone_map, "unknown.py", "dupes") is False


# ── filter_entries() ─────────────────────────────────────────


class TestFilterEntries:
    """Tests for the filter_entries helper."""

    @pytest.fixture
    def zone_map(self):
        files = [
            "src/app.py",
            "tests/test_app.py",
            "vendor/lib.py",
        ]
        return FileZoneMap(files, COMMON_ZONE_RULES)

    def test_removes_skipped_entries(self, zone_map):
        """Entries from skipped zones are removed."""
        entries = [
            {"file": "src/app.py", "msg": "dupe 1"},
            {"file": "tests/test_app.py", "msg": "dupe 2"},
        ]
        result = filter_entries(zone_map, entries, "dupes")
        assert len(result) == 1
        assert result[0]["file"] == "src/app.py"

    def test_keeps_allowed_entries(self, zone_map):
        """Entries from allowed zones are kept."""
        entries = [
            {"file": "src/app.py", "msg": "unused 1"},
            {"file": "tests/test_app.py", "msg": "unused 2"},
        ]
        # "unused" is not skipped in TEST zone
        result = filter_entries(zone_map, entries, "unused")
        assert len(result) == 2

    def test_vendor_entries_filtered(self, zone_map):
        """Entries from vendor zone are filtered for smells detector."""
        entries = [
            {"file": "src/app.py", "msg": "smell 1"},
            {"file": "vendor/lib.py", "msg": "smell 2"},
        ]
        result = filter_entries(zone_map, entries, "smells")
        assert len(result) == 1
        assert result[0]["file"] == "src/app.py"

    def test_custom_file_key(self, zone_map):
        """Custom file_key extracts the path from a different key."""
        entries = [
            {"path": "src/app.py", "msg": "ok"},
            {"path": "tests/test_app.py", "msg": "skip"},
        ]
        result = filter_entries(zone_map, entries, "dupes", file_key="path")
        assert len(result) == 1
        assert result[0]["path"] == "src/app.py"

    def test_list_file_key(self, zone_map):
        """When file_key points to a list, checks the first element."""
        entries = [
            {"files": ["src/app.py", "src/utils.py"], "msg": "cycle 1"},
            {"files": ["tests/test_app.py", "tests/test_utils.py"], "msg": "cycle 2"},
        ]
        result = filter_entries(zone_map, entries, "coupling", file_key="files")
        assert len(result) == 1
        assert result[0]["msg"] == "cycle 1"

    def test_none_zone_map_noop(self):
        """Returns entries unchanged when zone_map is None."""
        entries = [
            {"file": "tests/test_app.py", "msg": "dupe"},
        ]
        result = filter_entries(None, entries, "dupes")
        assert result == entries

    def test_empty_entries(self, zone_map):
        """Empty entries list returns empty list."""
        assert filter_entries(zone_map, [], "dupes") == []

    def test_all_entries_filtered(self, zone_map):
        """All entries removed when all are in skipped zones."""
        entries = [
            {"file": "tests/test_app.py", "msg": "dupe 1"},
        ]
        result = filter_entries(zone_map, entries, "dupes")
        assert result == []


# ── ZoneRule dataclass ───────────────────────────────────────


class TestZoneRule:
    """Tests for the ZoneRule dataclass."""

    def test_construction(self):
        """ZoneRule stores zone and patterns."""
        rule = ZoneRule(Zone.TEST, ["/test/", ".spec."])
        assert rule.zone == Zone.TEST
        assert rule.patterns == ["/test/", ".spec."]


# ── ZonePolicy dataclass ────────────────────────────────────


class TestZonePolicy:
    """Tests for the ZonePolicy dataclass."""

    def test_default_construction(self):
        """Default ZonePolicy has empty sets and False exclude."""
        policy = ZonePolicy()
        assert policy.skip_detectors == set()
        assert policy.downgrade_detectors == set()
        assert policy.exclude_from_score is False

    def test_custom_construction(self):
        """ZonePolicy with custom values."""
        policy = ZonePolicy(
            skip_detectors={"unused", "smells"},
            downgrade_detectors={"structural"},
            exclude_from_score=True,
        )
        assert policy.skip_detectors == {"unused", "smells"}
        assert policy.downgrade_detectors == {"structural"}
        assert policy.exclude_from_score is True
