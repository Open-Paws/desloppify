"""Tests for Rust cargo diagnostic parsing helpers."""

from __future__ import annotations

import json
from pathlib import Path

from desloppify.languages.rust.tools import parse_cargo_errors, parse_clippy_messages


def test_parse_clippy_messages_ignores_non_json_noise():
    message = {
        "reason": "compiler-message",
        "message": {
            "level": "warning",
            "message": "unused variable: `name`",
            "spans": [
                {
                    "is_primary": True,
                    "file_name": "src/lib.rs",
                    "line_start": 7,
                }
            ],
        },
    }
    output = "\n".join(
        [
            "Compiling demo v0.1.0",
            "[]",
            json.dumps(message),
        ]
    )

    entries = parse_clippy_messages(output, Path("."))

    assert entries == [
        {
            "file": "src/lib.rs",
            "line": 7,
            "message": "unused variable: `name`",
        }
    ]


def test_parse_cargo_errors_prefers_primary_span_and_includes_error_code():
    message = {
        "reason": "compiler-message",
        "message": {
            "level": "error",
            "message": "cannot find value `answer` in this scope",
            "code": {"code": "E0425"},
            "spans": [
                {
                    "is_primary": False,
                    "file_name": "src/other.rs",
                    "line_start": 3,
                },
                {
                    "is_primary": True,
                    "file_name": "src/lib.rs",
                    "line_start": 11,
                },
            ],
        },
    }

    entries = parse_cargo_errors(json.dumps(message), Path("."))

    assert entries == [
        {
            "file": "src/lib.rs",
            "line": 11,
            "message": "[E0425] cannot find value `answer` in this scope",
        }
    ]
