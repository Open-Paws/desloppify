"""Focused unit tests for security.scanner helpers."""

from __future__ import annotations

from desloppify.engine.detectors.security import scanner as scanner_mod


def test_scan_line_aggregates_all_rule_entries(monkeypatch):
    monkeypatch.setattr(
        scanner_mod,
        "_secret_format_entries",
        lambda *_args, **_kwargs: [{"kind": "format"}],
    )
    monkeypatch.setattr(
        scanner_mod,
        "_secret_name_entries",
        lambda *_args, **_kwargs: [{"kind": "name"}],
    )
    monkeypatch.setattr(
        scanner_mod,
        "_insecure_random_entries",
        lambda *_args, **_kwargs: [{"kind": "random"}],
    )
    monkeypatch.setattr(
        scanner_mod,
        "_weak_crypto_entries",
        lambda *_args, **_kwargs: [{"kind": "weak"}],
    )
    monkeypatch.setattr(
        scanner_mod,
        "_sensitive_log_entries",
        lambda *_args, **_kwargs: [{"kind": "log"}],
    )

    entries = scanner_mod._scan_line_for_security_entries(
        filepath="src/module.py",
        line_num=7,
        line="api_key = 'secret'",
        is_test=True,
    )

    # Verify all five rule sources contribute exactly one entry each
    assert len(entries) == 5
    assert isinstance(entries, list)
    assert all(isinstance(e, dict) for e in entries)
    assert [entry["kind"] for entry in entries] == [
        "format",
        "name",
        "random",
        "weak",
        "log",
    ]
    # Each entry contains exactly the "kind" key from our stubs
    assert all(set(e.keys()) == {"kind"} for e in entries)


def test_scan_line_passes_is_test_only_to_secret_rules(monkeypatch):
    seen: dict[str, object] = {}

    def _secret_format(filepath, line_num, line, is_test):
        seen["format"] = (filepath, line_num, line, is_test)
        return []

    def _secret_name(filepath, line_num, line, is_test):
        seen["name"] = (filepath, line_num, line, is_test)
        return []

    def _random(filepath, line_num, line):
        seen["random"] = (filepath, line_num, line)
        return []

    def _weak_crypto(filepath, line_num, line):
        seen["weak_crypto"] = (filepath, line_num, line)
        return []

    def _sensitive_log(filepath, line_num, line):
        seen["sensitive_log"] = (filepath, line_num, line)
        return []

    monkeypatch.setattr(scanner_mod, "_secret_format_entries", _secret_format)
    monkeypatch.setattr(scanner_mod, "_secret_name_entries", _secret_name)
    monkeypatch.setattr(scanner_mod, "_insecure_random_entries", _random)
    monkeypatch.setattr(scanner_mod, "_weak_crypto_entries", _weak_crypto)
    monkeypatch.setattr(scanner_mod, "_sensitive_log_entries", _sensitive_log)

    result = scanner_mod._scan_line_for_security_entries(
        filepath="src/file.ts",
        line_num=12,
        line="const token = random.random()",
        is_test=False,
    )

    # Return value should be empty since all stubs return []
    assert result == []
    assert isinstance(result, list)

    # All five rule functions were called
    assert len(seen) == 5
    assert set(seen.keys()) == {"format", "name", "random", "weak_crypto", "sensitive_log"}

    # Secret rules receive is_test as 4th argument
    assert seen["format"] == (
        "src/file.ts",
        12,
        "const token = random.random()",
        False,
    )
    assert seen["name"] == (
        "src/file.ts",
        12,
        "const token = random.random()",
        False,
    )
    # Non-secret rules receive only (filepath, line_num, line) — no is_test
    assert seen["random"] == ("src/file.ts", 12, "const token = random.random()")
    assert len(seen["random"]) == 3  # exactly 3 args, no is_test
    assert seen["weak_crypto"] == ("src/file.ts", 12, "const token = random.random()")
    assert len(seen["weak_crypto"]) == 3
    assert seen["sensitive_log"] == ("src/file.ts", 12, "const token = random.random()")
    assert len(seen["sensitive_log"]) == 3

