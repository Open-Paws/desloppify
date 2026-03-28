"""Tests for review dimensions, language guidance, context conventions, and cache behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

from desloppify.base.discovery.source import (
    disable_file_cache,
    enable_file_cache,
    is_file_cache_enabled,
)
from desloppify.intelligence.review import (
    DIMENSION_PROMPTS,
    LANG_GUIDANCE,
    build_review_context,
    import_review_issues,
)
from desloppify.intelligence.review import (
    DIMENSIONS as REVIEW_DIMENSIONS,
)
from desloppify.intelligence.review.context import serialize_context
from desloppify.tests.review.shared_review_fixtures import (
    _as_review_payload,
    prepare_review,
)

# ── New dimension tests ──────────────────────────────────────────


class TestNewDimensions:
    def test_logic_clarity_dimension(self):
        dim = DIMENSION_PROMPTS["logic_clarity"]
        assert "control flow" in dim["description"].lower()
        assert len(dim["look_for"]) >= 3
        assert len(dim["skip"]) >= 1

    def test_contract_coherence_dimension(self):
        dim = DIMENSION_PROMPTS["contract_coherence"]
        assert "contract" in dim["description"].lower()
        assert any("return type" in item.lower() for item in dim["look_for"])

    def test_type_safety_dimension(self):
        dim = DIMENSION_PROMPTS["type_safety"]
        assert "type" in dim["description"].lower()
        assert len(dim["look_for"]) >= 3
        assert len(dim["skip"]) >= 1

    def test_cross_module_architecture_dimension(self):
        dim = DIMENSION_PROMPTS["cross_module_architecture"]
        assert "module" in dim["description"].lower()
        assert len(dim["look_for"]) >= 3
        assert len(dim["skip"]) >= 1

    def test_new_dimensions_in_default(self):
        assert "logic_clarity" in REVIEW_DIMENSIONS
        assert "abstraction_fitness" in REVIEW_DIMENSIONS
        assert "ai_generated_debt" in REVIEW_DIMENSIONS

    def test_import_accepts_new_dimensions(self, empty_state):
        data = [
            {
                "file": "src/foo.ts",
                "dimension": "logic_clarity",
                "identifier": "handleClick",
                "summary": "Identical if/else branches",
                "confidence": "high",
            },
            {
                "file": "src/bar.py",
                "dimension": "contract_coherence",
                "identifier": "get_user",
                "summary": "Return type says User but can return None",
                "confidence": "medium",
            },
            {
                "file": "src/config.py",
                "dimension": "cross_module_architecture",
                "identifier": "DB_URL",
                "summary": "Module reads DB_URL at import time before config is loaded",
                "confidence": "low",
            },
        ]
        diff = import_review_issues(_as_review_payload(data), empty_state, "python")
        assert diff["new"] == 3

    def test_ai_generated_debt_dimension(self):
        dim = DIMENSION_PROMPTS["ai_generated_debt"]
        assert "llm" in dim["description"].lower() or "ai" in dim["description"].lower()
        assert len(dim["look_for"]) >= 3
        assert len(dim["skip"]) >= 1

    def test_authorization_coherence_dimension(self):
        dim = DIMENSION_PROMPTS["authorization_coherence"]
        assert "auth" in dim["description"].lower()
        assert len(dim["look_for"]) >= 3
        assert len(dim["skip"]) >= 1

    def test_new_phase2_dimensions_in_default(self):
        assert "ai_generated_debt" in REVIEW_DIMENSIONS
        assert "error_consistency" in REVIEW_DIMENSIONS

    def test_import_accepts_new_phase2_dimensions(self, empty_state):
        data = [
            {
                "file": "src/service.py",
                "dimension": "ai_generated_debt",
                "identifier": "handle_request",
                "summary": "Restating docstring on trivial function",
                "confidence": "medium",
            },
            {
                "file": "src/routes.py",
                "dimension": "authorization_coherence",
                "identifier": "delete_user",
                "summary": "Auth on GET/POST but not DELETE handler",
                "confidence": "high",
            },
        ]
        diff = import_review_issues(_as_review_payload(data), empty_state, "python")
        assert diff["new"] == 2

    def test_import_accepts_issue57_dimensions(self, empty_state):
        """New dimensions from #57 are accepted by import."""
        data = [
            {
                "file": "src/app.py",
                "dimension": "abstraction_fitness",
                "identifier": "handle_request",
                "summary": "Wrapper that just forwards to inner handler",
                "confidence": "high",
            },
            {
                "file": "src/utils.py",
                "dimension": "type_safety",
                "identifier": "parse_config",
                "summary": "Return type -> Config but can return None on failure",
                "confidence": "medium",
            },
            {
                "file": "src/core.py",
                "dimension": "cross_module_architecture",
                "identifier": "settings",
                "summary": "Global mutable dict modified by 4 different modules",
                "confidence": "high",
            },
        ]
        diff = import_review_issues(_as_review_payload(data), empty_state, "python")
        assert diff["new"] == 3


# ── Language guidance tests ──────────────────────────────────────


class TestLangGuidance:
    def test_python_guidance_exists(self):
        assert "python" in LANG_GUIDANCE
        py = LANG_GUIDANCE["python"]
        assert "patterns" in py
        assert "naming" in py
        assert len(py["patterns"]) >= 3

    def test_typescript_guidance_exists(self):
        assert "typescript" in LANG_GUIDANCE
        ts = LANG_GUIDANCE["typescript"]
        assert "patterns" in ts
        assert "naming" in ts
        assert len(ts["patterns"]) >= 3

    def test_prepare_includes_lang_guidance(self, mock_lang, empty_state, tmp_path):
        f = tmp_path / "foo.ts"
        f.write_text("export function getData() { return 42; }\n" * 25)
        mock_lang.file_finder = MagicMock(return_value=[str(f)])
        data = prepare_review(tmp_path, mock_lang, empty_state)
        assert "lang_guidance" in data
        assert "language" in data
        assert data["language"] == "typescript"

    def test_python_auth_guidance_exists(self):
        py = LANG_GUIDANCE["python"]
        assert "auth" in py
        assert len(py["auth"]) >= 3
        auth_text = " ".join(py["auth"]).lower()
        assert "login_required" in auth_text
        assert "request.user" in auth_text

    def test_typescript_auth_guidance_exists(self):
        ts = LANG_GUIDANCE["typescript"]
        assert "auth" in ts
        assert len(ts["auth"]) >= 3
        auth_text = " ".join(ts["auth"]).lower()
        assert "useauth" in auth_text or "getserversession" in auth_text

    def test_prepare_includes_lang_guidance_python(self, empty_state, tmp_path):
        lang = MagicMock()
        lang.name = "python"
        lang.zone_map = None
        lang.dep_graph = None
        f = tmp_path / "foo.py"
        f.write_text("def get_data():\n    return 42\n" * 15)
        lang.file_finder = MagicMock(return_value=[str(f)])
        data = prepare_review(tmp_path, lang, empty_state)
        assert data["language"] == "python"
        assert "patterns" in data["lang_guidance"]


# ── Sibling conventions tests ────────────────────────────────────


class TestSiblingConventions:
    def test_sibling_conventions_populated(self, mock_lang, empty_state, tmp_path):
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        for i in range(4):
            (hooks / f"hook{i}.ts").write_text(
                f"export function useHook{i}() {{}}\nfunction handleEvent{i}() {{}}\n"
            )
        mock_lang.file_finder = MagicMock(
            return_value=[str(hooks / f"hook{i}.ts") for i in range(4)]
        )
        ctx = build_review_context(tmp_path, mock_lang, empty_state)
        assert "hooks/" in ctx.sibling_conventions
        assert "use" in ctx.sibling_conventions["hooks/"]
        assert "handle" in ctx.sibling_conventions["hooks/"]

    def test_sibling_conventions_serialized(self, mock_lang, empty_state, tmp_path):
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        for i in range(4):
            (hooks / f"hook{i}.ts").write_text(f"function getData{i}() {{}}\n")
        mock_lang.file_finder = MagicMock(
            return_value=[str(hooks / f"hook{i}.ts") for i in range(4)]
        )
        ctx = build_review_context(tmp_path, mock_lang, empty_state)
        serialized = serialize_context(ctx)
        assert "sibling_conventions" in serialized


# ── File cache integration test ──────────────────────────────────


class TestFileCache:
    def test_build_context_uses_file_cache(self, mock_lang, empty_state, tmp_path):
        """build_review_context should enable file cache for performance."""
        f = tmp_path / "foo.ts"
        f.write_text("function getData() {}\nclass Foo {}")
        mock_lang.file_finder = MagicMock(return_value=[str(f)])

        # Cache should be disabled before and after
        assert not is_file_cache_enabled()
        build_review_context(tmp_path, mock_lang, empty_state)
        assert not is_file_cache_enabled()  # Cleaned up after

    def test_build_context_reentrant_cache(self, mock_lang, empty_state, tmp_path):
        """build_review_context shouldn't disable cache if caller already enabled it."""
        f = tmp_path / "foo.ts"
        f.write_text("function getData() {}\nclass Foo {}")
        mock_lang.file_finder = MagicMock(return_value=[str(f)])

        enable_file_cache()
        try:
            assert is_file_cache_enabled()
            build_review_context(tmp_path, mock_lang, empty_state)
            assert is_file_cache_enabled()  # Still enabled — didn't stomp caller
        finally:
            disable_file_cache()

    def test_prepare_caches_across_phases(self, mock_lang, empty_state, tmp_path):
        """prepare_review should enable cache for context + selection + extraction."""
        f = tmp_path / "foo.ts"
        f.write_text("export function getData() { return 42; }\n" * 25)
        mock_lang.file_finder = MagicMock(return_value=[str(f)])

        assert not is_file_cache_enabled()
        prepare_review(tmp_path, mock_lang, empty_state)
        assert not is_file_cache_enabled()  # Cleaned up after

