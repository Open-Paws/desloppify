"""Direct coverage for TypeScript detector IO helpers."""

from __future__ import annotations

from pathlib import Path

import desloppify.languages.typescript.detectors.io as io_mod


def test_typescript_io_helpers_filter_and_resolve_paths(monkeypatch, tmp_path: Path) -> None:
    assert io_mod.should_skip_typescript_source("src/types.d.ts") is True
    assert io_mod.should_skip_typescript_source("node_modules/pkg/index.ts") is True
    assert io_mod.should_skip_typescript_source("src/app.tsx") is False

    monkeypatch.setattr(
        io_mod,
        "find_ts_and_tsx_files",
        lambda _path: [
            "src/app.ts",
            "src/widget.tsx",
            "src/types.d.ts",
            "node_modules/pkg/index.ts",
        ],
    )
    assert io_mod.iter_typescript_sources(tmp_path) == ["src/app.ts", "src/widget.tsx"]

    monkeypatch.setattr(io_mod, "get_project_root", lambda: tmp_path)
    relative = io_mod.resolve_typescript_source("src/app.ts")
    absolute = io_mod.resolve_typescript_source(str(tmp_path / "src" / "app.ts"))
    assert relative == tmp_path / "src" / "app.ts"
    assert absolute == tmp_path / "src" / "app.ts"

