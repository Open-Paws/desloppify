"""Compatibility bridge to grouped tree-sitter namespace module.

Canonical implementation lives in desloppify.languages._framework.treesitter.specs.specs.
"""

from __future__ import annotations

from desloppify.languages._framework.treesitter.specs.specs import *  # noqa: F401, F403
from desloppify.languages._framework.treesitter.specs.specs import __all__
