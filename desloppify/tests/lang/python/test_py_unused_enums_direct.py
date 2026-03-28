"""Tests for unused enum detector.

Phase 5A: Detect enum classes with zero external imports.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from desloppify.languages.python.detectors.unused_enums import detect_unused_enums


def _setup_files(tmp_path: Path, files: dict[str, str]) -> list[str]:
    """Create files and return absolute paths for find_py_files mock."""
    paths: list[str] = []
    for name, content in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        paths.append(str(p))
    return paths


def _run(tmp_path, files):
    abs_paths = _setup_files(tmp_path, files)
    with patch(
        "desloppify.languages.python.detectors.unused_enums.find_py_files",
        return_value=abs_paths,
    ):
        return detect_unused_enums(tmp_path)


class TestDetectUnusedEnums:

    def test_unused_enum_detected(self, tmp_path: Path):
        entries, total = _run(tmp_path, {
            "enums.py": (
                "from enum import StrEnum\n"
                "class Status(StrEnum):\n"
                '    ACTIVE = "active"\n'
                '    INACTIVE = "inactive"\n'
            ),
            "main.py": "x = 1\n",
        })
        assert total == 2
        assert len(entries) == 1
        assert entries[0]["name"] == "Status"
        assert entries[0]["member_count"] == 2
        assert entries[0]["line"] == 2

    def test_used_enum_not_reported(self, tmp_path: Path):
        entries, _ = _run(tmp_path, {
            "enums.py": (
                "from enum import StrEnum\n"
                "class Status(StrEnum):\n"
                '    ACTIVE = "active"\n'
            ),
            "main.py": "from enums import Status\n",
        })
        assert len(entries) == 0

    def test_self_usage_not_counted_as_external(self, tmp_path: Path):
        """Enum referenced in its own file doesn't count as externally imported."""
        entries, _ = _run(tmp_path, {
            "enums.py": (
                "from enum import StrEnum\n"
                "class Status(StrEnum):\n"
                '    ACTIVE = "active"\n'
                "x = Status.ACTIVE\n"
            ),
        })
        assert len(entries) == 1

    def test_multiple_enums_reports_only_unused(self, tmp_path: Path):
        entries, _ = _run(tmp_path, {
            "enums.py": (
                "from enum import StrEnum, IntEnum\n"
                "class Used(StrEnum):\n"
                '    A = "a"\n'
                "class Unused(IntEnum):\n"
                "    X = 1\n"
            ),
            "main.py": "from enums import Used\n",
        })
        names = {e["name"] for e in entries}
        assert names == {"Unused"}

    def test_no_enums_returns_empty(self, tmp_path: Path):
        entries, total = _run(tmp_path, {"mod.py": "x = 1\n"})
        assert entries == []
        assert total == 1

    def test_aliased_import_counts_as_used(self, tmp_path: Path):
        """``from enums import Status as S`` still references the name 'Status'."""
        entries, _ = _run(tmp_path, {
            "enums.py": (
                "from enum import StrEnum\n"
                "class Status(StrEnum):\n"
                '    ACTIVE = "active"\n'
            ),
            "main.py": "from enums import Status as S\n",
        })
        assert len(entries) == 0

    def test_same_name_enums_conservatively_marked_used(self, tmp_path: Path):
        """When same enum name exists in multiple files, importing it marks
        all definitions as used (conservative — avoids false positives)."""
        entries, _ = _run(tmp_path, {
            "v1/enums.py": (
                "from enum import StrEnum\n"
                "class Status(StrEnum):\n"
                '    ACTIVE = "active"\n'
            ),
            "v2/enums.py": (
                "from enum import StrEnum\n"
                "class Status(StrEnum):\n"
                '    ACTIVE = "active"\n'
            ),
            "main.py": "from v2.enums import Status\n",
        })
        # Both are conservatively excluded — no false positives.
        assert len(entries) == 0

    def test_star_import_does_not_count(self, tmp_path: Path):
        """Wildcard import doesn't explicitly name the enum — still 'unused'."""
        entries, _ = _run(tmp_path, {
            "enums.py": (
                "from enum import StrEnum\n"
                "class Status(StrEnum):\n"
                '    ACTIVE = "active"\n'
            ),
            "main.py": "from enums import *\n",
        })
        assert len(entries) == 1
