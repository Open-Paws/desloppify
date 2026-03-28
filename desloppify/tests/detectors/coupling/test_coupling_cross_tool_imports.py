"""Cross-tool import detector tests for coupling analysis."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from desloppify.engine.detectors.coupling import detect_cross_tool_imports

# Fixed prefixes for all tests — simulate a /project/src layout.
SHARED_PREFIX = "/project/src/shared/"
TOOLS_PREFIX = "/project/src/tools/"


def _graph_entry(
    *,
    imports: set[str] | None = None,
    importer_count: int = 0,
    importers: list[str] | None = None,
) -> dict:
    """Build a minimal graph node dict."""
    return {
        "imports": imports or set(),
        "importer_count": importer_count,
        "importers": importers or [],
    }


def _write_file(path: Path, lines: int = 20) -> Path:
    """Write a dummy file with the given number of lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"line {i}" for i in range(lines)))
    return path


class TestDetectCrossToolImports:
    """Tests for tools/A importing from tools/B detection."""

    def test_finds_cross_tool_imports(self):
        """Importing from a different tool is a cross-tool violation."""
        graph = {
            f"{TOOLS_PREFIX}editor/main.ts": _graph_entry(
                imports={f"{TOOLS_PREFIX}viewer/utils.ts"},
            ),
        }

        with patch(
            "desloppify.engine.detectors.coupling.rel",
            side_effect=lambda p: p.replace("/project/", ""),
        ):
            entries, total_edges = detect_cross_tool_imports(
                Path("/project"), graph, TOOLS_PREFIX
            )

        assert len(entries) == 1
        assert entries[0]["source_tool"] == "editor"
        assert entries[0]["target_tool"] == "viewer"
        assert entries[0]["direction"] == "tools\u2192tools"
        assert total_edges.eligible_edges == 1

    def test_same_tool_imports_counted_as_edges_not_violations(self):
        """Same-tool imports count toward total_edges but are not violations."""
        graph = {
            f"{TOOLS_PREFIX}editor/main.ts": _graph_entry(
                imports={f"{TOOLS_PREFIX}editor/helpers.ts"},
            ),
        }

        with patch(
            "desloppify.engine.detectors.coupling.rel",
            side_effect=lambda p: p.replace("/project/", ""),
        ):
            entries, total_edges = detect_cross_tool_imports(
                Path("/project"), graph, TOOLS_PREFIX
            )

        assert entries == []
        assert total_edges.eligible_edges == 1  # edge counted, but not a violation

    def test_returns_entries_and_total_edges(self):
        """Return tuple is (violation_entries, total_cross_tool_edges)."""
        graph = {
            f"{TOOLS_PREFIX}editor/a.ts": _graph_entry(
                imports={
                    f"{TOOLS_PREFIX}viewer/b.ts",  # cross-tool
                    f"{TOOLS_PREFIX}editor/c.ts",  # same-tool
                },
            ),
        }

        with patch(
            "desloppify.engine.detectors.coupling.rel",
            side_effect=lambda p: p.replace("/project/", ""),
        ):
            entries, total_edges = detect_cross_tool_imports(
                Path("/project"), graph, TOOLS_PREFIX
            )

        assert len(entries) == 1  # only the cross-tool import
        assert total_edges.eligible_edges == 2  # both edges counted

    def test_non_tools_files_ignored(self):
        """Files outside tools/ prefix are not checked."""
        graph = {
            f"{SHARED_PREFIX}utils.ts": _graph_entry(
                imports={f"{TOOLS_PREFIX}editor/a.ts"},
            ),
        }

        with patch(
            "desloppify.engine.detectors.coupling.rel",
            side_effect=lambda p: p.replace("/project/", ""),
        ):
            entries, total_edges = detect_cross_tool_imports(
                Path("/project"), graph, TOOLS_PREFIX
            )

        assert entries == []
        assert total_edges.eligible_edges == 0

    def test_root_level_tools_file_skipped(self):
        """Files directly under tools/ (no sub-path) are skipped."""
        graph = {
            f"{TOOLS_PREFIX}config.ts": _graph_entry(
                imports={f"{TOOLS_PREFIX}editor/a.ts"},
            ),
        }

        with patch(
            "desloppify.engine.detectors.coupling.rel",
            side_effect=lambda p: p.replace("/project/", ""),
        ):
            entries, total_edges = detect_cross_tool_imports(
                Path("/project"), graph, TOOLS_PREFIX
            )

        assert entries == []
        assert total_edges.eligible_edges == 0

    def test_imports_to_non_tools_not_counted(self):
        """Imports pointing outside tools/ are not counted at all."""
        graph = {
            f"{TOOLS_PREFIX}editor/main.ts": _graph_entry(
                imports={f"{SHARED_PREFIX}utils.ts"},
            ),
        }

        with patch(
            "desloppify.engine.detectors.coupling.rel",
            side_effect=lambda p: p.replace("/project/", ""),
        ):
            entries, total_edges = detect_cross_tool_imports(
                Path("/project"), graph, TOOLS_PREFIX
            )

        assert entries == []
        assert total_edges.eligible_edges == 0

    def test_sorted_by_source_tool_then_file(self):
        """Results are sorted by (source_tool, file)."""
        graph = {
            f"{TOOLS_PREFIX}z-tool/main.ts": _graph_entry(
                imports={f"{TOOLS_PREFIX}editor/a.ts"},
            ),
            f"{TOOLS_PREFIX}alpha/main.ts": _graph_entry(
                imports={f"{TOOLS_PREFIX}editor/b.ts"},
            ),
            f"{TOOLS_PREFIX}alpha/aux.ts": _graph_entry(
                imports={f"{TOOLS_PREFIX}editor/c.ts"},
            ),
        }

        with patch(
            "desloppify.engine.detectors.coupling.rel",
            side_effect=lambda p: p.replace("/project/", ""),
        ):
            entries, total_edges = detect_cross_tool_imports(
                Path("/project"), graph, TOOLS_PREFIX
            )

        assert len(entries) == 3
        # alpha files first (sorted by source_tool), then z-tool
        assert entries[0]["source_tool"] == "alpha"
        assert entries[1]["source_tool"] == "alpha"
        assert entries[2]["source_tool"] == "z-tool"
        # Within alpha, sorted by file path
        assert entries[0]["file"] < entries[1]["file"]

    def test_empty_graph(self):
        """Empty graph returns no entries and zero edges."""
        entries, total_edges = detect_cross_tool_imports(
            Path("/project"), {}, TOOLS_PREFIX
        )
        assert entries == []
        assert total_edges.eligible_edges == 0

    def test_accepts_relative_graph_keys_with_absolute_tools_prefix(self):
        """Relative graph keys still match absolute tools prefixes."""
        graph = {
            "src/tools/editor/main.ts": _graph_entry(
                imports={"src/tools/viewer/utils.ts"},
            ),
        }
        with patch("desloppify.engine.detectors.coupling.rel", side_effect=lambda p: p):
            entries, total_edges = detect_cross_tool_imports(
                Path("/project"), graph, TOOLS_PREFIX
            )
        assert len(entries) == 1
        assert total_edges.eligible_edges == 1
        assert entries[0]["source_tool"] == "editor"
        assert entries[0]["target_tool"] == "viewer"

    def test_rejects_empty_tools_prefix(self):
        """Empty tools prefix is rejected explicitly."""
        with pytest.raises(ValueError, match="tools_prefix"):
            detect_cross_tool_imports(Path("/project"), {}, "")

    def test_multiple_cross_tool_imports_from_same_file(self):
        """A single file importing from multiple other tools creates multiple entries."""
        graph = {
            f"{TOOLS_PREFIX}editor/main.ts": _graph_entry(
                imports={
                    f"{TOOLS_PREFIX}viewer/a.ts",
                    f"{TOOLS_PREFIX}dashboard/b.ts",
                },
            ),
        }

        with patch(
            "desloppify.engine.detectors.coupling.rel",
            side_effect=lambda p: p.replace("/project/", ""),
        ):
            entries, total_edges = detect_cross_tool_imports(
                Path("/project"), graph, TOOLS_PREFIX
            )

        assert len(entries) == 2
        assert total_edges.eligible_edges == 2
        target_tools = {e["target_tool"] for e in entries}
        assert target_tools == {"viewer", "dashboard"}

    def test_bidirectional_cross_tool(self):
        """Cross-tool imports in both directions are both flagged."""
        graph = {
            f"{TOOLS_PREFIX}editor/main.ts": _graph_entry(
                imports={f"{TOOLS_PREFIX}viewer/utils.ts"},
            ),
            f"{TOOLS_PREFIX}viewer/main.ts": _graph_entry(
                imports={f"{TOOLS_PREFIX}editor/helpers.ts"},
            ),
        }

        with patch(
            "desloppify.engine.detectors.coupling.rel",
            side_effect=lambda p: p.replace("/project/", ""),
        ):
            entries, total_edges = detect_cross_tool_imports(
                Path("/project"), graph, TOOLS_PREFIX
            )

        assert len(entries) == 2
        assert total_edges.eligible_edges == 2
        source_tools = {e["source_tool"] for e in entries}
        assert source_tools == {"editor", "viewer"}
