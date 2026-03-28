"""Exclude-flag integration tests for Ruff-based external adapters."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from desloppify.languages.python.detectors.ruff_smells import detect_with_ruff_smells
from desloppify.languages.python.detectors.unused import detect_unused


# ── Ruff --exclude integration ───────────────────────────────────────────────


from desloppify.languages.python.detectors.unused import detect_unused  # noqa: E402


class TestRuffSmellsExcludeFlag:
    """Verify ruff smells passes --exclude to subprocess."""

    def test_ruff_smells_passes_exclude_flag(self, tmp_path):
        captured_cmd = []

        def _capture_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            mock_result = MagicMock()
            mock_result.stdout = "[]"
            return mock_result

        fake_dirs = [str(tmp_path / ".venv"), str(tmp_path / "node_modules")]
        with patch("subprocess.run", side_effect=_capture_run), patch(
            "desloppify.languages.python.detectors.ruff_smells._collect_exclude_dirs",
            return_value=fake_dirs,
        ):
            detect_with_ruff_smells(tmp_path)

        assert "--exclude" in captured_cmd
        idx = captured_cmd.index("--exclude")
        exclude_value = captured_cmd[idx + 1]
        assert str(tmp_path / ".venv") in exclude_value
        assert str(tmp_path / "node_modules") in exclude_value

    def test_ruff_smells_no_exclude_when_empty(self, tmp_path):
        captured_cmd = []

        def _capture_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            mock_result = MagicMock()
            mock_result.stdout = "[]"
            return mock_result

        with patch("subprocess.run", side_effect=_capture_run), patch(
            "desloppify.languages.python.detectors.ruff_smells._collect_exclude_dirs",
            return_value=[],
        ):
            detect_with_ruff_smells(tmp_path)

        assert "--exclude" not in captured_cmd


class TestRuffUnusedExcludeFlag:
    """Verify ruff unused passes --exclude to subprocess."""

    def test_ruff_unused_passes_exclude_flag(self, tmp_path):
        captured_cmd = []

        def _capture_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            mock_result = MagicMock()
            mock_result.stdout = "[]"
            return mock_result

        fake_dirs = [str(tmp_path / ".venv"), str(tmp_path / "__pycache__")]
        with patch("subprocess.run", side_effect=_capture_run), patch(
            "desloppify.languages.python.detectors.unused._collect_exclude_dirs",
            return_value=fake_dirs,
        ), patch(
            "desloppify.languages.python.detectors.unused.find_py_files",
            return_value=[],
        ):
            detect_unused(tmp_path)

        assert "--exclude" in captured_cmd
        idx = captured_cmd.index("--exclude")
        exclude_value = captured_cmd[idx + 1]
        assert str(tmp_path / ".venv") in exclude_value
        assert str(tmp_path / "__pycache__") in exclude_value

    def test_ruff_unused_no_exclude_when_empty(self, tmp_path):
        captured_cmd = []

        def _capture_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            mock_result = MagicMock()
            mock_result.stdout = "[]"
            return mock_result

        with patch("subprocess.run", side_effect=_capture_run), patch(
            "desloppify.languages.python.detectors.unused._collect_exclude_dirs",
            return_value=[],
        ), patch(
            "desloppify.languages.python.detectors.unused.find_py_files",
            return_value=[],
        ):
            detect_unused(tmp_path)

        assert "--exclude" not in captured_cmd
