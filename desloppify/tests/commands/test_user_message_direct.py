"""Direct tests for base output user-message box rendering."""

from __future__ import annotations

from desloppify.base.output.user_message import print_user_message


def test_print_user_message_renders_box(capsys) -> None:
    print_user_message("short message")
    out = capsys.readouterr().out

    assert "┌" in out and "┐" in out
    assert "└" in out and "┘" in out
    assert "short message" in out


def test_print_user_message_wraps_long_text(capsys) -> None:
    text = (
        "This is a deliberately long sentence that should wrap across multiple "
        "lines inside the bordered user message box."
    )
    print_user_message(text)
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip().startswith("│")]

    # Includes one blank padding line at top and bottom plus content lines.
    assert len(lines) >= 4
    # Content should be present but split across multiple rows.
    assert "deliberately long sentence" in out
    assert "bordered user message" in out
    assert "box." in out
