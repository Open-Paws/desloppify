"""Tests for desloppify.base.signal_patterns — regex patterns and helpers."""

from __future__ import annotations

from desloppify.base.signal_patterns import (
    DEPRECATION_MARKER_RE,
    MIGRATION_TODO_RE,
    SERVER_ONLY_PATH_HINTS,
    SERVICE_ROLE_TOKEN_RE,
    is_server_only_path,
)

# ── is_server_only_path ──────────────────────────────────────────────


def test_server_only_path_empty():
    """Empty string returns False."""
    assert is_server_only_path("") is False


def test_server_only_path_api_dir():
    """Paths containing /api/ are server-only."""
    assert is_server_only_path("src/api/handler.ts") is True


def test_server_only_path_server_dir():
    """Paths containing /server/ are server-only."""
    assert is_server_only_path("project/server/index.ts") is True


def test_server_only_path_backend_dir():
    """Paths containing /backend/ are server-only."""
    assert is_server_only_path("backend/routes.py") is True


def test_server_only_path_functions_dir():
    """Paths containing /functions/ are server-only."""
    assert is_server_only_path("supabase/functions/hello/index.ts") is True


def test_server_only_path_supabase_functions():
    """Paths containing /supabase/functions/ are server-only."""
    assert is_server_only_path("supabase/functions/auth/index.ts") is True


def test_server_only_path_scripts_dir():
    """Paths containing /scripts/ are server-only."""
    assert is_server_only_path("scripts/deploy.sh") is True


def test_server_only_path_client_code():
    """Client-side paths are not server-only."""
    assert is_server_only_path("src/components/Button.tsx") is False


def test_server_only_path_backslash_normalized():
    """Backslashes are normalized to forward slashes."""
    assert is_server_only_path("project\\api\\handler.ts") is True


def test_server_only_path_no_leading_slash():
    """Paths without leading slash still match (prefix is added)."""
    assert is_server_only_path("api/handler.ts") is True


def test_server_only_path_absolute():
    """Absolute paths work correctly."""
    assert is_server_only_path("/home/user/project/server/app.py") is True


# ── DEPRECATION_MARKER_RE ────────────────────────────────────────────


def test_deprecation_marker_decorator():
    """Matches @deprecated and @Deprecated annotations."""
    assert DEPRECATION_MARKER_RE.search("@deprecated") is not None
    assert DEPRECATION_MARKER_RE.search("@Deprecated") is not None


def test_deprecation_marker_word():
    """Matches DEPRECATED keyword."""
    assert DEPRECATION_MARKER_RE.search("DEPRECATED: use newFunc") is not None


def test_deprecation_marker_no_match():
    """Does not match random text."""
    assert DEPRECATION_MARKER_RE.search("this function is old") is None


def test_deprecation_marker_word_boundary():
    """@deprecated must be at a word boundary (not part of larger word)."""
    # @deprecatedMethod should not match because it is a larger token.
    assert DEPRECATION_MARKER_RE.search("@deprecatedMethod") is None


# ── MIGRATION_TODO_RE ─────────────────────────────────────────────────


def test_migration_todo_basic():
    """Matches TODO with migration keywords."""
    assert MIGRATION_TODO_RE.search("TODO: migrate to new API") is not None


def test_migration_todo_fixme_legacy():
    """Matches FIXME with legacy keyword."""
    assert MIGRATION_TODO_RE.search("FIXME: legacy code needs rewrite") is not None


def test_migration_todo_hack_deprecated():
    """Matches HACK with deprecated keyword."""
    assert MIGRATION_TODO_RE.search("HACK: deprecated method used here") is not None


def test_migration_todo_remove_after():
    """Matches TODO with remove-after pattern."""
    assert MIGRATION_TODO_RE.search("TODO remove after v3 release") is not None


def test_migration_todo_no_migration_keyword():
    """Does not match TODO without migration-related keywords."""
    assert MIGRATION_TODO_RE.search("TODO: fix the button color") is None


def test_migration_todo_case_insensitive():
    """Match is case-insensitive for migration keywords."""
    assert MIGRATION_TODO_RE.search("TODO: MIGRATE to new system") is not None


# ── SERVICE_ROLE_TOKEN_RE ─────────────────────────────────────────────


def test_service_role_camel_case():
    """Matches serviceRole and serviceRoleKey."""
    assert SERVICE_ROLE_TOKEN_RE.search("const serviceRoleKey = '...'") is not None


def test_service_role_snake_case():
    """Matches service_role and service_role_key."""
    assert SERVICE_ROLE_TOKEN_RE.search("service_role_key = env('...')") is not None


def test_service_role_env_var():
    """Matches SUPABASE_SERVICE_ROLE_KEY."""
    assert SERVICE_ROLE_TOKEN_RE.search("SUPABASE_SERVICE_ROLE_KEY") is not None


def test_service_role_no_match():
    """Does not match unrelated text."""
    assert SERVICE_ROLE_TOKEN_RE.search("const userRole = 'admin'") is None


def test_service_role_case_insensitive():
    """Match is case-insensitive."""
    assert SERVICE_ROLE_TOKEN_RE.search("SERVICE_ROLE") is not None


# ── SERVER_ONLY_PATH_HINTS ────────────────────────────────────────────


def test_server_only_path_hints_are_tuples():
    """Hints should be a tuple of directory path patterns."""
    assert isinstance(SERVER_ONLY_PATH_HINTS, tuple)
    for hint in SERVER_ONLY_PATH_HINTS:
        assert hint.startswith("/")
        assert hint.endswith("/")
