"""R language plugin — air + Jarl + lintr + tree-sitter + R-specific smells."""

from desloppify.languages._framework.base.types import DetectorPhase
from desloppify.languages._framework.generic_support.core import generic_lang
from desloppify.languages._framework.treesitter import R_SPEC
from desloppify.languages.r.phases_smells import phase_smells
from desloppify.languages.r import test_coverage as r_test_coverage_hooks

generic_lang(
    name="r",
    extensions=[".R", ".r"],
    tools=[
        {
            "label": "air",
            "cmd": "air format --check .",
            "fmt": "air",
            "id": "air_format",
            "tier": 1,
            "fix_cmd": "air format .",
        },
        {
            "label": "jarl",
            "cmd": "jarl check .",
            "fmt": "gnu",
            "id": "jarl_lint",
            "tier": 2,
            "fix_cmd": "jarl check . --fix --allow-dirty",
        },
        {
            "label": "lintr",
            "cmd": (
                "Rscript -e \"lintr::lint_dir('.')\""
            ),
            "fmt": "gnu",
            "id": "lintr_lint",
            "tier": 3,
            "fix_cmd": None,
        },
    ],
    exclude=[".Rhistory", ".RData", ".Rproj.user", "renv", "packrat"],
    depth="shallow",
    detect_markers=["DESCRIPTION", ".Rproj"],
    default_src="R",
    external_test_dirs=["tests/testthat"],
    test_file_extensions=[".R", ".r"],
    treesitter_spec=R_SPEC,
    custom_phases=[
        DetectorPhase("R code smells", phase_smells),
    ],
    test_coverage_module=r_test_coverage_hooks,
)

__all__ = [
    "generic_lang",
    "R_SPEC",
]
