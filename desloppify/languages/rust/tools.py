"""Shared Rust tool command strings and JSON diagnostic parsers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CLIPPY_WARNING_CMD = (
    "cargo clippy --workspace --all-targets --all-features --message-format=json "
    "-- -D warnings -W clippy::pedantic -W clippy::cargo -W clippy::unwrap_used "
    "-W clippy::expect_used -W clippy::panic -W clippy::todo -W clippy::unimplemented "
    "2>&1"
)
CARGO_ERROR_CMD = (
    "cargo check --workspace --all-targets --all-features --message-format=json 2>&1"
)
RUSTDOC_WARNING_CMD = (
    "cargo rustdoc --workspace --all-features --lib --message-format=json "
    "-- -D rustdoc::broken_intra_doc_links "
    "-D rustdoc::private_intra_doc_links "
    "-W rustdoc::missing_crate_level_docs 2>&1"
)


def _pick_primary_span(spans: list[dict[str, Any]]) -> dict[str, Any] | None:
    for span in spans:
        if span.get("is_primary"):
            return span
    return spans[0] if spans else None


def _parse_cargo_messages(
    output: str,
    scan_path: Path,
    *,
    allowed_levels: set[str],
) -> list[dict[str, Any]]:
    del scan_path
    entries: list[dict[str, Any]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        data = _parse_json_object_line(line)
        if data is None:
            continue
        if data.get("reason") != "compiler-message":
            continue
        message = data.get("message") or {}
        level = str(message.get("level") or "").lower()
        if level not in allowed_levels:
            continue
        span = _pick_primary_span(list(message.get("spans") or []))
        if not span:
            continue
        filename = str(span.get("file_name") or "").strip()
        line_no = span.get("line_start")
        if not filename or not isinstance(line_no, int):
            continue
        code = (message.get("code") or {}).get("code") or ""
        rendered = str(message.get("rendered") or message.get("message") or "").strip()
        if not rendered:
            continue
        summary = rendered.splitlines()[0].strip()
        if code and code not in summary:
            summary = f"[{code}] {summary}"
        entries.append(
            {
                "file": filename,
                "line": line_no,
                "message": summary,
            }
        )
    return entries


def _parse_json_object_line(line: str) -> dict[str, Any] | None:
    """Parse one cargo JSON line, ignoring human-readable noise."""
    if not line.startswith("{"):
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def parse_clippy_messages(output: str, scan_path: Path) -> list[dict[str, Any]]:
    """Parse cargo-clippy diagnostics, including denied warnings."""
    return _parse_cargo_messages(output, scan_path, allowed_levels={"warning", "error"})


def parse_cargo_errors(output: str, scan_path: Path) -> list[dict[str, Any]]:
    """Parse cargo-check compiler errors only."""
    return _parse_cargo_messages(output, scan_path, allowed_levels={"error"})


def parse_rustdoc_messages(output: str, scan_path: Path) -> list[dict[str, Any]]:
    """Parse rustdoc diagnostics, including denied warnings."""
    return _parse_cargo_messages(output, scan_path, allowed_levels={"warning", "error"})


__all__ = [
    "CARGO_ERROR_CMD",
    "CLIPPY_WARNING_CMD",
    "RUSTDOC_WARNING_CMD",
    "parse_cargo_errors",
    "parse_clippy_messages",
    "parse_rustdoc_messages",
]
