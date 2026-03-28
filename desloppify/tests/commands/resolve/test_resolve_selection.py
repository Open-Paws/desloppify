"""Tests for resolve selection validation helpers."""

from __future__ import annotations

from desloppify.app.commands.helpers.attestation import (
    _MIN_NOTE_LENGTH,
    show_note_length_requirement,
    validate_note_length,
)


def test_validate_note_length_accepts_long_note():
    note = "I refactored the module extraction to use proper dependency injection patterns."
    assert validate_note_length(note) is True


def test_validate_note_length_rejects_short_note():
    assert validate_note_length("short") is False


def test_validate_note_length_rejects_none():
    assert validate_note_length(None) is False


def test_validate_note_length_rejects_empty():
    assert validate_note_length("") is False


def test_validate_note_length_strips_whitespace():
    """Whitespace-padded notes should be measured by stripped length."""
    short = " " * 60 + "x"
    assert validate_note_length(short) is False


def test_validate_note_length_exact_boundary():
    note = "x" * _MIN_NOTE_LENGTH
    assert validate_note_length(note) is True

    short = "x" * (_MIN_NOTE_LENGTH - 1)
    assert validate_note_length(short) is False


def test_show_note_length_requirement_outputs_warning(capsys):
    show_note_length_requirement("too short")
    captured = capsys.readouterr()
    assert "at least" in captured.err
    assert str(_MIN_NOTE_LENGTH) in captured.err
