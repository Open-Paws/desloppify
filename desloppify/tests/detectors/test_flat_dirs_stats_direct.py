"""Direct coverage for flat-directory stats helpers."""

from __future__ import annotations

from pathlib import Path

import desloppify.engine.detectors._flat_dirs.stats as stats_mod


def test_build_dir_stats_counts_parent_dirs_and_children(tmp_path: Path) -> None:
    scan_root = tmp_path
    pkg = scan_root / "pkg"
    sub = pkg / "sub"
    pkg.mkdir()
    sub.mkdir()
    (pkg / "alpha.py").write_text("alpha\n")
    (sub / "beta.py").write_text("beta\n")

    dir_counts, child_dirs = stats_mod.build_dir_stats(
        scan_root,
        ["pkg/alpha.py", "pkg/sub/beta.py"],
    )

    pkg_key = str(pkg.resolve())
    sub_key = str(sub.resolve())

    assert dir_counts[pkg_key] == 1
    assert dir_counts[sub_key] == 1
    assert child_dirs[pkg_key] == {sub_key}


def test_build_dir_stats_skips_unresolvable_paths(monkeypatch, tmp_path: Path) -> None:
    scan_root = tmp_path
    good = scan_root / "good.py"
    good.write_text("ok\n")

    def _fake_resolve_scan_file(file_path: str, *, scan_root: Path) -> Path:
        if file_path == "bad.py":
            raise OSError("boom")
        return scan_root / file_path

    monkeypatch.setattr(stats_mod, "resolve_scan_file", _fake_resolve_scan_file)

    dir_counts, child_dirs = stats_mod.build_dir_stats(scan_root, ["bad.py", "good.py"])

    assert dir_counts[str(scan_root.resolve())] == 1
    assert child_dirs == {}


def test_all_tracked_dirs_unions_counts_and_child_relationships() -> None:
    tracked = stats_mod.all_tracked_dirs(
        {"a": 1},
        {"b": {"c"}, "d": {"e", "f"}},
    )

    assert tracked == {"a", "b", "c", "d", "e", "f"}
