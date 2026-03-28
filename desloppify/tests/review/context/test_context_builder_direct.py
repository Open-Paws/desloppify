"""Direct coverage tests for review context builder internals."""

from __future__ import annotations

import re
from types import SimpleNamespace

from desloppify.intelligence.review._context.models import ReviewContext
from desloppify.intelligence.review.context_builder import (
    ReviewContextBuildServices,
    build_review_context_inner,
)


class _ZoneMap:
    def counts(self) -> dict[str, int]:
        return {"production": 2, "tests": 1}


def test_build_review_context_inner_populates_sections() -> None:
    files = ["src/a.py", "src/b.py", "src/empty.py"]
    content_by_path = {
        "src/a.py": "class Alpha:\n    pass\n\ndef parse_item():\n    raise ValueError()\n",
        "src/b.py": "def process_data():\n    try:\n        return 1\n    except Exception:\n        return 0\n",
        "src/empty.py": "",
    }

    lang = SimpleNamespace(dep_graph={"src/a.py": {"importers": 4}}, zone_map=_ZoneMap())
    state = {
        "issues": {
            "1": {
                "status": "open",
                "file": "src/a.py",
                "detector": "smells",
                "summary": "Long function body",
            },
            "2": {
                "status": "fixed",
                "file": "src/b.py",
                "detector": "smells",
                "summary": "fixed",
            },
            "3": {
                "status": "open",
                "file": "other/c.py",
                "detector": "smells",
                "summary": "outside selection",
            },
        }
    }

    ctx = build_review_context_inner(
        files,
        lang,
        state,
        ReviewContext(),
        ReviewContextBuildServices(
            read_file_text=lambda path: content_by_path.get(path),
            abs_path=lambda path: path,
            rel_path=lambda path: path,
            importer_count=lambda entry: entry.get("importers", 0),
            default_review_module_patterns=lambda content: ["service"] if "def" in content else [],
            gather_ai_debt_signals=lambda file_contents, rel_fn: {"files": sorted(file_contents)},
            gather_auth_context=lambda file_contents, rel_fn: {"auth_files": len(file_contents)},
            classify_error_strategy=lambda content: "raises" if "raise" in content else "returns",
            func_name_re=re.compile(r"def\s+([A-Za-z_]\w*)"),
            class_name_re=re.compile(r"class\s+([A-Za-z_]\w*)"),
            name_prefix_re=re.compile(r"([a-z]+)"),
            error_patterns={
                "has_try": re.compile(r"\btry\b"),
                "has_raise": re.compile(r"\braise\b"),
            },
        ),
    )

    assert ctx.naming_vocabulary["total_names"] == 3
    assert ctx.error_conventions["has_try"] == 1
    assert ctx.error_conventions["has_raise"] == 1
    assert ctx.module_patterns["src/"]["service"] == 2
    assert ctx.import_graph_summary["top_imported"]["src/a.py"] == 4
    assert ctx.zone_distribution["tests"] == 1
    assert list(ctx.existing_issues.keys()) == ["src/a.py"]
    assert ctx.codebase_stats["total_files"] == 3
    assert ctx.ai_debt_signals["files"] == ["src/a.py", "src/b.py", "src/empty.py"]
    assert ctx.auth_patterns["auth_files"] == 3
    assert ctx.error_strategies["src/a.py"] == "raises"


def test_build_review_context_inner_falls_back_to_default_module_patterns() -> None:
    files = ["pkg/file.py"]
    lang = SimpleNamespace(
        dep_graph={},
        zone_map=None,
        review_module_patterns_fn=lambda _content: "not-a-list",
    )

    ctx = build_review_context_inner(
        files,
        lang,
        {"issues": {}},
        ReviewContext(),
        ReviewContextBuildServices(
            read_file_text=lambda _path: "def run_task():\n    return 1\n",
            abs_path=lambda path: path,
            rel_path=lambda path: path,
            importer_count=lambda _entry: 0,
            default_review_module_patterns=lambda _content: [
                "fallback_pattern",
                "fallback_pattern",
            ],
            gather_ai_debt_signals=lambda _file_contents, rel_fn: {},
            gather_auth_context=lambda _file_contents, rel_fn: {},
            classify_error_strategy=lambda _content: "",
            func_name_re=re.compile(r"def\s+([A-Za-z_]\w*)"),
            class_name_re=re.compile(r"class\s+([A-Za-z_]\w*)"),
            name_prefix_re=re.compile(r"([a-z]+)"),
            error_patterns={},
        ),
    )

    assert ctx.module_patterns == {}
    assert ctx.codebase_stats["avg_file_loc"] == 2
