"""Direct coverage tests for holistic budget abstraction helpers."""

from __future__ import annotations

from desloppify.intelligence.review.context_holistic.budget import (
    axes as axes_mod,
    scan as scan_mod,
)


def test_budget_abstractions_axes_exports_expected_symbols() -> None:
    expected = {
        "_assemble_context",
        "_build_abstraction_leverage_context",
        "_build_definition_directness_context",
        "_build_delegation_density_context",
        "_build_indirection_cost_context",
        "_build_interface_honesty_context",
        "_build_type_discipline_context",
        "_compute_sub_axes",
    }
    assert set(axes_mod.__all__) == expected


def test_budget_abstractions_scan_reuses_axes_helpers() -> None:
    assert scan_mod._assemble_context is axes_mod._assemble_context
    assert scan_mod._compute_sub_axes is axes_mod._compute_sub_axes
    assert callable(scan_mod._abstractions_context)


def test_budget_abstractions_compute_sub_axes_callable() -> None:
    sub_axes = axes_mod._compute_sub_axes(
        wrapper_rate=0.1,
        util_files=[],
        indirection_hotspots=[],
        wide_param_bags=[],
        one_impl_interfaces=[],
        delegation_classes=[],
        facade_modules=[],
        typed_dict_violation_files=set(),
        total_typed_dict_violations=0,
    )
    assert set(sub_axes) == {
        "abstraction_leverage",
        "indirection_cost",
        "interface_honesty",
        "delegation_density",
        "definition_directness",
        "type_discipline",
    }
