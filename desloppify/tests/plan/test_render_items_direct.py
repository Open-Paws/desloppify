"""Direct coverage tests for plan item section rendering helpers."""

from __future__ import annotations

import desloppify.engine.planning.render_items as render_mod


def test_plan_item_sections_returns_empty_when_no_open_items(monkeypatch) -> None:
    monkeypatch.setattr(
        render_mod,
        "build_work_queue",
        lambda _state, options: {"items": []},
    )

    lines = render_mod.plan_item_sections({"a": {"status": "open"}})

    assert lines == []


def test_plan_item_sections_renders_subjective_and_regular_items(monkeypatch) -> None:
    items = [
        {
            "kind": "subjective_dimension",
            "file": ".",
            "summary": "Re-review naming quality",
            "id": "subjective::naming_quality",
            "primary_command": "desloppify review --prepare --dimensions naming_quality",
        },
        {
            "kind": "issue",
            "file": "src/a.ts",
            "summary": "Untested module",
            "id": "test_coverage::src/a.ts::x",
            "confidence": "high",
        },
        {
            "kind": "issue",
            "file": "src/a.ts",
            "summary": "Second issue",
            "id": "smells::src/a.ts::y",
            "confidence": "low",
        },
    ]
    monkeypatch.setattr(render_mod, "build_work_queue", lambda _state, options: {"items": items})

    lines = render_mod.plan_item_sections({"dummy": {}}, state={"issues": {}})
    text = "\n".join(lines)

    assert "## Open Items (3)" in text
    assert "### `src/a.ts` (2 issues)" in text
    assert "### `Codebase-wide` (1 issues)" in text
    assert "[subjective] Re-review naming quality" in text
    assert "action: `desloppify review --prepare --dimensions naming_quality`" in text
    assert "[high] Untested module" in text


def test_plan_item_sections_clamps_subjective_threshold_before_queue_build(monkeypatch) -> None:
    captured = {}

    def fake_build_work_queue(_state, options):
        captured["threshold"] = options.subjective_threshold
        return {"items": []}

    monkeypatch.setattr(render_mod, "build_work_queue", fake_build_work_queue)

    render_mod.plan_item_sections(
        {},
        state={"issues": {}, "config": {"target_strict_score": "120"}},
    )
    assert captured["threshold"] == 100.0

    render_mod.plan_item_sections(
        {},
        state={"issues": {}, "config": {"target_strict_score": "-10"}},
    )
    assert captured["threshold"] == 0.0

    render_mod.plan_item_sections(
        {},
        state={"issues": {}, "config": {"target_strict_score": "invalid"}},
    )
    assert captured["threshold"] == render_mod.DEFAULT_TARGET_STRICT_SCORE
