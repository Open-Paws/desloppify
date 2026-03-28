"""Focused tests for concern helper modules (signals/text/state/generators)."""

from __future__ import annotations

from desloppify.engine._concerns.generators import _cross_file_patterns, _file_concerns
from desloppify.engine._concerns.signals import _extract_signals, _has_elevated_signals
from desloppify.engine._concerns.state import _group_by_file, _open_issues
from desloppify.engine._concerns.text import (
    _build_evidence,
    _build_question,
    _build_summary,
    _classify,
)
from desloppify.engine._concerns.utils import _is_dismissed


def _make_issue(
    detector: str,
    file: str,
    name: str,
    *,
    detail: dict | None = None,
    status: str = "open",
) -> dict:
    fid = f"{detector}::{file}::{name}"
    return {
        "id": fid,
        "detector": detector,
        "file": file,
        "tier": 3,
        "confidence": "high",
        "summary": f"test issue {name}",
        "detail": detail or {},
        "status": status,
        "note": None,
        "first_seen": "2026-01-01T00:00:00+00:00",
        "last_seen": "2026-01-01T00:00:00+00:00",
        "resolved_at": None,
        "reopen_count": 0,
    }


def _state_with_issues(*issues: dict) -> dict:
    return {"issues": {f["id"]: f for f in issues}}


# ── Targeted _extract_signals tests ──────────────────────────────────


class TestExtractSignals:
    """Boundary conditions for _extract_signals."""

    def test_empty_issues(self):
        assert _extract_signals([]) == {}

    def test_structural_signals_extracted(self):
        issues = [
            _make_issue(
                "structural", "f.py", "s",
                detail={"loc": 200, "complexity_signals": ["10 params", "nesting depth 5"]},
            ),
        ]
        signals = _extract_signals(issues)
        assert signals["max_params"] == 10
        assert signals["max_nesting"] == 5
        assert signals["loc"] == 200

    def test_structural_signals_take_max_across_issues(self):
        issues = [
            _make_issue(
                "structural", "f.py", "s1",
                detail={"loc": 100, "complexity_signals": ["5 params"]},
            ),
            _make_issue(
                "structural", "f.py", "s2",
                detail={"loc": 80, "complexity_signals": ["12 params"]},
            ),
        ]
        signals = _extract_signals(issues)
        assert signals["max_params"] == 12
        assert signals["loc"] == 100

    def test_zero_and_negative_values_ignored(self):
        issues = [
            _make_issue(
                "structural", "f.py", "s",
                detail={"loc": 0, "complexity_signals": ["0 params"]},
            ),
        ]
        signals = _extract_signals(issues)
        assert "max_params" not in signals
        assert "loc" not in signals

    def test_empty_detail_ignored(self):
        issues = [
            _make_issue(
                "structural", "f.py", "s",
                detail={},
            ),
        ]
        signals = _extract_signals(issues)
        assert signals == {}

    def test_detail_not_a_dict_ignored(self):
        issues = [
            _make_issue(
                "structural", "f.py", "s",
                detail={"complexity_signals": "not_a_list"},
            ),
        ]
        signals = _extract_signals(issues)
        assert signals == {}

    def test_monster_function_extracted(self):
        issues = [
            _make_issue(
                "smells", "f.py", "m",
                detail={"smell_id": "monster_function", "function": "big_one", "loc": 300},
            ),
        ]
        signals = _extract_signals(issues)
        assert signals["monster_loc"] == 300
        assert signals["monster_funcs"] == ["big_one"]

    def test_multiple_monster_functions_takes_max_loc(self):
        issues = [
            _make_issue(
                "smells", "f.py", "m1",
                detail={"smell_id": "monster_function", "function": "f1", "loc": 100},
            ),
            _make_issue(
                "smells", "f.py", "m2",
                detail={"smell_id": "monster_function", "function": "f2", "loc": 250},
            ),
        ]
        signals = _extract_signals(issues)
        assert signals["monster_loc"] == 250
        assert signals["monster_funcs"] == ["f1", "f2"]

    def test_monster_without_function_name(self):
        issues = [
            _make_issue(
                "smells", "f.py", "m",
                detail={"smell_id": "monster_function", "loc": 200},
            ),
        ]
        signals = _extract_signals(issues)
        assert signals["monster_loc"] == 200
        assert "monster_funcs" not in signals

    def test_monster_without_loc(self):
        issues = [
            _make_issue(
                "smells", "f.py", "m",
                detail={"smell_id": "monster_function", "function": "f"},
            ),
        ]
        signals = _extract_signals(issues)
        assert "monster_loc" not in signals
        assert signals["monster_funcs"] == ["f"]

    def test_non_monster_smells_produce_no_signals(self):
        issues = [
            _make_issue(
                "smells", "f.py", "s",
                detail={"smell_id": "star_import"},
            ),
        ]
        signals = _extract_signals(issues)
        assert signals == {}

    def test_non_structural_non_smell_detectors_ignored(self):
        issues = [
            _make_issue("coupling", "f.py", "c1"),
            _make_issue("dupes", "f.py", "d1"),
            _make_issue("naming", "f.py", "n1"),
        ]
        signals = _extract_signals(issues)
        assert signals == {}

    def test_mixed_structural_and_monster(self):
        issues = [
            _make_issue(
                "structural", "f.py", "s",
                detail={"loc": 350, "complexity_signals": ["9 params"]},
            ),
            _make_issue(
                "smells", "f.py", "m",
                detail={"smell_id": "monster_function", "function": "do_all", "loc": 180},
            ),
        ]
        signals = _extract_signals(issues)
        assert signals["max_params"] == 9
        assert signals["loc"] == 350
        assert signals["monster_loc"] == 180
        assert signals["monster_funcs"] == ["do_all"]


# ── Targeted _has_elevated_signals tests ─────────────────────────────


class TestHasElevatedSignals:
    """Boundary conditions for threshold checks."""

    def test_params_at_boundary_7_not_elevated(self):
        issues = [
            _make_issue(
                "structural", "f.py", "s",
                detail={"complexity_signals": ["7 params"]},
            ),
        ]
        assert _has_elevated_signals(issues) is False

    def test_params_at_boundary_8_is_elevated(self):
        issues = [
            _make_issue(
                "structural", "f.py", "s",
                detail={"complexity_signals": ["8 params"]},
            ),
        ]
        assert _has_elevated_signals(issues) is True

    def test_nesting_at_boundary_5_not_elevated(self):
        issues = [
            _make_issue(
                "structural", "f.py", "s",
                detail={"complexity_signals": ["nesting depth 5"]},
            ),
        ]
        assert _has_elevated_signals(issues) is False

    def test_nesting_at_boundary_6_is_elevated(self):
        issues = [
            _make_issue(
                "structural", "f.py", "s",
                detail={"complexity_signals": ["nesting depth 6"]},
            ),
        ]
        assert _has_elevated_signals(issues) is True

    def test_loc_at_boundary_299_not_elevated(self):
        issues = [
            _make_issue(
                "structural", "f.py", "s",
                detail={"loc": 299},
            ),
        ]
        assert _has_elevated_signals(issues) is False

    def test_loc_at_boundary_300_is_elevated(self):
        issues = [
            _make_issue(
                "structural", "f.py", "s",
                detail={"loc": 300},
            ),
        ]
        assert _has_elevated_signals(issues) is True

    def test_boilerplate_duplication_is_elevated(self):
        issues = [_make_issue("boilerplate_duplication", "f.py", "bd")]
        assert _has_elevated_signals(issues) is True

    def test_responsibility_cohesion_is_elevated(self):
        issues = [_make_issue("responsibility_cohesion", "f.py", "rc")]
        assert _has_elevated_signals(issues) is True

    def test_empty_issues_not_elevated(self):
        assert _has_elevated_signals([]) is False

    def test_naming_alone_not_elevated(self):
        issues = [_make_issue("naming", "f.py", "n")]
        assert _has_elevated_signals(issues) is False


# ── Targeted _classify tests ─────────────────────────────────────────


class TestClassify:
    """Concern type classification priority."""

    def test_three_detectors_is_mixed_responsibilities(self):
        assert _classify({"a", "b", "c"}, {}) == "mixed_responsibilities"

    def test_dupes_wins_over_coupling(self):
        assert _classify({"dupes", "coupling"}, {}) == "duplication_design"

    def test_boilerplate_duplication_classified(self):
        assert _classify({"boilerplate_duplication"}, {}) == "duplication_design"

    def test_monster_loc_is_structural_complexity(self):
        assert _classify({"smells"}, {"monster_loc": 200}) == "structural_complexity"

    def test_coupling_alone(self):
        assert _classify({"coupling"}, {}) == "coupling_design"

    def test_high_params_is_interface_design(self):
        assert _classify({"structural"}, {"max_params": 8}) == "interface_design"

    def test_deep_nesting_is_structural_complexity(self):
        assert _classify({"structural"}, {"max_nesting": 6}) == "structural_complexity"

    def test_responsibility_cohesion_alone(self):
        assert _classify({"responsibility_cohesion"}, {}) == "mixed_responsibilities"

    def test_fallback_is_design_concern(self):
        assert _classify({"naming"}, {}) == "design_concern"

    def test_priority_three_detectors_beats_dupes(self):
        """3+ detectors wins even when dupes is present."""
        assert _classify({"dupes", "naming", "coupling"}, {}) == "mixed_responsibilities"


# ── Targeted _build_summary tests ────────────────────────────────────


class TestBuildSummary:
    """Summary text for each concern type."""

    def test_mixed_responsibilities_summary(self):
        s = _build_summary("mixed_responsibilities", {"a", "b", "c"}, {})
        assert "3 detectors" in s
        assert "responsibilities" in s

    def test_structural_complexity_monster(self):
        s = _build_summary(
            "structural_complexity", {"smells"}, {"monster_loc": 200, "monster_funcs": ["f1", "f2"]}
        )
        assert "200" in s
        assert "f1" in s
        assert "monster" in s.lower()

    def test_structural_complexity_nesting(self):
        s = _build_summary("structural_complexity", {"structural"}, {"max_nesting": 7})
        assert "nesting" in s.lower()
        assert "7" in s

    def test_structural_complexity_params(self):
        s = _build_summary("structural_complexity", {"structural"}, {"max_params": 10})
        assert "10" in s
        assert "parameter" in s.lower()

    def test_structural_complexity_no_parts_fallback(self):
        s = _build_summary("structural_complexity", set(), {})
        assert "elevated signals" in s

    def test_duplication_design_summary(self):
        s = _build_summary("duplication_design", {"dupes"}, {})
        assert "duplication" in s.lower()

    def test_coupling_design_summary(self):
        s = _build_summary("coupling_design", {"coupling"}, {})
        assert "coupling" in s.lower()

    def test_interface_design_summary(self):
        s = _build_summary("interface_design", {"structural"}, {"max_params": 15})
        assert "15" in s
        assert "parameter" in s.lower()

    def test_default_summary_lists_detectors(self):
        s = _build_summary("design_concern", {"naming", "patterns"}, {})
        assert "naming" in s
        assert "patterns" in s


# ── Targeted _build_evidence tests ───────────────────────────────────


class TestBuildEvidence:
    """Evidence tuple construction."""

    def test_empty_issues_minimal_evidence(self):
        evidence = _build_evidence([], {})
        assert len(evidence) >= 1
        assert "Flagged by:" in evidence[0]

    def test_monster_func_names_capped_at_3(self):
        signals = {
            "monster_loc": 200,
            "monster_funcs": ["f1", "f2", "f3", "f4", "f5"],
        }
        evidence = _build_evidence([], signals)
        monster_ev = [e for e in evidence if "Monster" in e]
        assert len(monster_ev) == 1
        # Only first 3 function names
        assert "f1" in monster_ev[0]
        assert "f3" in monster_ev[0]
        assert "f4" not in monster_ev[0]

    def test_issue_summaries_capped_at_10(self):
        issues = [
            _make_issue("smells", "f.py", f"s{i}") for i in range(15)
        ]
        evidence = _build_evidence(issues, {})
        summary_entries = [e for e in evidence if e.startswith("[")]
        assert len(summary_entries) == 10

    def test_signals_below_threshold_omitted(self):
        """Params < 8 and nesting < 6 not included in evidence."""
        signals = {"max_params": 5, "max_nesting": 4, "loc": 100}
        evidence = _build_evidence([], signals)
        assert any("100" in e for e in evidence)  # loc included
        assert not any("parameters" in e.lower() for e in evidence)
        assert not any("nesting" in e.lower() for e in evidence)


# ── Targeted _build_question tests ───────────────────────────────────


class TestBuildQuestion:
    """Question construction for each signal type."""

    def test_no_signals_fallback_question(self):
        q = _build_question(set(), {})
        assert "review" in q.lower()

    def test_multiple_signal_types_combined(self):
        """Question includes all applicable parts."""
        q = _build_question(
            {"dupes", "coupling", "orphaned", "responsibility_cohesion"},
            {"monster_funcs": ["big"], "max_params": 10, "max_nesting": 7},
        )
        assert "duplication" in q.lower()
        assert "coupling" in q.lower()
        assert "dead" in q.lower() or "orphan" in q.lower()
        assert "parameter" in q.lower()
        assert "nesting" in q.lower()
        assert "big" in q
        assert "responsibilit" in q.lower()


# ── Targeted _group_by_file and _open_issues tests ─────────────────


class TestGroupByFileAndOpenIssues:
    """Filtering and grouping helpers."""

    def test_open_issues_filters_non_open(self):
        state = _state_with_issues(
            _make_issue("smells", "a.py", "s1", status="open"),
            _make_issue("smells", "b.py", "s2", status="fixed"),
            _make_issue("smells", "c.py", "s3", status="wontfix"),
        )
        result = _open_issues(state)
        assert len(result) == 1
        assert result[0]["file"] == "a.py"

    def test_open_issues_empty_state(self):
        assert _open_issues({}) == []
        assert _open_issues({"issues": {}}) == []

    def test_open_issues_skips_non_dict(self):
        state = {"issues": {"id1": "not_a_dict", "id2": 42}}
        assert _open_issues(state) == []

    def test_group_by_file_excludes_dot_file(self):
        state = _state_with_issues(
            _make_issue("smells", ".", "holistic"),
            _make_issue("smells", "a.py", "s1"),
        )
        grouped = _group_by_file(state)
        assert "." not in grouped
        assert "a.py" in grouped

    def test_group_by_file_excludes_empty_file(self):
        f = _make_issue("smells", "a.py", "s1")
        f["file"] = ""
        state = {"issues": {f["id"]: f}}
        grouped = _group_by_file(state)
        assert "" not in grouped

    def test_group_by_file_groups_correctly(self):
        state = _state_with_issues(
            _make_issue("smells", "a.py", "s1"),
            _make_issue("naming", "a.py", "n1"),
            _make_issue("smells", "b.py", "s2"),
        )
        grouped = _group_by_file(state)
        assert len(grouped["a.py"]) == 2
        assert len(grouped["b.py"]) == 1


# ── Targeted _is_dismissed tests ─────────────────────────────────────


class TestIsDismissed:
    """Dismissal matching logic."""

    def test_not_dismissed_when_no_entry(self):
        assert _is_dismissed({}, "fp123", ("id1",)) is False

    def test_not_dismissed_when_entry_is_not_dict(self):
        assert _is_dismissed({"fp123": "invalid"}, "fp123", ("id1",)) is False
        assert _is_dismissed({"fp123": None}, "fp123", ("id1",)) is False

    def test_dismissed_when_source_ids_match(self):
        dismissals = {"fp123": {"source_issue_ids": ["id1", "id2"]}}
        assert _is_dismissed(dismissals, "fp123", ("id2", "id1")) is True

    def test_not_dismissed_when_source_ids_differ(self):
        dismissals = {"fp123": {"source_issue_ids": ["id1"]}}
        assert _is_dismissed(dismissals, "fp123", ("id1", "id_new")) is False

    def test_dismissed_with_empty_sources_matches_empty(self):
        dismissals = {"fp123": {"source_issue_ids": []}}
        assert _is_dismissed(dismissals, "fp123", ()) is True


# ── Targeted _file_concerns generator tests ──────────────────────────


class TestFileConcernsGenerator:
    """Direct tests for the _file_concerns generator."""

    def test_single_judgment_below_threshold_no_concern(self):
        """One judgment detector, no elevated signals: skipped."""
        state = _state_with_issues(
            _make_issue("naming", "a.py", "n1"),
        )
        assert _file_concerns(state, {}) == []

    def test_two_judgment_detectors_generates_concern(self):
        state = _state_with_issues(
            _make_issue("naming", "a.py", "n1"),
            _make_issue("patterns", "a.py", "p1"),
        )
        concerns = _file_concerns(state, {})
        assert len(concerns) == 1
        assert concerns[0].file == "a.py"

    def test_clearcut_issues_excluded_from_judgment_count(self):
        """Clear-cut detectors don't count toward the 2-detector threshold,
        but 1 judgment + 2 mechanical issues does trigger the lowered threshold."""
        state = _state_with_issues(
            _make_issue("naming", "a.py", "n1"),
            _make_issue("unused", "a.py", "u1"),
            _make_issue("logs", "a.py", "l1"),
        )
        # 1 judgment (naming) + 2 mechanical (unused, logs) = 3 total → triggers
        concerns = _file_concerns(state, {})
        assert len(concerns) == 1
        assert concerns[0].file == "a.py"

    def test_dismissal_suppresses_file_concern(self):
        state = _state_with_issues(
            _make_issue("naming", "a.py", "n1"),
            _make_issue("patterns", "a.py", "p1"),
        )
        # Generate to get the fingerprint
        concerns = _file_concerns(state, {})
        fp = concerns[0].fingerprint
        src_ids = concerns[0].source_issues

        dismissals = {fp: {"source_issue_ids": list(src_ids)}}
        assert _file_concerns(state, dismissals) == []

    def test_multiple_files_each_get_concern(self):
        state = _state_with_issues(
            _make_issue("naming", "a.py", "n1"),
            _make_issue("patterns", "a.py", "p1"),
            _make_issue("naming", "b.py", "n2"),
            _make_issue("coupling", "b.py", "c2"),
        )
        concerns = _file_concerns(state, {})
        files = {c.file for c in concerns}
        assert files == {"a.py", "b.py"}

    def test_concern_bundles_all_judgment_issues(self):
        """The concern's source_issues includes ALL judgment issues for the file."""
        state = _state_with_issues(
            _make_issue("naming", "a.py", "n1"),
            _make_issue("patterns", "a.py", "p1"),
            _make_issue("smells", "a.py", "s1"),
        )
        concerns = _file_concerns(state, {})
        assert len(concerns) == 1
        assert len(concerns[0].source_issues) == 3


# ── Targeted _cross_file_patterns generator tests ────────────────────


class TestCrossFilePatternsGenerator:
    """Direct tests for the _cross_file_patterns generator."""

    def test_exactly_3_files_triggers_pattern(self):
        state = _state_with_issues(
            *[
                f
                for fname in ("a.py", "b.py", "c.py")
                for f in (
                    _make_issue("smells", fname, "s"),
                    _make_issue("naming", fname, "n"),
                )
            ]
        )
        patterns = _cross_file_patterns(state, {})
        assert len(patterns) == 1
        assert patterns[0].type == "systemic_pattern"
        assert "3 files" in patterns[0].summary

    def test_exactly_2_files_below_threshold(self):
        state = _state_with_issues(
            *[
                f
                for fname in ("a.py", "b.py")
                for f in (
                    _make_issue("smells", fname, "s"),
                    _make_issue("naming", fname, "n"),
                )
            ]
        )
        patterns = _cross_file_patterns(state, {})
        assert patterns == []

    def test_single_detector_per_file_no_pattern(self):
        """Files need 2+ judgment detectors each for cross-file patterns."""
        state = _state_with_issues(
            *[_make_issue("naming", f"file{i}.py", "n") for i in range(5)]
        )
        patterns = _cross_file_patterns(state, {})
        assert patterns == []

    def test_different_combos_no_pattern(self):
        """Files with different detector combos don't form a pattern."""
        state = _state_with_issues(
            _make_issue("smells", "a.py", "s"),
            _make_issue("naming", "a.py", "n"),
            _make_issue("coupling", "b.py", "c"),
            _make_issue("patterns", "b.py", "p"),
            _make_issue("dupes", "c.py", "d"),
            _make_issue("structural", "c.py", "st"),
        )
        patterns = _cross_file_patterns(state, {})
        assert patterns == []

    def test_pattern_evidence_lists_files(self):
        state = _state_with_issues(
            *[
                f
                for fname in ("alpha.py", "beta.py", "gamma.py", "delta.py")
                for f in (
                    _make_issue("coupling", fname, "c"),
                    _make_issue("structural", fname, "s"),
                )
            ]
        )
        patterns = _cross_file_patterns(state, {})
        assert len(patterns) == 1
        assert "4 files" in patterns[0].summary
        # Evidence should list affected files
        assert any("alpha.py" in e for e in patterns[0].evidence)

    def test_pattern_dismissal_suppresses(self):
        state = _state_with_issues(
            *[
                f
                for fname in ("a.py", "b.py", "c.py")
                for f in (
                    _make_issue("smells", fname, "s"),
                    _make_issue("naming", fname, "n"),
                )
            ]
        )
        patterns = _cross_file_patterns(state, {})
        assert len(patterns) == 1
        fp = patterns[0].fingerprint
        src_ids = patterns[0].source_issues

        dismissals = {fp: {"source_issue_ids": list(src_ids)}}
        assert _cross_file_patterns(state, dismissals) == []

    def test_multiple_distinct_patterns(self):
        """Two different detector combos each appearing in 3+ files."""
        issues = []
        for fname in ("a.py", "b.py", "c.py"):
            issues.append(_make_issue("smells", fname, "s"))
            issues.append(_make_issue("naming", fname, "n"))
        for fname in ("x.py", "y.py", "z.py"):
            issues.append(_make_issue("coupling", fname, "c"))
            issues.append(_make_issue("structural", fname, "st"))
        state = _state_with_issues(*issues)
        patterns = _cross_file_patterns(state, {})
        assert len(patterns) == 2
        types = {p.type for p in patterns}
        assert types == {"systemic_pattern"}

    def test_empty_state_no_patterns(self):
        assert _cross_file_patterns({}, {}) == []
        assert _cross_file_patterns({"issues": {}}, {}) == []

    def test_pattern_fingerprint_stable_across_file_order(self):
        """Fingerprint is the same regardless of issue insertion order."""
        issues_a = [
            _make_issue("smells", "c.py", "s"),
            _make_issue("naming", "c.py", "n"),
            _make_issue("smells", "a.py", "s"),
            _make_issue("naming", "a.py", "n"),
            _make_issue("smells", "b.py", "s"),
            _make_issue("naming", "b.py", "n"),
        ]
        issues_b = [
            _make_issue("smells", "b.py", "s"),
            _make_issue("naming", "b.py", "n"),
            _make_issue("smells", "a.py", "s"),
            _make_issue("naming", "a.py", "n"),
            _make_issue("smells", "c.py", "s"),
            _make_issue("naming", "c.py", "n"),
        ]
        p1 = _cross_file_patterns(_state_with_issues(*issues_a), {})
        p2 = _cross_file_patterns(_state_with_issues(*issues_b), {})
        assert len(p1) == 1 and len(p2) == 1
        assert p1[0].fingerprint == p2[0].fingerprint
