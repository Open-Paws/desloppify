"""Pytest collection wrapper for review misc test cases."""

from __future__ import annotations

from . import review_misc_cases as _cases

for _name in dir(_cases):
    if not (_name.startswith("Test") or _name.startswith("test_")):
        continue
    _obj = getattr(_cases, _name)
    globals()[_name] = _obj
    if hasattr(_obj, "__module__"):
        _obj.__module__ = __name__

__all__ = [name for name in globals() if name.startswith("Test") or name.startswith("test_")]
