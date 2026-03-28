"""Tests for concern generators (mechanical → subjective bridge)."""

from __future__ import annotations

from desloppify.base.registry import JUDGMENT_DETECTORS
from desloppify.engine._concerns.generators import (
    cleanup_stale_dismissals,
    generate_concerns,
)
from desloppify.engine._concerns.utils import _fingerprint

# ── Helpers ──────────────────────────────────────────────────────────


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


# ── Elevated single-detector signals ─────────────────────────────────


class TestElevatedSignals:
    """Files with a single judgment detector but strong signals get flagged."""

    def test_monster_function_flags(self):
        f = _make_issue(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "do_everything", "loc": 200},
        )
        concerns = generate_concerns(_state_with_issues(f))
        assert len(concerns) == 1
        c = concerns[0]
        assert c.type == "structural_complexity"
        assert c.file == "app/big.py"
        assert "do_everything" in c.summary
        assert "200" in c.summary

    def test_high_params_flags(self):
        f = _make_issue(
            "structural", "app/service.py", "struct",
            detail={"complexity_signals": ["12 params"]},
        )
        concerns = generate_concerns(_state_with_issues(f))
        assert len(concerns) == 1
        assert concerns[0].type == "interface_design"
        assert "12" in concerns[0].summary

    def test_deep_nesting_flags(self):
        f = _make_issue(
            "structural", "app/nested.py", "struct",
            detail={"complexity_signals": ["nesting depth 8"]},
        )
        concerns = generate_concerns(_state_with_issues(f))
        assert len(concerns) == 1
        assert concerns[0].type == "structural_complexity"
        assert "8" in concerns[0].summary

    def test_large_file_flags(self):
        f = _make_issue(
            "structural", "app/huge.py", "struct",
            detail={"loc": 500},
        )
        concerns = generate_concerns(_state_with_issues(f))
        assert len(concerns) == 1

    def test_duplication_flags(self):
        f = _make_issue("dupes", "app/dup.py", "dup1")
        concerns = generate_concerns(_state_with_issues(f))
        assert len(concerns) == 1
        assert concerns[0].type == "duplication_design"

    def test_coupling_flags(self):
        f = _make_issue("coupling", "app/coupled.py", "coupling1")
        concerns = generate_concerns(_state_with_issues(f))
        assert len(concerns) == 1
        assert concerns[0].type == "coupling_design"

    def test_responsibility_cohesion_flags(self):
        f = _make_issue("responsibility_cohesion", "app/mixed.py", "resp1")
        concerns = generate_concerns(_state_with_issues(f))
        assert len(concerns) == 1
        assert concerns[0].type == "mixed_responsibilities"


# ── Non-elevated single-detector — no flag ───────────────────────────


class TestNonElevatedSkipped:
    """A single judgment detector without elevated signals is NOT flagged."""

    def test_single_naming_not_flagged(self):
        f = _make_issue("naming", "app/file.py", "name1")
        assert generate_concerns(_state_with_issues(f)) == []

    def test_single_patterns_not_flagged(self):
        f = _make_issue("patterns", "app/file.py", "pat1")
        assert generate_concerns(_state_with_issues(f)) == []

    def test_moderate_structural_not_flagged(self):
        f = _make_issue(
            "structural", "app/ok.py", "struct",
            detail={"loc": 150, "complexity_signals": ["5 params", "nesting depth 3"]},
        )
        assert generate_concerns(_state_with_issues(f)) == []

    def test_non_monster_smell_not_flagged(self):
        f = _make_issue(
            "smells", "app/file.py", "smell",
            detail={"smell_id": "dead_useeffect"},
        )
        assert generate_concerns(_state_with_issues(f)) == []


# ── Clear-cut detectors — never flagged alone ────────────────────────


class TestClearCutDetectorsSkipped:
    """Auto-fixable / clear-cut detectors don't generate concerns."""

    def test_unused_not_flagged(self):
        f = _make_issue("unused", "app/file.py", "unused1")
        assert generate_concerns(_state_with_issues(f)) == []

    def test_logs_not_flagged(self):
        f = _make_issue("logs", "app/file.py", "log1")
        assert generate_concerns(_state_with_issues(f)) == []

    def test_security_not_flagged(self):
        f = _make_issue("security", "app/file.py", "sec1")
        assert generate_concerns(_state_with_issues(f)) == []

    def test_two_clearcut_not_flagged(self):
        """Two clear-cut detectors on the same file: no concern."""
        issues = [
            _make_issue("unused", "app/file.py", "unused1"),
            _make_issue("logs", "app/file.py", "log1"),
        ]
        assert generate_concerns(_state_with_issues(*issues)) == []


# ── Multi-detector files ─────────────────────────────────────────────


class TestMultiDetector:
    """Files with 2+ judgment detectors get flagged."""

    def test_two_judgment_detectors_flag(self):
        issues = [
            _make_issue("naming", "app/file.py", "name1"),
            _make_issue("patterns", "app/file.py", "pat1"),
        ]
        concerns = generate_concerns(_state_with_issues(*issues))
        assert len(concerns) == 1
        assert concerns[0].file == "app/file.py"

    def test_three_detectors_is_mixed_responsibilities(self):
        issues = [
            _make_issue("smells", "app/god.py", "smell1"),
            _make_issue("naming", "app/god.py", "name1"),
            _make_issue("structural", "app/god.py", "struct1"),
        ]
        concerns = generate_concerns(_state_with_issues(*issues))
        assert len(concerns) == 1
        assert concerns[0].type == "mixed_responsibilities"
        assert "3" in concerns[0].summary

    def test_judgment_plus_clearcut_not_flagged(self):
        """One judgment + one clear-cut detector = only 1 judgment, not enough."""
        issues = [
            _make_issue("naming", "app/file.py", "name1"),
            _make_issue("unused", "app/file.py", "unused1"),
        ]
        assert generate_concerns(_state_with_issues(*issues)) == []


# ── Evidence and questions ───────────────────────────────────────────


class TestEvidenceAndQuestions:
    """Concerns bundle full context for the LLM."""

    def test_evidence_includes_all_issues(self):
        issues = [
            _make_issue("smells", "app/f.py", "s1"),
            _make_issue("naming", "app/f.py", "n1"),
        ]
        concerns = generate_concerns(_state_with_issues(*issues))
        assert len(concerns) == 1
        evidence = concerns[0].evidence
        # Should include detector list and individual issue summaries.
        assert any("Flagged by:" in e for e in evidence)
        assert any("[smells]" in e for e in evidence)
        assert any("[naming]" in e for e in evidence)

    def test_evidence_includes_signals(self):
        f = _make_issue(
            "structural", "app/f.py", "struct",
            detail={"loc": 400, "complexity_signals": ["15 params", "nesting depth 9"]},
        )
        concerns = generate_concerns(_state_with_issues(f))
        evidence = concerns[0].evidence
        assert any("15" in e and "parameters" in e.lower() for e in evidence)
        assert any("9" in e and "nesting" in e.lower() for e in evidence)
        assert any("400" in e for e in evidence)

    def test_question_mentions_monster_function(self):
        f = _make_issue(
            "smells", "app/f.py", "m",
            detail={"smell_id": "monster_function", "function": "big_func", "loc": 200},
        )
        concerns = generate_concerns(_state_with_issues(f))
        assert "big_func" in concerns[0].question

    def test_question_mentions_params(self):
        f = _make_issue(
            "structural", "app/f.py", "s",
            detail={"complexity_signals": ["10 params"]},
        )
        concerns = generate_concerns(_state_with_issues(f))
        assert "parameter" in concerns[0].question.lower()

    def test_question_mentions_nesting(self):
        f = _make_issue(
            "structural", "app/f.py", "s",
            detail={"complexity_signals": ["nesting depth 7"]},
        )
        concerns = generate_concerns(_state_with_issues(f))
        assert "nesting" in concerns[0].question.lower()

    def test_question_mentions_duplication(self):
        f = _make_issue("dupes", "app/f.py", "d")
        concerns = generate_concerns(_state_with_issues(f))
        assert "duplication" in concerns[0].question.lower()

    def test_question_mentions_coupling(self):
        f = _make_issue("coupling", "app/f.py", "c")
        concerns = generate_concerns(_state_with_issues(f))
        assert "coupling" in concerns[0].question.lower()

    def test_question_mentions_orphaned(self):
        issues = [
            _make_issue("orphaned", "app/f.py", "o"),
            _make_issue("naming", "app/f.py", "n"),
        ]
        concerns = generate_concerns(_state_with_issues(*issues))
        assert any("dead" in concerns[0].question.lower() or
                    "orphan" in concerns[0].question.lower()
                    for _ in [1])


# ── Cross-file systemic patterns ─────────────────────────────────────


class TestSystemicPatterns:
    """3+ files with the same detector combo → systemic pattern."""

    def test_three_files_same_combo_flagged(self):
        issues = []
        for fname in ("a.py", "b.py", "c.py"):
            issues.append(_make_issue("smells", fname, "s"))
            issues.append(_make_issue("naming", fname, "n"))
        concerns = generate_concerns(_state_with_issues(*issues))
        systemic = [c for c in concerns if c.type == "systemic_pattern"]
        assert len(systemic) == 1
        assert "3 files" in systemic[0].summary

    def test_two_files_same_combo_not_flagged(self):
        issues = []
        for fname in ("a.py", "b.py"):
            issues.append(_make_issue("smells", fname, "s"))
            issues.append(_make_issue("naming", fname, "n"))
        concerns = generate_concerns(_state_with_issues(*issues))
        systemic = [c for c in concerns if c.type == "systemic_pattern"]
        assert len(systemic) == 0

    def test_systemic_plus_per_file(self):
        """Systemic patterns coexist with per-file concerns."""
        issues = []
        for fname in ("a.py", "b.py", "c.py"):
            issues.append(_make_issue("smells", fname, "s"))
            issues.append(_make_issue("naming", fname, "n"))
        concerns = generate_concerns(_state_with_issues(*issues))
        # Should have per-file concerns AND a systemic pattern.
        per_file = [c for c in concerns if c.type != "systemic_pattern"]
        systemic = [c for c in concerns if c.type == "systemic_pattern"]
        assert len(per_file) == 3
        assert len(systemic) == 1


# ── Dismissal tracking ──────────────────────────────────────────────


class TestDismissals:
    def test_dismissed_concern_suppressed(self):
        f = _make_issue(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "f", "loc": 200},
        )
        state = _state_with_issues(f)
        concerns = generate_concerns(state)
        assert len(concerns) == 1
        fp = concerns[0].fingerprint

        state["concern_dismissals"] = {
            fp: {
                "dismissed_at": "2026-01-01T00:00:00+00:00",
                "reasoning": "Single responsibility",
                "source_issue_ids": [f["id"]],
            }
        }
        assert generate_concerns(state) == []

    def test_dismissed_with_source_ids_suppresses(self):
        """Dismissals with matching source_issue_ids suppress the concern."""
        f = _make_issue(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "f", "loc": 200},
        )
        state = _state_with_issues(f)
        concerns = generate_concerns(state)
        assert len(concerns) == 1
        fp = concerns[0].fingerprint

        # Dismissal with correct source IDs suppresses.
        state["concern_dismissals"] = {
            fp: {
                "dismissed_at": "2026-01-01T00:00:00+00:00",
                "reasoning": "Acceptable complexity",
                "source_issue_ids": [f["id"]],
            }
        }
        assert generate_concerns(state) == []

    def test_stale_dismissal_cleaned_up(self):
        """Dismissals whose source issues are all gone get removed."""
        f = _make_issue(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "f", "loc": 200},
        )
        state = _state_with_issues(f)
        concerns = generate_concerns(state)
        fp = concerns[0].fingerprint

        # Create a dismissal referencing issues that no longer exist.
        state["concern_dismissals"] = {
            "stale_fp_abc123": {
                "dismissed_at": "2026-01-01T00:00:00+00:00",
                "reasoning": "Old dismissal",
                "source_issue_ids": ["gone::issue::1", "gone::issue::2"],
            },
            fp: {
                "dismissed_at": "2026-01-01T00:00:00+00:00",
                "reasoning": "Still valid",
                "source_issue_ids": [f["id"]],
            },
        }
        removed = cleanup_stale_dismissals(state)
        # Stale dismissal removed, valid one stays.
        assert removed == 1
        assert "stale_fp_abc123" not in state["concern_dismissals"]
        assert fp in state["concern_dismissals"]

    def test_stale_dismissal_without_source_ids_not_cleaned(self):
        """Dismissals without source_issue_ids are preserved (legacy)."""
        f = _make_issue(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "f", "loc": 200},
        )
        state = _state_with_issues(f)
        state["concern_dismissals"] = {
            "legacy_fp": {
                "dismissed_at": "2026-01-01T00:00:00+00:00",
                "reasoning": "Legacy dismissal",
            },
        }
        removed = cleanup_stale_dismissals(state)
        # Legacy dismissal without source_issue_ids is NOT cleaned up.
        assert removed == 0
        assert "legacy_fp" in state["concern_dismissals"]

    def test_cleanup_on_empty_state(self):
        """cleanup_stale_dismissals on empty state is a no-op."""
        assert cleanup_stale_dismissals({}) == 0
        assert cleanup_stale_dismissals({"concern_dismissals": {}}) == 0

    def test_generate_concerns_does_not_mutate_dismissals(self):
        """generate_concerns is a pure query — no side effects on state."""
        f = _make_issue(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "f", "loc": 200},
        )
        state = _state_with_issues(f)
        state["concern_dismissals"] = {
            "stale_fp": {
                "dismissed_at": "2026-01-01T00:00:00+00:00",
                "reasoning": "Old",
                "source_issue_ids": ["gone::id"],
            },
        }
        generate_concerns(state)
        # generate_concerns must NOT remove stale dismissals.
        assert "stale_fp" in state["concern_dismissals"]

    def test_dismissed_resurfaces_on_changed_issues(self):
        f = _make_issue(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "f", "loc": 200},
        )
        state = _state_with_issues(f)
        concerns = generate_concerns(state)
        fp = concerns[0].fingerprint

        state["concern_dismissals"] = {
            fp: {
                "dismissed_at": "2026-01-01T00:00:00+00:00",
                "reasoning": "Was fine",
                "source_issue_ids": ["other::issue::id"],
            }
        }
        assert len(generate_concerns(state)) == 1


# ── Edge cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_state(self):
        assert generate_concerns({}) == []
        assert generate_concerns({"issues": {}}) == []

    def test_non_open_issues_ignored(self):
        f = _make_issue(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "f", "loc": 200},
            status="fixed",
        )
        assert generate_concerns(_state_with_issues(f)) == []

    def test_holistic_file_ignored(self):
        """File '.' (holistic issues) should not generate concerns."""
        issues = [
            _make_issue("smells", ".", "s"),
            _make_issue("naming", ".", "n"),
            _make_issue("structural", ".", "st"),
            _make_issue("patterns", ".", "p"),
        ]
        assert generate_concerns(_state_with_issues(*issues)) == []

    def test_results_sorted_by_type_then_file(self):
        issues = [
            _make_issue("dupes", "z_file.py", "d"),
            _make_issue(
                "smells", "a_file.py", "m",
                detail={"smell_id": "monster_function", "function": "f", "loc": 150},
            ),
        ]
        concerns = generate_concerns(_state_with_issues(*issues))
        assert len(concerns) == 2
        for a, b in zip(concerns, concerns[1:], strict=False):
            assert (a.type, a.file) <= (b.type, b.file)

    def test_no_duplicate_fingerprints(self):
        issues = [
            _make_issue("smells", "a.py", "s"),
            _make_issue("naming", "a.py", "n"),
        ]
        concerns = generate_concerns(_state_with_issues(*issues))
        fps = [c.fingerprint for c in concerns]
        assert len(fps) == len(set(fps))


# ── Fingerprint stability ───────────────────────────────────────────


class TestFingerprint:
    def test_deterministic(self):
        fp1 = _fingerprint("t", "f.py", ("x", "y"))
        fp2 = _fingerprint("t", "f.py", ("y", "x"))
        assert fp1 == fp2

    def test_different_type_different_fingerprint(self):
        fp1 = _fingerprint("a", "f.py", ("x",))
        fp2 = _fingerprint("b", "f.py", ("x",))
        assert fp1 != fp2


# ── Registry integration ─────────────────────────────────────────


class TestRegistryIntegration:
    """JUDGMENT_DETECTORS derived from registry replaces hardcoded set."""

    def test_judgment_detectors_includes_cycles(self):
        assert "cycles" in JUDGMENT_DETECTORS

    def test_judgment_detectors_excludes_clearcut(self):
        for det in ("unused", "logs", "exports", "deprecated", "security",
                     "test_coverage", "stale_exclude"):
            assert det not in JUDGMENT_DETECTORS

    def test_judgment_detectors_includes_expected(self):
        expected = {
            "structural", "smells", "dupes", "boilerplate_duplication",
            "coupling", "cycles", "props", "react", "orphaned", "naming",
            "patterns", "facade", "single_use", "responsibility_cohesion",
            "signature", "dict_keys", "flat_dirs", "global_mutable_config",
            "private_imports", "layer_violation",
        }
        assert expected.issubset(JUDGMENT_DETECTORS)


