"""Guard against bundled skill copies drifting from docs/."""

from __future__ import annotations

from pathlib import Path


def test_bundled_skill_docs_match_source_docs() -> None:
    root = Path(__file__).resolve().parents[2]
    docs_dir = root / "docs"
    bundled_dir = root / "desloppify" / "data" / "global"
    filenames = (
        "SKILL.md",
        "CLAUDE.md",
        "CURSOR.md",
        "CODEX.md",
        "WINDSURF.md",
        "GEMINI.md",
        "HERMES.md",
    )

    for filename in filenames:
        source = (docs_dir / filename).read_text(encoding="utf-8")
        bundled = (bundled_dir / filename).read_text(encoding="utf-8")
        assert bundled == source, (
            "Bundled skill data is out of sync with docs/. "
            "Run: cp docs/*.md desloppify/data/global/"
        )
