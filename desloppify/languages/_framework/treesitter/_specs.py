"""Compatibility bridge to grouped tree-sitter namespace module.

Canonical implementation lives in
desloppify.languages._framework.treesitter.specs.specs.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType


def load_compat_exports(
    namespace: dict[str, object],
    module_path: str,
) -> tuple[ModuleType, list[str]]:
    """Populate a wrapper module namespace from its canonical implementation."""
    impl = import_module(module_path)
    exports = [name for name in dir(impl) if not name.startswith("__")]
    namespace.update({name: getattr(impl, name) for name in exports})
    public = getattr(impl, "__all__", None)
    if public is None:
        public = [name for name in exports if not name.startswith("_")]
    return impl, list(public)


_IMPL, __all__ = load_compat_exports(
    globals(),
    "desloppify.languages._framework.treesitter.specs.specs",
)
