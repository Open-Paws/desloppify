"""Tests for prompt section rendering — concern signals and judgment findings."""

from __future__ import annotations

from desloppify.app.commands.review.prompt_sections import (
    build_batch_context,
    explode_to_single_dimension,
    render_judgment_findings_section,
    render_mechanical_concern_signals,
)


class TestRenderMechanicalConcernSignals:
    def test_empty_signals(self):
        assert render_mechanical_concern_signals({}) == ""
        assert render_mechanical_concern_signals({"concern_signals": []}) == ""

    def test_renders_fingerprint_when_present(self):
        batch = {
            "concern_signals": [
                {
                    "type": "complexity_hotspot",
                    "file": "src/big.py",
                    "summary": "Large file",
                    "question": "Split it?",
                    "evidence": ["500 lines"],
                    "fingerprint": "abc123",
                },
            ],
        }
        result = render_mechanical_concern_signals(batch)
        assert "fingerprint: abc123" in result

    def test_omits_fingerprint_line_when_absent(self):
        batch = {
            "concern_signals": [
                {
                    "type": "design_concern",
                    "file": "src/a.py",
                    "summary": "Concern",
                    "question": "Ok?",
                    "evidence": [],
                },
            ],
        }
        result = render_mechanical_concern_signals(batch)
        assert "    fingerprint:" not in result

    def test_cap_at_30(self):
        signals = [
            {
                "type": "concern",
                "file": f"src/file_{i}.py",
                "summary": f"concern {i}",
                "question": "?",
                "evidence": [],
            }
            for i in range(35)
        ]
        batch = {"concern_signals": signals}
        result = render_mechanical_concern_signals(batch)
        assert "(+5 more" in result

    def test_verdict_instructions_in_header(self):
        batch = {
            "concern_signals": [
                {
                    "type": "x",
                    "file": "a.py",
                    "summary": "s",
                    "question": "q",
                    "evidence": [],
                },
            ],
        }
        result = render_mechanical_concern_signals(batch)
        assert 'concern_verdict: "confirmed"' in result
        assert 'concern_verdict: "dismissed"' in result


class TestRenderJudgmentFindingsSection:
    def test_empty_when_no_counts(self):
        assert render_judgment_findings_section({}) == ""
        assert render_judgment_findings_section({"judgment_finding_counts": {}}) == ""

    def test_renders_cli_commands(self):
        batch = {
            "judgment_finding_counts": {
                "smells": 12,
                "structural": 4,
                "naming": 8,
            },
        }
        result = render_judgment_findings_section(batch)
        assert "desloppify show naming --no-budget" in result
        assert "# 12 findings" in result
        assert "# 4 findings" in result
        assert "# 8 findings" in result

    def test_skips_zero_counts(self):
        batch = {
            "judgment_finding_counts": {
                "smells": 5,
                "structural": 0,
            },
        }
        result = render_judgment_findings_section(batch)
        assert "smells" in result
        assert "structural" not in result

    def test_includes_adjudication_instructions(self):
        batch = {"judgment_finding_counts": {"smells": 3}}
        result = render_judgment_findings_section(batch)
        assert "concern_verdict" in result
        assert "concern_fingerprint" in result


def test_exploded_batch_uses_public_dimension_prompt_contract() -> None:
    batches = explode_to_single_dimension(
        [
            {
                "name": "mid elegance",
                "dimensions": ["mid_level_elegance"],
                "why": "test",
                "files_to_read": ["a.py"],
            }
        ],
        dimension_prompts={"mid_level_elegance": {"description": "explicit rubric"}},
    )

    context = build_batch_context(batches[0], 0)

    assert context.dimension_prompts == {
        "mid_level_elegance": {"description": "explicit rubric"}
    }
