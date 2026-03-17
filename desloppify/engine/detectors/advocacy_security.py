"""Advocacy security detector — finds activist protection antipatterns.

Heuristic detector based on the 3-adversary threat model for animal advocacy
software: state surveillance, industry infiltration, and AI model bias.

Checks for:
- Activist identity leakage in logs/errors
- Sensitive data sent to external AI APIs without zero-retention headers
- Investigation materials in publicly accessible paths
- Unencrypted writes of sensitive data

Expect false positives — confidence is "medium" by default, "high" only
for unambiguous violations.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Pattern definitions ──────────────────────────────────────────────────

# Sensitive field names that shouldn't appear in log/error output
_SENSITIVE_FIELDS = re.compile(
    r"\b(user\.(?:email|name|phone|address|real_?name|identity|ssn)|"
    r"activist|witness|investigator|informant|whistleblower|"
    r"req(?:uest)?\.ip|request\.remote_addr|x[_-]forwarded[_-]for|"
    r"client[_.]ip|remote[_.]addr|peer[_.]addr)"
    r"\b",
    re.IGNORECASE,
)

# Log/print/error output patterns
_LOG_PATTERNS = re.compile(
    r"\b(console\.(log|warn|error|info|debug)|"
    r"print|println|printf|fprintf|log\.(info|warn|error|debug|fatal)|"
    r"logger\.(info|warn|error|debug|fatal)|"
    r"logging\.(info|warn|error|debug|fatal))\s*\(",
    re.IGNORECASE,
)

# Error/throw/raise patterns
_ERROR_PATTERNS = re.compile(
    r"\b(throw\s+new\s+\w*Error|raise\s+\w*Error|"
    r"Error\(|Exception\(|panic\()\s*\(",
    re.IGNORECASE,
)

# Known AI API domains (calls to these without zero-retention should be flagged)
_AI_API_DOMAINS = re.compile(
    r"(api\.openai\.com|api\.anthropic\.com|api\.cohere\.(ai|com)|"
    r"generativelanguage\.googleapis\.com|api\.mistral\.ai|"
    r"api\.together\.xyz|openrouter\.ai/api)",
    re.IGNORECASE,
)

# HTTP call patterns
_HTTP_CALL = re.compile(
    r"\b(fetch|axios\.(get|post|put|patch)|requests\.(get|post|put|patch)|"
    r"http\.(?:Get|Post|Put)|urllib\.request|aiohttp|httpx)\s*\(",
    re.IGNORECASE,
)

# Sensitive path segments
_SENSITIVE_PATH_SEGMENTS = re.compile(
    r"[/\\](investigation|evidence|whistleblower|undercover|activist|"
    r"witness|informant|covert)[/\\]",
    re.IGNORECASE,
)

# Public-facing directory patterns
_PUBLIC_DIRS = re.compile(
    r"[/\\](public|static|assets|www|wwwroot|dist|build|out)[/\\]",
    re.IGNORECASE,
)

# Unencrypted file write patterns
_FILE_WRITE = re.compile(
    r"\b(writeFile|write_text|write_bytes|open\(.+['\"]w|"
    r"fs\.write|fwrite|io\.Write|os\.Create)\b",
    re.IGNORECASE,
)

# Sensitive data variable names
_SENSITIVE_VARS = re.compile(
    r"\b(investigation_?data|evidence_?data|witness_?info|"
    r"activist_?data|target_?list|covert_?ops|"
    r"informant|whistleblower_?report)\b",
    re.IGNORECASE,
)

# localStorage/sessionStorage patterns
_BROWSER_STORAGE = re.compile(
    r"\b(localStorage|sessionStorage)\.(setItem|getItem)\s*\(",
    re.IGNORECASE,
)


def _find_files(path: Path) -> list[str]:
    """Find source files to scan."""
    code_extensions = frozenset({
        ".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs",
        ".java", ".kt", ".cs", ".rb", ".php",
    })
    if path.is_file():
        return [str(path)]

    files = []
    for root, dirs, filenames in os.walk(path):
        dirs[:] = [
            d for d in dirs
            if d not in {
                "node_modules", ".git", "dist", "build", ".next",
                "__pycache__", ".mypy_cache", ".pytest_cache", "vendor",
                ".desloppify", ".venv", "venv",
            }
        ]
        for name in filenames:
            if any(name.endswith(ext) for ext in code_extensions):
                files.append(os.path.join(root, name))
    return files


def detect_advocacy_security(
    path: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Detect advocacy-specific security antipatterns in files under path.

    Returns (entries, potentials) where entries are DetectorEntry-shaped dicts.
    """
    files = _find_files(path)
    entries: list[dict[str, Any]] = []

    for filepath in files:
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            continue

        for lineno, line in enumerate(lines, start=1):
            # Skip comment-only lines that are explaining security (not violating it)
            stripped = line.strip()
            if stripped.startswith(("//", "#", "*", "/*", "'''", '"""')):
                continue

            # ── Check 1: PII/identity in log/print statements ──
            if _LOG_PATTERNS.search(line) and _SENSITIVE_FIELDS.search(line):
                entries.append(_make_entry(
                    filepath, lineno, line,
                    kind="identity_leakage",
                    summary="Sensitive identity field in log output — may expose activist/user identity",
                    confidence="medium",
                    tier=2,
                ))

            # ── Check 2: PII in error/throw/raise ──
            elif _ERROR_PATTERNS.search(line) and _SENSITIVE_FIELDS.search(line):
                entries.append(_make_entry(
                    filepath, lineno, line,
                    kind="identity_in_error",
                    summary="Sensitive identity field in error message — may expose in stack traces",
                    confidence="medium",
                    tier=2,
                ))

            # ── Check 3: Calls to AI APIs (check for investigation data in body) ──
            if _AI_API_DOMAINS.search(line):
                # Flag any call to an AI API that appears to send data
                entries.append(_make_entry(
                    filepath, lineno, line,
                    kind="external_ai_api",
                    summary="Call to external AI API — verify zero-retention policy and data sensitivity",
                    confidence="medium",
                    tier=2,
                ))

            # ── Check 4: HTTP calls with sensitive variable names in body ──
            if _HTTP_CALL.search(line) and _SENSITIVE_VARS.search(line):
                entries.append(_make_entry(
                    filepath, lineno, line,
                    kind="sensitive_data_transmission",
                    summary="Sensitive advocacy data in HTTP request body — ensure zero-retention endpoint",
                    confidence="medium",
                    tier=2,
                ))

            # ── Check 5: Investigation data in public directories ──
            if _PUBLIC_DIRS.search(filepath) and _SENSITIVE_PATH_SEGMENTS.search(filepath):
                # Only flag once per file, at line 1
                if lineno == 1:
                    entries.append(_make_entry(
                        filepath, lineno, line,
                        kind="public_investigation_data",
                        summary="Investigation/evidence data in publicly accessible directory",
                        confidence="high",
                        tier=2,
                    ))

            # ── Check 6: Unencrypted writes of sensitive data ──
            if _FILE_WRITE.search(line) and _SENSITIVE_VARS.search(line):
                entries.append(_make_entry(
                    filepath, lineno, line,
                    kind="unencrypted_sensitive_write",
                    summary="Unencrypted file write of sensitive advocacy data — use encrypted storage",
                    confidence="medium",
                    tier=2,
                ))

            # ── Check 7: Sensitive data in browser localStorage ──
            if _BROWSER_STORAGE.search(line) and _SENSITIVE_VARS.search(line):
                entries.append(_make_entry(
                    filepath, lineno, line,
                    kind="browser_storage_sensitive",
                    summary="Sensitive advocacy data stored in browser storage — not encrypted at rest",
                    confidence="medium",
                    tier=2,
                ))

            # ── Check 8: IP address logging ──
            if _LOG_PATTERNS.search(line) and re.search(
                r"\b(req\.ip|request\.ip|remote_addr|x.forwarded.for|client.ip)\b",
                line, re.IGNORECASE,
            ):
                entries.append(_make_entry(
                    filepath, lineno, line,
                    kind="ip_logging",
                    summary="IP address logging — may deanonymize activists in access logs",
                    confidence="high",
                    tier=2,
                ))

    return entries, {"advocacy_security": len(files)}


def _make_entry(
    filepath: str,
    lineno: int,
    line: str,
    *,
    kind: str,
    summary: str,
    confidence: str,
    tier: int,
) -> dict[str, Any]:
    return {
        "file": filepath,
        "line": lineno,
        "tier": tier,
        "confidence": confidence,
        "summary": summary,
        "name": kind,
        "detail": {
            "kind": kind,
            "content": line.strip()[:200],
        },
    }
