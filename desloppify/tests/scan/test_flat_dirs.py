"""Tests for desloppify.engine.detectors.flat_dirs — flat directory detection."""

import pytest

from desloppify.engine.detectors.flat_dirs import (
    FlatDirDetectionConfig,
    detect_flat_dirs,
    format_flat_dir_summary,
)


class TestDetectFlatDirs:
    def test_rejects_mixed_config_and_legacy_kwargs(self, tmp_path):
        with pytest.raises(TypeError):
            detect_flat_dirs(
                tmp_path,
                file_finder=lambda p: [],
                config=FlatDirDetectionConfig(),
                threshold=20,
            )

    def test_dir_over_threshold_detected(self, tmp_path):
        d = tmp_path / "components"
        d.mkdir()
        files = []
        for i in range(25):
            f = d / f"comp_{i}.tsx"
            f.write_text(f"export const Comp{i} = () => null;")
            files.append(str(f))

        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: files,
            threshold=20,
        )
        assert len(entries) == 1
        assert entries[0]["directory"] == str(d)
        assert entries[0]["file_count"] == 25
        assert total == 1

    def test_dir_under_threshold_not_detected(self, tmp_path):
        d = tmp_path / "utils"
        d.mkdir()
        files = []
        for i in range(5):
            f = d / f"util_{i}.py"
            f.write_text(f"x = {i}")
            files.append(str(f))

        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: files,
            threshold=20,
        )
        assert entries == []
        assert total == 1

    def test_dir_at_threshold_detected(self, tmp_path):
        """A dir with exactly threshold files SHOULD be flagged (uses >=)."""
        d = tmp_path / "exact"
        d.mkdir()
        files = []
        for i in range(20):
            f = d / f"file_{i}.py"
            f.write_text(f"x = {i}")
            files.append(str(f))

        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: files,
            threshold=20,
        )
        assert len(entries) == 1
        assert entries[0]["file_count"] == 20

    def test_custom_threshold(self, tmp_path):
        d = tmp_path / "small_dir"
        d.mkdir()
        files = []
        for i in range(5):
            f = d / f"file_{i}.py"
            f.write_text(f"x = {i}")
            files.append(str(f))

        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: files,
            threshold=3,
        )
        assert len(entries) == 1

    def test_multiple_dirs(self, tmp_path):
        d1 = tmp_path / "dir1"
        d1.mkdir()
        d2 = tmp_path / "dir2"
        d2.mkdir()
        files = []
        for i in range(25):
            f = d1 / f"file_{i}.py"
            f.write_text(f"x = {i}")
            files.append(str(f))
        for i in range(30):
            f = d2 / f"file_{i}.py"
            f.write_text(f"x = {i}")
            files.append(str(f))

        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: files,
            threshold=20,
        )
        assert len(entries) == 2
        assert total == 2
        # Sorted by file_count descending
        assert entries[0]["file_count"] >= entries[1]["file_count"]

    def test_empty_file_list(self, tmp_path):
        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: [],
            threshold=20,
        )
        assert entries == []
        assert total == 0

    def test_files_across_many_dirs(self, tmp_path):
        """Many directories each with few files should not trigger."""
        files = []
        for d_idx in range(10):
            d = tmp_path / f"dir_{d_idx}"
            d.mkdir()
            for f_idx in range(3):
                f = d / f"file_{f_idx}.py"
                f.write_text(f"x = {f_idx}")
                files.append(str(f))

        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: files,
            threshold=20,
        )
        assert entries == []
        assert total == 10

    def test_entry_structure(self, tmp_path):
        d = tmp_path / "components"
        d.mkdir()
        files = []
        for i in range(25):
            f = d / f"comp_{i}.tsx"
            f.write_text(f"export const Comp{i} = () => null;")
            files.append(str(f))

        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: files,
            threshold=20,
        )
        entry = entries[0]
        assert "directory" in entry
        assert "file_count" in entry
        assert "child_dir_count" in entry
        assert "combined_score" in entry
        assert isinstance(entry["file_count"], int)
        assert isinstance(entry["child_dir_count"], int)
        assert isinstance(entry["combined_score"], int)

    def test_sorted_by_file_count_descending(self, tmp_path):
        d1 = tmp_path / "small"
        d1.mkdir()
        d2 = tmp_path / "large"
        d2.mkdir()
        files = []
        for i in range(22):
            f = d1 / f"f_{i}.py"
            f.write_text("")
            files.append(str(f))
        for i in range(40):
            f = d2 / f"f_{i}.py"
            f.write_text("")
            files.append(str(f))

        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: files,
            threshold=20,
        )
        assert entries[0]["file_count"] > entries[1]["file_count"]

    def test_child_directory_threshold_detected(self, tmp_path):
        parent = tmp_path / "parent"
        parent.mkdir()
        files = []
        # Keep file count low, but fan out into many child dirs.
        for i in range(10):
            child = parent / f"child_{i}"
            child.mkdir()
            f = child / "index.ts"
            f.write_text("export const x = 1;")
            files.append(str(f))
        # Add one file in the parent so it appears in directory counts.
        parent_file = parent / "root.ts"
        parent_file.write_text("export const y = 2;")
        files.append(str(parent_file))

        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: files,
            threshold=20,
            child_dir_threshold=10,
            combined_threshold=999,
        )
        assert total >= 1
        assert any(
            entry["directory"] == str(parent)
            and entry["file_count"] == 1
            and entry["child_dir_count"] == 10
            for entry in entries
        )

    def test_combined_threshold_detected(self, tmp_path):
        parent = tmp_path / "combined"
        parent.mkdir()
        files = []
        for i in range(9):
            f = parent / f"file_{i}.ts"
            f.write_text("export const v = 1;")
            files.append(str(f))
        for i in range(7):
            child = parent / f"folder_{i}"
            child.mkdir()
            f = child / "nested.ts"
            f.write_text("export const nested = 1;")
            files.append(str(f))

        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: files,
            threshold=20,
            child_dir_threshold=999,
            combined_threshold=30,
            child_dir_weight=3,
        )
        assert total >= 1
        assert any(
            entry["directory"] == str(parent)
            and entry["file_count"] == 9
            and entry["child_dir_count"] == 7
            and entry["combined_score"] == 30
            for entry in entries
        )

    def test_fragmented_parent_detected_with_many_sparse_children(self, tmp_path):
        parent = tmp_path / "parent"
        parent.mkdir()
        files = []
        parent_file = parent / "index.ts"
        parent_file.write_text("export const parent = true;")
        files.append(str(parent_file))

        for i in range(9):
            child = parent / f"child_{i}"
            child.mkdir()
            child_file = child / "single.ts"
            child_file.write_text("export const single = true;")
            files.append(str(child_file))

        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: files,
            threshold=999,
            child_dir_threshold=999,
            combined_threshold=999,
        )

        assert total >= 1
        assert len(entries) == 1
        entry = entries[0]
        assert entry["directory"] == str(parent)
        assert entry["kind"] == "fragmented"
        assert entry["child_dir_count"] == 9
        assert entry["sparse_child_count"] == 9
        assert entry["sparse_child_ratio"] == 1.0

    def test_fragmented_parent_not_detected_when_children_are_not_sparse(self, tmp_path):
        parent = tmp_path / "parent"
        parent.mkdir()
        files = []
        parent_file = parent / "index.ts"
        parent_file.write_text("export const parent = true;")
        files.append(str(parent_file))

        for i in range(9):
            child = parent / f"child_{i}"
            child.mkdir()
            for j in range(2):
                child_file = child / f"file_{j}.ts"
                child_file.write_text("export const item = true;")
                files.append(str(child_file))

        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: files,
            threshold=999,
            child_dir_threshold=999,
            combined_threshold=999,
        )

        assert total >= 1
        assert entries == []

    def test_fragmented_parent_not_detected_when_sparse_ratio_low(self, tmp_path):
        parent = tmp_path / "parent"
        parent.mkdir()
        files = []
        parent_file = parent / "index.ts"
        parent_file.write_text("export const parent = true;")
        files.append(str(parent_file))

        for i in range(9):
            child = parent / f"child_{i}"
            child.mkdir()
            if i < 5:
                child_file = child / "single.ts"
                child_file.write_text("export const single = true;")
                files.append(str(child_file))
            else:
                for j in range(2):
                    child_file = child / f"file_{j}.ts"
                    child_file.write_text("export const item = true;")
                    files.append(str(child_file))

        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: files,
            threshold=999,
            child_dir_threshold=999,
            combined_threshold=999,
        )

        assert total >= 1
        assert entries == []

    def test_thin_wrapper_detected_when_parent_has_high_fanout(self, tmp_path):
        shared = tmp_path / "shared"
        shared.mkdir()
        files = []

        # Parent fan-out: many sibling dirs with files.
        for i in range(10):
            sibling = shared / f"group_{i}"
            sibling.mkdir()
            sibling_file = sibling / "entry.ts"
            sibling_file.write_text("export const sibling = true;")
            files.append(str(sibling_file))

        # Thin generic wrapper: utils -> helper.ts (single child dir, no local files)
        wrapper = shared / "utils"
        wrapper.mkdir()
        child = wrapper / "helper"
        child.mkdir()
        child_file = child / "helper.ts"
        child_file.write_text("export const helper = true;")
        files.append(str(child_file))

        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: files,
            threshold=999,
            child_dir_threshold=999,
            combined_threshold=999,
            sparse_parent_child_threshold=999,
        )

        assert total >= 1
        assert any(
            entry["directory"] == str(wrapper)
            and entry["kind"] == "thin_wrapper"
            and entry["parent_sibling_count"] >= 10
            and entry["wrapper_item_count"] == 1
            for entry in entries
        )

    def test_thin_wrapper_not_detected_when_parent_fanout_is_low(self, tmp_path):
        shared = tmp_path / "shared"
        shared.mkdir()
        files = []

        for i in range(3):
            sibling = shared / f"group_{i}"
            sibling.mkdir()
            sibling_file = sibling / "entry.ts"
            sibling_file.write_text("export const sibling = true;")
            files.append(str(sibling_file))

        wrapper = shared / "utils"
        wrapper.mkdir()
        child = wrapper / "helper"
        child.mkdir()
        child_file = child / "helper.ts"
        child_file.write_text("export const helper = true;")
        files.append(str(child_file))

        entries, total = detect_flat_dirs(
            tmp_path,
            file_finder=lambda p: files,
            threshold=999,
            child_dir_threshold=999,
            combined_threshold=999,
            sparse_parent_child_threshold=999,
            thin_wrapper_parent_sibling_threshold=10,
        )

        assert total >= 1
        assert not any(entry.get("kind") == "thin_wrapper" for entry in entries)

    def test_format_summary_uses_fragmentation_language(self):
        summary = format_flat_dir_summary(
            {
                "kind": "fragmented",
                "file_count": 1,
                "child_dir_count": 9,
                "combined_score": 28,
                "sparse_child_count": 9,
                "sparse_child_file_threshold": 1,
            }
        )
        assert "Directory fragmentation" in summary
        assert "9/9 child dirs have <=" in summary

    def test_format_summary_uses_thin_wrapper_language(self):
        summary = format_flat_dir_summary(
            {
                "kind": "thin_wrapper",
                "file_count": 0,
                "child_dir_count": 1,
                "wrapper_item_count": 1,
                "parent_sibling_count": 12,
            }
        )
        assert "Thin wrapper directory" in summary
        assert "parent with 12 sibling dirs" in summary
