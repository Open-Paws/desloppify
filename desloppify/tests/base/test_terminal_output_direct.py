from __future__ import annotations

from desloppify.base.output import terminal


def test_no_color_flag_reads_environment_live(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert bool(terminal.NO_COLOR) is False
    monkeypatch.setenv("NO_COLOR", "1")
    assert bool(terminal.NO_COLOR) is True

