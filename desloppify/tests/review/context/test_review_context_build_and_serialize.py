"""Integration tests for review context builders and serialization."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from desloppify.intelligence.review.context import (
    ReviewContext,
    build_review_context,
    serialize_context,
)
from desloppify.intelligence.review.context_holistic.orchestrator import (
    build_holistic_context,
)
from desloppify.state import empty_state as make_empty_state


# ── Integration: build_review_context ─────────────────────────────


class TestBuildReviewContext:
    """Tests for build_review_context populating signal fields."""

    @pytest.fixture
    def mock_lang(self):
        lang = MagicMock()
        lang.name = "typescript"
        lang.file_finder = MagicMock(return_value=[])
        lang.zone_map = None
        lang.dep_graph = None
        return lang

    @pytest.fixture
    def empty_state(self):
        return make_empty_state()

    def test_ai_debt_signals_populated(self, mock_lang, empty_state):
        """build_review_context should populate ai_debt_signals."""
        # Create a file with high comment ratio
        comment_heavy = "# comment\n" * 8 + "x = 1\n" * 2

        with patch(
            "desloppify.intelligence.review.context.read_file_text", return_value=comment_heavy
        ):
            ctx = build_review_context(
                Path("/project"),
                mock_lang,
                empty_state,
                files=["/project/src/chatty.py"],
            )

        assert ctx.ai_debt_signals is not None
        assert "file_signals" in ctx.ai_debt_signals

    def test_auth_patterns_populated(self, mock_lang, empty_state):
        """build_review_context should populate auth_patterns."""
        route_content = textwrap.dedent("""\
            @app.get("/users")
            @login_required
            def get_users():
                return []
        """)

        with patch(
            "desloppify.intelligence.review.context.read_file_text", return_value=route_content
        ):
            ctx = build_review_context(
                Path("/project"),
                mock_lang,
                empty_state,
                files=["/project/src/routes.py"],
            )

        assert ctx.auth_patterns is not None
        assert "route_auth_coverage" in ctx.auth_patterns
        assert "auth_patterns" in ctx.auth_patterns
        assert "auth_guard_patterns" in ctx.auth_patterns

    def test_error_strategies_populated(self, mock_lang, empty_state):
        """build_review_context should populate error_strategies."""
        throw_content = textwrap.dedent("""\
            function validate(x) {
                if (!x) throw new Error("missing");
                if (x < 0) throw new Error("negative");
                if (x > 100) throw new Error("too big");
            }
        """)

        with patch(
            "desloppify.intelligence.review.context.read_file_text", return_value=throw_content
        ):
            ctx = build_review_context(
                Path("/project"),
                mock_lang,
                empty_state,
                files=["/project/src/validate.ts"],
            )

        assert ctx.error_strategies is not None
        assert len(ctx.error_strategies) > 0

    def test_empty_files_returns_default_context(self, mock_lang, empty_state):
        """build_review_context with no files should return empty context."""
        ctx = build_review_context(
            Path("/project"),
            mock_lang,
            empty_state,
            files=[],
        )
        assert ctx.ai_debt_signals == {}
        assert ctx.auth_patterns == {}
        assert ctx.error_strategies == {}


# ── Integration: build_holistic_context ───────────────────────────


class TestBuildHolisticContext:
    """Tests for build_holistic_context including signal sections."""

    @pytest.fixture
    def mock_lang(self):
        lang = MagicMock()
        lang.name = "typescript"
        lang.file_finder = MagicMock(return_value=[])
        lang.zone_map = None
        lang.dep_graph = None
        return lang

    @pytest.fixture
    def empty_state(self):
        return make_empty_state()

    def test_authorization_section_present_with_routes(self, mock_lang, empty_state):
        """build_holistic_context should include authorization when route handlers exist."""
        content = textwrap.dedent("""\
            @app.get("/api/data")
            def get_data():
                return []
        """)

        with patch(
            "desloppify.intelligence.review.context_holistic.readers.read_file_text", return_value=content
        ):
            ctx = build_holistic_context(
                Path("/project"),
                mock_lang,
                empty_state,
                files=["/project/src/api.py"],
            )

        assert "authorization" in ctx

    def test_ai_debt_section_present_with_signals(self, mock_lang, empty_state):
        """build_holistic_context should include ai_debt_signals when files have signals."""
        comment_heavy = "# comment\n" * 8 + "x = 1\n" * 2

        with patch(
            "desloppify.intelligence.review.context_holistic.readers.read_file_text",
            return_value=comment_heavy,
        ):
            ctx = build_holistic_context(
                Path("/project"),
                mock_lang,
                empty_state,
                files=["/project/src/chatty.py"],
            )

        assert "ai_debt_signals" in ctx

    def test_migration_signals_present(self, mock_lang, empty_state):
        """build_holistic_context should include migration_signals when deprecated markers exist."""
        content = "@deprecated\ndef old(): pass\n"

        with patch(
            "desloppify.intelligence.review.context_holistic.readers.read_file_text", return_value=content
        ):
            ctx = build_holistic_context(
                Path("/project"),
                mock_lang,
                empty_state,
                files=["/project/src/old.py"],
            )

        assert "migration_signals" in ctx

    def test_no_auth_section_when_no_routes(self, mock_lang, empty_state):
        """build_holistic_context emits an empty authorization section when no routes exist."""
        content = "def helper():\n    return 42\n"

        with patch(
            "desloppify.intelligence.review.context_holistic.readers.read_file_text", return_value=content
        ):
            ctx = build_holistic_context(
                Path("/project"),
                mock_lang,
                empty_state,
                files=["/project/src/util.py"],
            )

        assert "authorization" in ctx
        assert ctx["authorization"] == {}

    def test_authorization_section_present_with_rls_only(self, mock_lang, empty_state):
        """Holistic context should include authorization for non-route RLS evidence."""
        content = textwrap.dedent("""\
            CREATE TABLE accounts(id int);
            ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
        """)

        with patch(
            "desloppify.intelligence.review.context_holistic.readers.read_file_text", return_value=content
        ):
            ctx = build_holistic_context(
                Path("/project"),
                mock_lang,
                empty_state,
                files=["/project/sql/schema.sql"],
            )

        assert "authorization" in ctx
        assert "rls_coverage" in ctx["authorization"]

    def test_authorization_section_present_with_service_role_only(
        self, mock_lang, empty_state
    ):
        """Holistic context should include authorization for client-side service-role evidence."""
        content = "const admin = createClient(url, service_role);"

        with patch(
            "desloppify.intelligence.review.context_holistic.readers.read_file_text", return_value=content
        ):
            ctx = build_holistic_context(
                Path("/project"),
                mock_lang,
                empty_state,
                files=["/project/src/client.ts"],
            )

        assert "authorization" in ctx
        usage = ctx["authorization"].get("service_role_usage") or []
        assert any(path.endswith("/src/client.ts") for path in usage)

    def test_no_ai_debt_when_clean(self, mock_lang, empty_state):
        """build_holistic_context emits empty ai_debt_signals when no signals exist."""
        content = "def add(a, b):\n    return a + b\n"

        with patch(
            "desloppify.intelligence.review.context_holistic.readers.read_file_text", return_value=content
        ):
            ctx = build_holistic_context(
                Path("/project"),
                mock_lang,
                empty_state,
                files=["/project/src/clean.py"],
            )

        assert "ai_debt_signals" in ctx
        assert ctx["ai_debt_signals"] == {}

    def test_codebase_stats_always_present(self, mock_lang, empty_state):
        """build_holistic_context should always include codebase_stats."""
        content = "x = 1\n"

        with patch(
            "desloppify.intelligence.review.context_holistic.readers.read_file_text", return_value=content
        ):
            ctx = build_holistic_context(
                Path("/project"),
                mock_lang,
                empty_state,
                files=["/project/src/x.py"],
            )

        assert "codebase_stats" in ctx
        assert "total_files" in ctx["codebase_stats"]
        assert "total_loc" in ctx["codebase_stats"]


# ── Serialization ─────────────────────────────────────────────────


class TestSerializeContext:
    """Tests for serialize_context."""

    def test_always_present_fields(self):
        """Core fields should always be present in serialized output."""
        ctx = ReviewContext()
        d = serialize_context(ctx)
        assert "naming_vocabulary" in d
        assert "error_conventions" in d
        assert "module_patterns" in d
        assert "import_graph_summary" in d
        assert "zone_distribution" in d
        assert "existing_issues" in d
        assert "codebase_stats" in d
        assert "sibling_conventions" in d

    def test_ai_debt_signals_included_when_populated(self):
        """ai_debt_signals should be included when non-empty."""
        ctx = ReviewContext()
        ctx.ai_debt_signals = {
            "file_signals": {"a.py": {"comment_ratio": 0.5}},
            "codebase_avg_comment_ratio": 0.1,
        }
        d = serialize_context(ctx)
        assert "ai_debt_signals" in d

    def test_ai_debt_signals_excluded_when_empty(self):
        """ai_debt_signals should be excluded when empty."""
        ctx = ReviewContext()
        ctx.ai_debt_signals = {}
        d = serialize_context(ctx)
        assert "ai_debt_signals" not in d

    def test_auth_patterns_included_when_populated(self):
        """auth_patterns should be included when non-empty."""
        ctx = ReviewContext()
        ctx.auth_patterns = {"route_auth_coverage": {"api.py": {"handlers": 2}}}
        d = serialize_context(ctx)
        assert "auth_patterns" in d

    def test_auth_patterns_excluded_when_empty(self):
        """auth_patterns should be excluded when empty."""
        ctx = ReviewContext()
        ctx.auth_patterns = {}
        d = serialize_context(ctx)
        assert "auth_patterns" not in d

    def test_error_strategies_included_when_populated(self):
        """error_strategies should be included when non-empty."""
        ctx = ReviewContext()
        ctx.error_strategies = {"api.py": "throw"}
        d = serialize_context(ctx)
        assert "error_strategies" in d

    def test_error_strategies_excluded_when_empty(self):
        """error_strategies should be excluded when empty."""
        ctx = ReviewContext()
        ctx.error_strategies = {}
        d = serialize_context(ctx)
        assert "error_strategies" not in d

    def test_all_conditional_fields_present(self):
        """All three conditional fields should appear when populated."""
        ctx = ReviewContext()
        ctx.ai_debt_signals = {"file_signals": {}, "codebase_avg_comment_ratio": 0.0}
        ctx.auth_patterns = {"auth_patterns": {"a.py": 1}}
        ctx.error_strategies = {"a.py": "throw"}
        d = serialize_context(ctx)
        # ai_debt_signals has truthy value (non-empty dict with keys)
        assert "ai_debt_signals" in d
        assert "auth_patterns" in d
        assert "error_strategies" in d

    def test_serialized_values_match_context(self):
        """Serialized values should exactly match the ReviewContext attributes."""
        ctx = ReviewContext()
        ctx.naming_vocabulary = {"prefixes": {"get": 5}, "total_names": 10}
        ctx.error_conventions = {"try_catch": 3}
        ctx.ai_debt_signals = {
            "file_signals": {"x.py": {"log_density": 4.0}},
            "codebase_avg_comment_ratio": 0.15,
        }
        d = serialize_context(ctx)
        assert d["naming_vocabulary"] == ctx.naming_vocabulary
        assert d["error_conventions"] == ctx.error_conventions
        assert d["ai_debt_signals"] == ctx.ai_debt_signals
