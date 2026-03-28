"""Direct tests for review context heuristic signal helpers."""

from __future__ import annotations

import re
from types import SimpleNamespace

import desloppify.intelligence.review.context_signals.ai as signal_ai_mod
import desloppify.intelligence.review.context_signals.auth as signal_auth_mod
import desloppify.intelligence.review.context_signals.migration as signal_migration_mod


def test_gather_ai_debt_signals_collects_comment_log_and_guard_signals():
    file_contents = {
        "a.py": (
            "# c1\n# c2\n# c3\n# c4\n"
            "def f():\n"
            "    logging.error('x')\n    logging.error('y')\n"
            "    logging.error('z')\n    logging.error('w')\n"
            "    try:\n        pass\n    except Exception:\n        pass\n"
            "    try:\n        pass\n    except Exception:\n        pass\n"
            "    try:\n        pass\n    except Exception:\n        pass\n"
        ),
        "b.py": "def ok():\n    return 1\n",
    }
    result = signal_ai_mod.gather_ai_debt_signals(file_contents, rel_fn=lambda p: p)
    assert "a.py" in result["file_signals"]
    signals = result["file_signals"]["a.py"]
    assert "log_density" in signals
    assert result["codebase_avg_comment_ratio"] > 0


def test_gather_auth_context_collects_route_rls_and_service_role():
    file_contents = {
        "api.py": ("@app.get('/x')\ndef route():\n    request.user\n    return 1\n"),
        "schema.sql": (
            "CREATE TABLE accounts(id int);\n"
            "ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;\n"
        ),
        "client.ts": "const k = service_role; createClient(url, key)",
    }
    result = signal_auth_mod.gather_auth_context(file_contents, rel_fn=lambda p: p)
    assert "route_auth_coverage" in result
    assert result["route_auth_coverage"]["api.py"]["handlers"] == 1
    assert result["route_auth_coverage"]["api.py"]["with_auth"] == 0
    assert result["route_auth_coverage"]["api.py"]["without_auth"] == 1
    assert "rls_coverage" in result
    assert result["rls_coverage"]["with_rls"] == ["accounts"]
    assert result["service_role_usage"] == ["client.ts"]
    assert result["auth_patterns"]["api.py"] >= 1
    assert "auth_guard_patterns" not in result
    assert result["auth_usage_patterns"]["api.py"] >= 1


def test_gather_auth_context_requires_enforcement_for_lookup_only_routes() -> None:
    file_contents = {
        "route.ts": (
            "export async function GET(req) {\n"
            "  const session = await getServerSession();\n"
            "  return Response.json({ ok: !!session });\n"
            "}\n"
        )
    }
    result = signal_auth_mod.gather_auth_context(file_contents, rel_fn=lambda p: p)
    coverage = result["route_auth_coverage"]["route.ts"]
    assert coverage["with_auth"] == 0
    assert coverage["without_auth"] == 1
    assert result["auth_usage_patterns"]["route.ts"] >= 1


def test_gather_auth_context_tracks_policy_only_tables_separately():
    file_contents = {
        "schema.sql": (
            "CREATE TABLE accounts(id int);\n"
            "CREATE TABLE posts(id int);\n"
            "ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;\n"
        ),
        "policies.sql": (
            "CREATE POLICY post_reader ON posts;\n"
        ),
    }
    result = signal_auth_mod.gather_auth_context(file_contents, rel_fn=lambda p: p)
    assert result["rls_coverage"]["with_rls"] == ["accounts"]
    assert result["rls_coverage"]["policy_only"] == ["posts"]
    assert "posts" in result["rls_coverage"]["without_rls"]
    assert result["rls_coverage"]["files"]["posts"] == ["policies.sql", "schema.sql"]


def test_gather_auth_context_excludes_server_only_service_role_paths():
    file_contents = {
        "functions/worker.ts": "const k = service_role; createClient(url, k)",
    }
    result = signal_auth_mod.gather_auth_context(file_contents, rel_fn=lambda p: p)
    assert "service_role_usage" not in result


def test_gather_auth_context_ignores_non_source_guidance_files():
    file_contents = {
        "README.md": "@app.get('/docs') should use request.user and useAuth",
        "docs/security.txt": "createClient(url, service_role) example",
    }
    result = signal_auth_mod.gather_auth_context(file_contents, rel_fn=lambda p: p)
    assert result == {}


def test_gather_auth_context_ignores_runtime_extensions_in_guidance_paths() -> None:
    file_contents = {
        "guidance/auth_examples.py": "@app.get('/docs')\ndef route():\n    request.user\n",
        "prompts/security_prompt.ts": "const k = service_role; createClient(url, k)",
        "src/routes/admin.py": "@app.get('/admin')\ndef route():\n    return 1\n",
    }
    result = signal_auth_mod.gather_auth_context(file_contents, rel_fn=lambda p: p)
    assert list(result["route_auth_coverage"]) == ["src/routes/admin.py"]
    assert "service_role_usage" not in result


def test_gather_auth_context_counts_public_route_markers_separately():
    file_contents = {
        "api.py": (
            "@app.get('/health')\n"
            "def health():\n"
            "    # public_route: anonymous health check\n"
            "    return {'ok': True}\n"
            "@app.get('/private')\n"
            "def private():\n"
            "    return {'ok': True}\n"
        )
    }
    result = signal_auth_mod.gather_auth_context(file_contents, rel_fn=lambda p: p)
    ra = result["route_auth_coverage"]["api.py"]
    assert ra["handlers"] == 2
    assert ra["public_routes"] == 1
    assert ra["without_auth"] == 1


def test_gather_migration_signals_and_classify_error_strategy():
    file_contents = {
        "old.ts": "@deprecated\nTODO migrate legacy handler\nfoo.oldApi()\n",
        "new.ts": "foo.newApi()\n",
        "dual.ts": "const x = 1\n",
        "dual.js": "const y = 1\n",
    }
    lang_cfg = SimpleNamespace(
        migration_mixed_extensions={".ts", ".js"},
        migration_pattern_pairs=[
            ("api_shift", re.compile(r"oldApi"), re.compile(r"newApi")),
        ],
    )

    result = signal_migration_mod.gather_migration_signals(
        file_contents,
        lang_cfg,
        rel_fn=lambda p: p,
    )
    assert result["deprecated_markers"]["total"] >= 1
    assert result["migration_todos"]
    assert result["pattern_pairs"][0]["name"] == "api_shift"
    assert "dual" in result["mixed_extensions"]

    assert (
        signal_migration_mod.classify_error_strategy(
            "raise ValueError('x')\nraise RuntimeError('y')"
        )
        == "throw"
    )
    assert (
        signal_migration_mod.classify_error_strategy("return None\nreturn null\n")
        == "return_null"
    )
    assert (
        signal_migration_mod.classify_error_strategy(
            "try:\n    pass\nexcept Exception:\n    raise\n"
        )
        == "try_catch"
    )
    assert (
        signal_migration_mod.classify_error_strategy("raise X\nreturn None\n")
        == "mixed"
    )
