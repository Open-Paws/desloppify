"""Direct tests for shared facade detector helpers.

Phase 2A: Facade detector defaults to a practical importer ceiling while
still allowing explicit overrides for broader scans.
"""

from __future__ import annotations

from desloppify.languages._framework.facade_common import (
    facade_tier_confidence,
    detect_reexport_facades_common,
)

# ── facade_tier_confidence ──────────────────────────────


class TestFacadeTierConfidence:
    """Tier and confidence assignment based on importer count."""

    def test_low_importers_tier_2_high(self):
        tier, conf = facade_tier_confidence(0)
        assert tier == 2
        assert conf == "high"

    def test_five_importers_tier_2_high(self):
        tier, conf = facade_tier_confidence(5)
        assert tier == 2
        assert conf == "high"

    def test_six_importers_tier_3_medium(self):
        tier, conf = facade_tier_confidence(6)
        assert tier == 3
        assert conf == "medium"

    def test_twenty_importers_tier_3_medium(self):
        tier, conf = facade_tier_confidence(20)
        assert tier == 3
        assert conf == "medium"

    def test_over_twenty_importers_tier_4_medium(self):
        tier, conf = facade_tier_confidence(21)
        assert tier == 4
        assert conf == "medium"



# ── detect_reexport_facades_common ───────────────────────


class TestDetectReexportFacadesCommon:
    """Shared facade detection logic with tier/confidence in output."""

    def test_entries_include_tier_and_confidence(self):
        graph = {
            "a.py": {"importer_count": 0},
        }

        def fake_is_facade(path: str) -> dict | None:
            return {"loc": 10, "imports_from": ["pkg.a"]}

        entries, total = detect_reexport_facades_common(
            graph, is_facade_fn=fake_is_facade
        )
        assert len(entries) == 1
        assert entries[0]["tier"] == 2
        assert entries[0]["confidence"] == "high"
        assert entries[0]["kind"] == "file"

    def test_tier_scales_with_importer_count(self):
        graph = {
            "low.py": {"importer_count": 3},
            "mid.py": {"importer_count": 15},
            "high.py": {"importer_count": 50},
        }

        def always_facade(path: str) -> dict | None:
            return {"loc": 10, "imports_from": ["pkg"]}

        entries, _ = detect_reexport_facades_common(
            graph, is_facade_fn=always_facade, max_importers=100
        )
        by_file = {e["file"]: e for e in entries}

        assert by_file["low.py"]["tier"] == 2
        assert by_file["mid.py"]["tier"] == 3
        assert by_file["high.py"]["tier"] == 4

    def test_high_importer_count_filtered_by_default_ceiling(self):
        """Default max_importers ceiling suppresses very high-importer facades."""
        graph = {
            "big.py": {"importer_count": 500},
        }

        def always_facade(path: str) -> dict | None:
            return {"loc": 20, "imports_from": ["pkg"]}

        entries, total = detect_reexport_facades_common(
            graph, is_facade_fn=always_facade
        )
        assert total == 1
        assert entries == []

    def test_non_facades_excluded(self):
        graph = {
            "a.py": {"importer_count": 0},
            "b.py": {"importer_count": 0},
        }

        def selective(path: str) -> dict | None:
            if path == "a.py":
                return {"loc": 10, "imports_from": ["pkg.a"]}
            return None

        entries, total = detect_reexport_facades_common(
            graph, is_facade_fn=selective
        )
        assert total == 2
        assert len(entries) == 1
        assert entries[0]["file"] == "a.py"

    def test_empty_graph(self):
        entries, total = detect_reexport_facades_common(
            {}, is_facade_fn=lambda p: None
        )
        assert total == 0
        assert entries == []

    def test_entry_shape(self):
        graph = {"mod.py": {"importer_count": 7}}

        def facade(path: str) -> dict | None:
            return {"loc": 15, "imports_from": ["a", "b"]}

        entries, _ = detect_reexport_facades_common(
            graph, is_facade_fn=facade
        )
        e = entries[0]
        assert e["file"] == "mod.py"
        assert e["loc"] == 15
        assert e["importers"] == 7
        assert e["imports_from"] == ["a", "b"]
        assert e["kind"] == "file"
        assert e["tier"] == 3
        assert e["confidence"] == "medium"
