"""Tests for new budget_patterns scanners: dict[str,Any], enum bypass, type census.

Phase 3A: _find_dict_any_annotations
Phase 3B: _collect_enum_defs + _find_enum_bypass
Phase 3C: _census_type_strategies
"""

from __future__ import annotations

import ast

from desloppify.intelligence.review.context_holistic.budget.patterns_enums import (
    _census_type_strategies,
    _collect_enum_defs,
    _find_enum_bypass,
)
from desloppify.intelligence.review.context_holistic.budget.patterns_types import (
    _find_dict_any_annotations,
    _guess_alternative,
    _is_dict_str_any,
)


def _parse(content: str) -> ast.Module:
    return ast.parse(content)


# ── _is_dict_str_any ─────────────────────────────────────


class TestIsDictStrAny:
    """Detect dict[str, Any] annotations in AST nodes."""

    def test_dict_str_any_detected(self):
        tree = _parse("def f(x: dict[str, Any]) -> None: pass")
        fn = tree.body[0]
        assert _is_dict_str_any(fn.args.args[0].annotation) is True

    def test_dict_str_int_not_detected(self):
        tree = _parse("def f(x: dict[str, int]) -> None: pass")
        fn = tree.body[0]
        assert _is_dict_str_any(fn.args.args[0].annotation) is False

    def test_dict_int_any_not_detected(self):
        tree = _parse("def f(x: dict[int, Any]) -> None: pass")
        fn = tree.body[0]
        assert _is_dict_str_any(fn.args.args[0].annotation) is False

    def test_plain_dict_not_detected(self):
        tree = _parse("def f(x: dict) -> None: pass")
        fn = tree.body[0]
        assert _is_dict_str_any(fn.args.args[0].annotation) is False

    def test_list_str_not_detected(self):
        tree = _parse("def f(x: list[str]) -> None: pass")
        fn = tree.body[0]
        assert _is_dict_str_any(fn.args.args[0].annotation) is False


# ── _guess_alternative ───────────────────────────────────


class TestGuessAlternative:

    def test_exact_match(self):
        assert _guess_alternative("config", {"Config"}) == "Config"

    def test_substring_match(self):
        assert _guess_alternative("state", {"StateModel"}) == "StateModel"

    def test_no_match(self):
        assert _guess_alternative("data", {"Config", "Options"}) is None

    def test_empty_dict_names(self):
        assert _guess_alternative("config", set()) is None


# ── _find_dict_any_annotations ───────────────────────────


class TestFindDictAnyAnnotations:

    def test_param_annotation_detected(self):
        content = (
            "from typing import Any\n"
            "def process(state: dict[str, Any]) -> None:\n"
            "    pass\n"
        )
        trees = {"/fake/mod.py": _parse(content)}
        results = _find_dict_any_annotations(trees, set())
        assert len(results) == 1
        assert results[0]["param"] == "state"
        assert results[0]["function"] == "process"

    def test_return_annotation_detected(self):
        content = (
            "from typing import Any\n"
            "def build() -> dict[str, Any]:\n"
            "    return {}\n"
        )
        trees = {"/fake/mod.py": _parse(content)}
        results = _find_dict_any_annotations(trees, set())
        assert len(results) == 1
        assert results[0]["param"] == "(return)"

    def test_multiple_params_detected(self):
        content = (
            "from typing import Any\n"
            "def merge(a: dict[str, Any], b: dict[str, Any]) -> None:\n"
            "    pass\n"
        )
        trees = {"/fake/mod.py": _parse(content)}
        results = _find_dict_any_annotations(trees, set())
        assert len(results) == 2

    def test_kwonly_params_detected(self):
        content = (
            "from typing import Any\n"
            "def f(*, config: dict[str, Any]) -> None:\n"
            "    pass\n"
        )
        trees = {"/fake/mod.py": _parse(content)}
        results = _find_dict_any_annotations(trees, set())
        assert len(results) == 1
        assert results[0]["param"] == "config"

    def test_non_dict_any_params_ignored(self):
        content = "def f(x: int, y: str, z: list[str]) -> bool:\n    return True\n"
        trees = {"/fake/mod.py": _parse(content)}
        results = _find_dict_any_annotations(trees, set())
        assert results == []

    def test_known_alternative_suggested(self):
        content = (
            "from typing import Any\n"
            "def process(config: dict[str, Any]) -> None:\n"
            "    pass\n"
        )
        trees = {"/fake/mod.py": _parse(content)}
        results = _find_dict_any_annotations(trees, {"Config"})
        assert len(results) == 1
        assert results[0]["known_alternative"] == "Config"

    def test_no_alternative_when_unrelated(self):
        content = (
            "from typing import Any\n"
            "def process(data: dict[str, Any]) -> None:\n"
            "    pass\n"
        )
        trees = {"/fake/mod.py": _parse(content)}
        results = _find_dict_any_annotations(trees, {"Config"})
        assert len(results) == 1
        assert results[0]["known_alternative"] is None

    def test_vararg_kwarg_detected(self):
        content = (
            "from typing import Any\n"
            "def f(*args: dict[str, Any], **kwargs: dict[str, Any]) -> None:\n"
            "    pass\n"
        )
        trees = {"/fake/mod.py": _parse(content)}
        results = _find_dict_any_annotations(trees, set())
        params = {r["param"] for r in results}
        assert params == {"args", "kwargs"}

    def test_empty_trees(self):
        assert _find_dict_any_annotations({}, set()) == []


# ── _collect_enum_defs ───────────────────────────────────


class TestCollectEnumDefs:

    def test_str_enum_collected(self):
        content = (
            "from enum import StrEnum\n"
            "class Status(StrEnum):\n"
            '    ACTIVE = "active"\n'
            '    INACTIVE = "inactive"\n'
        )
        trees = {"/fake/enums.py": _parse(content)}
        defs = _collect_enum_defs(trees)
        # Keyed by (file, name) tuple
        key = next(k for k in defs if k[1] == "Status")
        assert defs[key]["members"]["ACTIVE"] == "active"
        assert defs[key]["members"]["INACTIVE"] == "inactive"

    def test_int_enum_collected(self):
        content = (
            "from enum import IntEnum\n"
            "class Priority(IntEnum):\n"
            "    LOW = 1\n"
            "    HIGH = 2\n"
        )
        trees = {"/fake/enums.py": _parse(content)}
        defs = _collect_enum_defs(trees)
        key = next(k for k in defs if k[1] == "Priority")
        assert defs[key]["members"]["LOW"] == 1

    def test_plain_enum_collected(self):
        content = (
            "from enum import Enum\n"
            "class Color(Enum):\n"
            '    RED = "red"\n'
        )
        trees = {"/fake/enums.py": _parse(content)}
        defs = _collect_enum_defs(trees)
        assert any(k[1] == "Color" for k in defs)

    def test_non_enum_class_ignored(self):
        content = "class Foo:\n    BAR = 1\n"
        trees = {"/fake/mod.py": _parse(content)}
        defs = _collect_enum_defs(trees)
        assert defs == {}

    def test_enum_without_constant_members_ignored(self):
        content = (
            "from enum import StrEnum\n"
            "class Empty(StrEnum):\n"
            "    pass\n"
        )
        trees = {"/fake/mod.py": _parse(content)}
        defs = _collect_enum_defs(trees)
        assert defs == {}

    def test_same_name_enums_from_different_files_preserved(self):
        content_a = (
            "from enum import StrEnum\n"
            "class Status(StrEnum):\n"
            '    ON = "on"\n'
        )
        content_b = (
            "from enum import StrEnum\n"
            "class Status(StrEnum):\n"
            '    READY = "ready"\n'
        )
        trees = {
            "/fake/a.py": _parse(content_a),
            "/fake/b.py": _parse(content_b),
        }
        defs = _collect_enum_defs(trees)
        status_keys = [k for k in defs if k[1] == "Status"]
        assert len(status_keys) == 2


# ── _find_enum_bypass ────────────────────────────────────


class TestFindEnumBypass:

    def test_string_comparison_matching_enum_value_detected(self):
        enum_content = (
            "from enum import StrEnum\n"
            "class Status(StrEnum):\n"
            '    ACTIVE = "active"\n'
        )
        usage_content = 'if x == "active":\n    pass\n'
        trees = {
            "/fake/enums.py": _parse(enum_content),
            "/fake/usage.py": _parse(usage_content),
        }
        defs = _collect_enum_defs(trees)
        results = _find_enum_bypass(trees, defs)
        # Should find the bypass in usage.py
        usage_hits = [r for r in results if "usage" in r["file"]]
        assert len(usage_hits) >= 1
        assert usage_hits[0]["enum_name"] == "Status"
        assert usage_hits[0]["member"] == "ACTIVE"
        assert usage_hits[0]["raw_value"] == "'active'"

    def test_int_comparison_matching_enum_value_detected(self):
        enum_content = (
            "from enum import IntEnum\n"
            "class Priority(IntEnum):\n"
            "    HIGH = 200\n"
        )
        usage_content = "if priority == 200:\n    pass\n"
        trees = {
            "/fake/enums.py": _parse(enum_content),
            "/fake/usage.py": _parse(usage_content),
        }
        defs = _collect_enum_defs(trees)
        results = _find_enum_bypass(trees, defs)
        usage_hits = [r for r in results if "usage" in r["file"]]
        assert len(usage_hits) >= 1
        assert usage_hits[0]["enum_name"] == "Priority"

    def test_non_matching_constant_ignored(self):
        enum_content = (
            "from enum import StrEnum\n"
            "class Status(StrEnum):\n"
            '    ACTIVE = "active"\n'
        )
        usage_content = 'if x == "unknown":\n    pass\n'
        trees = {
            "/fake/enums.py": _parse(enum_content),
            "/fake/usage.py": _parse(usage_content),
        }
        defs = _collect_enum_defs(trees)
        results = _find_enum_bypass(trees, defs)
        # Only the enum definition file might match (comparing with its own value)
        usage_hits = [r for r in results if "usage" in r["file"]]
        assert usage_hits == []

    def test_empty_enum_defs_returns_empty(self):
        trees = {"/fake/mod.py": _parse('if x == "foo":\n    pass\n')}
        assert _find_enum_bypass(trees, {}) == []

    def test_comparator_on_right_side_detected(self):
        enum_content = (
            "from enum import StrEnum\n"
            "class Mode(StrEnum):\n"
            '    FAST = "fast"\n'
        )
        usage_content = 'if "fast" == mode:\n    pass\n'
        trees = {
            "/fake/enums.py": _parse(enum_content),
            "/fake/usage.py": _parse(usage_content),
        }
        defs = _collect_enum_defs(trees)
        results = _find_enum_bypass(trees, defs)
        usage_hits = [r for r in results if "usage" in r["file"]]
        assert len(usage_hits) >= 1

    def test_gt_operator_not_flagged(self):
        """Only == and != should be flagged, not >, <, >=, <=."""
        enum_content = (
            "from enum import StrEnum\n"
            "class Status(StrEnum):\n"
            '    ACTIVE = "active"\n'
        )
        usage_content = 'if x > "active":\n    pass\n'
        trees = {
            "/fake/enums.py": _parse(enum_content),
            "/fake/usage.py": _parse(usage_content),
        }
        defs = _collect_enum_defs(trees)
        results = _find_enum_bypass(trees, defs)
        usage_hits = [r for r in results if "usage" in r["file"]]
        assert usage_hits == []

    def test_enum_own_file_not_flagged(self):
        """Comparisons in the file where the enum is defined should be skipped."""
        content = (
            "from enum import StrEnum\n"
            "class Status(StrEnum):\n"
            '    ACTIVE = "active"\n'
            '\n'
            'def check(x):\n'
            '    return x == "active"\n'
        )
        trees = {"/fake/enums.py": _parse(content)}
        defs = _collect_enum_defs(trees)
        results = _find_enum_bypass(trees, defs)
        assert results == []

    def test_generic_int_value_not_flagged(self):
        """IntEnum member with value 1 should not flag x == 1."""
        enum_content = (
            "from enum import IntEnum\n"
            "class Priority(IntEnum):\n"
            "    HIGH = 1\n"
        )
        usage_content = "if x == 1:\n    pass\n"
        trees = {
            "/fake/enums.py": _parse(enum_content),
            "/fake/usage.py": _parse(usage_content),
        }
        defs = _collect_enum_defs(trees)
        results = _find_enum_bypass(trees, defs)
        usage_hits = [r for r in results if "usage" in r["file"]]
        assert usage_hits == []


# ── _census_type_strategies ──────────────────────────────


class TestCensusTypeStrategies:

    def test_typed_dict_classified(self):
        content = (
            "from typing import TypedDict\n"
            "class Config(TypedDict):\n"
            "    name: str\n"
            "    value: int\n"
        )
        trees = {"/fake/mod.py": _parse(content)}
        census = _census_type_strategies(trees)
        assert "TypedDict" in census
        assert len(census["TypedDict"]) == 1
        assert census["TypedDict"][0]["name"] == "Config"
        assert census["TypedDict"][0]["field_count"] == 2

    def test_dataclass_classified(self):
        content = (
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Item:\n"
            "    name: str\n"
            "    price: float\n"
        )
        trees = {"/fake/mod.py": _parse(content)}
        census = _census_type_strategies(trees)
        assert "dataclass" in census
        assert len(census["dataclass"]) == 1
        assert census["dataclass"][0]["name"] == "Item"

    def test_frozen_dataclass_classified(self):
        content = (
            "from dataclasses import dataclass\n"
            "@dataclass(frozen=True)\n"
            "class Point:\n"
            "    x: float\n"
            "    y: float\n"
        )
        trees = {"/fake/mod.py": _parse(content)}
        census = _census_type_strategies(trees)
        assert "frozen_dataclass" in census
        assert census["frozen_dataclass"][0]["name"] == "Point"

    def test_named_tuple_classified(self):
        content = (
            "from typing import NamedTuple\n"
            "class Coord(NamedTuple):\n"
            "    x: float\n"
            "    y: float\n"
        )
        trees = {"/fake/mod.py": _parse(content)}
        census = _census_type_strategies(trees)
        assert "NamedTuple" in census
        assert census["NamedTuple"][0]["name"] == "Coord"

    def test_regular_class_not_classified(self):
        content = "class Foo:\n    bar: int = 42\n"
        trees = {"/fake/mod.py": _parse(content)}
        census = _census_type_strategies(trees)
        # Regular class matches none of the strategies
        assert census == {}

    def test_multiple_strategies_in_one_file(self):
        content = (
            "from typing import TypedDict, NamedTuple\n"
            "from dataclasses import dataclass\n"
            "\n"
            "class Config(TypedDict):\n"
            "    name: str\n"
            "\n"
            "@dataclass\n"
            "class Item:\n"
            "    value: int\n"
            "\n"
            "class Pair(NamedTuple):\n"
            "    a: int\n"
            "    b: int\n"
        )
        trees = {"/fake/mod.py": _parse(content)}
        census = _census_type_strategies(trees)
        assert "TypedDict" in census
        assert "dataclass" in census
        assert "NamedTuple" in census

    def test_empty_strategies_excluded(self):
        trees = {"/fake/mod.py": _parse("x = 1\n")}
        census = _census_type_strategies(trees)
        assert census == {}

    def test_frozen_false_classified_as_dataclass(self):
        content = (
            "from dataclasses import dataclass\n"
            "@dataclass(frozen=False)\n"
            "class Mutable:\n"
            "    x: int\n"
        )
        trees = {"/fake/mod.py": _parse(content)}
        census = _census_type_strategies(trees)
        assert "dataclass" in census
        assert "frozen_dataclass" not in census
