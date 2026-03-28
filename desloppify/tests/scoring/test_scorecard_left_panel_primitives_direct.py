"""Direct tests for scorecard left-panel primitive drawing helpers."""

from __future__ import annotations

import desloppify.app.output.scorecard_parts.left_panel_primitives as panel_mod


class _FakeDraw:
    def __init__(self) -> None:
        self.text_calls: list[dict] = []
        self.rounded_rect_calls: list[dict] = []

    def text(self, xy, text, fill=None, font=None):
        self.text_calls.append({"xy": xy, "text": text, "fill": fill, "font": font})

    def textlength(self, text, font=None):
        del font
        return float(len(text) * 10)

    def rounded_rectangle(self, box, radius=0, fill=None, outline=None, width=1):
        self.rounded_rect_calls.append(
            {
                "box": box,
                "radius": radius,
                "fill": fill,
                "outline": outline,
                "width": width,
            }
        )


def test_draw_left_panel_version_centers_text() -> None:
    draw = _FakeDraw()
    font = object()

    panel_mod.draw_left_panel_version(
        draw,
        center_x=100,
        baseline_y=20,
        version_text="v1.2.3",
        version_bbox=(0, 4, 0, 0),
        version_width=40.0,
        font_version=font,
    )

    call = draw.text_calls[0]
    assert call["xy"] == (80.0, 16)
    assert call["text"] == "v1.2.3"
    assert call["fill"] == panel_mod.DIM
    assert call["font"] is font


def test_draw_left_panel_title_centers_text() -> None:
    draw = _FakeDraw()
    font = object()

    panel_mod.draw_left_panel_title(
        draw,
        center_x=90,
        title_y=50,
        title="Project",
        title_bbox=(0, 6, 0, 0),
        title_width=70.0,
        font_title=font,
    )

    call = draw.text_calls[0]
    assert call["xy"] == (55.0, 44)
    assert call["text"] == "Project"
    assert call["fill"] == panel_mod.TEXT


def test_draw_left_panel_score_uses_score_color(monkeypatch) -> None:
    draw = _FakeDraw()
    font = object()
    monkeypatch.setattr(panel_mod, "score_color", lambda value, muted=False: f"{value}:{muted}")

    panel_mod.draw_left_panel_score(
        draw,
        center_x=80,
        score_y=60,
        score_text="88.4",
        score_bbox=(0, 7, 0, 0),
        score_value=88.4,
        font_big=font,
    )

    call = draw.text_calls[0]
    expected_width = float(len("88.4") * 10)
    assert call["xy"] == (80 - expected_width / 2, 53)
    assert call["fill"] == "88.4:False"


def test_draw_left_panel_strict_draws_label_and_value(monkeypatch) -> None:
    draw = _FakeDraw()
    monkeypatch.setattr(panel_mod, "scale", lambda x: x)
    monkeypatch.setattr(panel_mod, "score_color", lambda value, muted=False: f"strict:{value}:{muted}")

    panel_mod.draw_left_panel_strict(
        draw,
        center_x=120,
        strict_y=40,
        strict_value=72.1,
        strict_text="72.1",
        strict_label_bbox=(0, 3, 0, 0),
        strict_value_bbox=(0, 2, 0, 0),
        font_strict_label=object(),
        font_strict_val=object(),
    )

    assert len(draw.text_calls) == 2
    label_call, value_call = draw.text_calls
    assert label_call["text"] == "strict"
    assert label_call["fill"] == panel_mod.DIM
    assert value_call["text"] == "72.1"
    assert value_call["fill"] == "strict:72.1:True"


def test_draw_left_panel_project_pill_draws_box_and_text(monkeypatch) -> None:
    draw = _FakeDraw()
    monkeypatch.setattr(panel_mod, "scale", lambda x: x + 1)

    panel_mod.draw_left_panel_project_pill(
        draw,
        center_x=100,
        strict_y=30,
        strict_height=8,
        project_gap=6,
        project_pill_height=20,
        pill_pad_y=4,
        pill_pad_x=5,
        project_name="demo",
        project_bbox=(0, 2, 0, 0),
        font_project=object(),
    )

    assert len(draw.rounded_rect_calls) == 1
    rect = draw.rounded_rect_calls[0]
    assert rect["radius"] == 4  # scale(3) with monkeypatched scale
    assert rect["fill"] == panel_mod.BG
    assert rect["outline"] == panel_mod.BORDER
    assert rect["width"] == 1

    assert len(draw.text_calls) == 1
    text_call = draw.text_calls[0]
    assert text_call["text"] == "demo"
    assert text_call["fill"] == panel_mod.DIM
