"""Direct coverage tests for review external-session helper module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from desloppify.app.commands.review import external as external_mod
from desloppify.base.exception_sets import CommandError


def test_parse_iso_handles_invalid_and_naive_inputs() -> None:
    assert external_mod._parse_iso(None) is None
    assert external_mod._parse_iso("") is None
    assert external_mod._parse_iso("not-a-date") is None

    naive = external_mod._parse_iso("2026-03-08T12:34:56")
    assert naive is not None
    assert naive.tzinfo == UTC


def test_parse_iso_converts_offset_to_utc() -> None:
    dt = external_mod._parse_iso("2026-03-08T12:00:00+02:00")
    assert dt is not None
    assert dt.tzinfo == UTC
    assert dt.hour == 10


def test_validate_session_id_rejects_empty_and_path_segments() -> None:
    with pytest.raises(CommandError):
        external_mod._validate_session_id("")

    with pytest.raises(CommandError):
        external_mod._validate_session_id("../bad")

    with pytest.raises(CommandError):
        external_mod._validate_session_id("bad/name")

    external_mod._validate_session_id("ext_20260308_deadbeef")


def test_build_template_payload_uses_dimension_names() -> None:
    packet = {
        "dimensions": ["naming_quality", "abstraction_fitness", "", None, "naming_quality"],
    }

    payload = external_mod._build_template_payload(
        packet,
        session_id="ext_id",
        token="tok",
    )

    assert payload["session"] == {"id": "ext_id", "token": "tok"}
    assert set(payload["assessments"].keys()) == {"naming_quality", "abstraction_fitness"}
    assert payload["dimension_notes"] == {}
    assert payload["issues"] == []


def test_canonical_external_payload_adds_provenance_and_strips_session() -> None:
    raw = {
        "session": {"id": "ext_1", "token": "tok_1"},
        "assessments": {"naming_quality": 77},
        "issues": [{"id": "review::a"}],
    }
    session = {
        "session_id": "ext_1",
        "token": "tok_1",
        "runner": "claude",
        "blind_packet_path": "/tmp/blind.json",
        "packet_sha256": "abc123",
    }

    payload = external_mod._canonical_external_payload(raw, session=session)

    assert "session" not in payload
    assert payload["assessments"] == {"naming_quality": 77}
    assert payload["issues"] == [{"id": "review::a"}]
    assert payload["provenance"]["runner"] == "claude"
    assert payload["provenance"]["session_id"] == "ext_1"
    assert payload["provenance"]["packet_path"] == "/tmp/blind.json"
    assert payload["provenance"]["packet_sha256"] == "abc123"


def test_canonical_external_payload_rejects_session_mismatch() -> None:
    raw = {"session": {"id": "ext_wrong", "token": "tok"}}
    session = {"session_id": "ext_ok", "token": "tok"}

    with pytest.raises(CommandError):
        external_mod._canonical_external_payload(raw, session=session)


def test_ensure_session_open_and_not_expired_guards() -> None:
    external_mod._ensure_session_open({"status": "open"})

    with pytest.raises(CommandError):
        external_mod._ensure_session_open({"status": "submitted"})

    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat(timespec="seconds")
    external_mod._ensure_session_not_expired({"expires_at": future})

    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat(timespec="seconds")
    with pytest.raises(CommandError):
        external_mod._ensure_session_not_expired({"expires_at": past})

    with pytest.raises(CommandError):
        external_mod._ensure_session_not_expired({"expires_at": "invalid"})
