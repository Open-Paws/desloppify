"""Direct tests for ``desloppify.app.commands.next`` package module."""

from __future__ import annotations

import importlib


def test_next_package_has_docstring() -> None:
    module = importlib.import_module("desloppify.app.commands.next")
    assert module.__doc__ == "Next command package with a stable package-root entrypoint."
