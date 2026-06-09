"""Tests for stroke-fit text vinyl tracing."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from text_geometry import (
    SHAPE_MODE_RECTANGLES,
    SHAPE_MODE_STROKES,
    build_typecode_payload_from_mask,
    estimate_traced_text_layers,
    normalize_text_shape_mode,
)
from text_stroke_trace import (
    STROKE_COORDINATE_MODEL,
    _mask_pixels,
    _prepare_mask,
    _text_stroke_components,
    _uncovered_pixels,
    fit_stroke_rectangles_from_mask,
)


def test_normalize_strokes_mode() -> None:
    assert normalize_text_shape_mode("strokes") == SHAPE_MODE_STROKES
    assert normalize_text_shape_mode("rotated_rectangles") == SHAPE_MODE_STROKES


def test_skeleton_trace_method_uses_stroke_payload() -> None:
    from PIL import Image
    from text_geometry import TRACE_METHOD_BARS_SKELETON

    mask = Image.new("L", (8, 24), 0)
    for y in range(4, 20):
        mask.putpixel((4, y), 255)
    payload = build_typecode_payload_from_mask(
        mask,
        (255, 255, 255, 255),
        shape_mode=SHAPE_MODE_RECTANGLES,
        trace_method=TRACE_METHOD_BARS_SKELETON,
    )
    assert payload["coordinate_model"] == STROKE_COORDINATE_MODEL
    assert len(payload["shapes"]) <= 2


def test_stroke_fit_vertical_bar_is_few_layers() -> None:
    from PIL import Image

    mask = Image.new("L", (8, 24), 0)
    for y in range(4, 20):
        mask.putpixel((4, y), 255)
    rects = fit_stroke_rectangles_from_mask(mask)
    assert len(rects) <= 2
    payload = build_typecode_payload_from_mask(mask, (255, 255, 255, 255), shape_mode=SHAPE_MODE_STROKES)
    assert payload["coordinate_model"] == STROKE_COORDINATE_MODEL
    assert len(payload["shapes"]) <= 2
    for shape in payload["shapes"]:
        assert shape["type"] == 1048677


def test_stroke_l_shape_uses_low_rotation() -> None:
    from PIL import Image

    mask = Image.new("L", (20, 24), 0)
    for y in range(4, 20):
        mask.putpixel((6, y), 255)
    for x in range(6, 14):
        mask.putpixel((x, 19), 255)
    rects = fit_stroke_rectangles_from_mask(mask)
    assert len(rects) <= 6
    for rect in rects:
        if rect.length >= rect.width * 1.5:
            assert abs(rect.rotation_deg) < 20.0 or abs(rect.rotation_deg - 90.0) < 20.0


def test_stroke_walker_fewer_than_grid_trace() -> None:
    try:
        from text_fonts import find_font_for_text
    except Exception:
        return
    font = find_font_for_text("WALKER")
    if font is None:
        return
    grid_layers = estimate_traced_text_layers(
        "WALKER",
        font_path=font,
        font_size=120,
        cell_size=1,
        shape_mode=SHAPE_MODE_RECTANGLES,
    )
    stroke_layers = estimate_traced_text_layers(
        "WALKER",
        font_path=font,
        font_size=120,
        cell_size=1,
        shape_mode=SHAPE_MODE_STROKES,
    )
    assert stroke_layers < grid_layers
    assert stroke_layers <= max(140, int(grid_layers * 0.75))


def test_stroke_walker_covers_most_pixels() -> None:
    try:
        from text_fonts import find_font_for_text
        from text_geometry import render_text_mask
    except Exception:
        return
    font = find_font_for_text("WALKER")
    if font is None:
        return
    mask = render_text_mask("WALKER", font_path=font, font_size=120)
    prepared = _prepare_mask(mask)
    pixels = _mask_pixels(prepared)
    strokes = fit_stroke_rectangles_from_mask(mask)
    uncovered = _uncovered_pixels(pixels, strokes)
    assert len(uncovered) / max(1, len(pixels)) < 0.03


def test_walker_splits_into_letters() -> None:
    try:
        from text_fonts import find_font_for_text
        from text_geometry import render_text_mask
    except Exception:
        return
    font = find_font_for_text("WALKER")
    if font is None:
        return
    mask = render_text_mask("WALKER", font_path=font, font_size=120)
    prepared = _prepare_mask(mask)
    pixels = _mask_pixels(prepared)
    groups = _text_stroke_components(pixels)
    assert len(groups) >= 5


def test_overlap_mode_fewer_layers_than_grid_for_latin() -> None:
    try:
        from text_fonts import find_font_for_text
        from text_geometry import (
            TRACE_METHOD_BARS_FULL,
            TRACE_METHOD_BARS_SKELETON,
            decompose_mask_to_rectangles,
            render_text_mask,
            trace_uses_stroke_fitting,
        )
        from text_stroke_trace import count_stroke_layers_from_mask
    except Exception:
        return
    font = find_font_for_text("Æ")
    if font is None:
        return
    mask = render_text_mask("Æ", font_path=font, font_size=120)
    grid_layers = len(decompose_mask_to_rectangles(mask, cell_size=1))
    overlap_layers = count_stroke_layers_from_mask(mask, prefer_overlap=True)
    plain_stroke_layers = count_stroke_layers_from_mask(mask, prefer_overlap=False)
    assert trace_uses_stroke_fitting(trace_method=TRACE_METHOD_BARS_SKELETON)
    assert overlap_layers < grid_layers
    # Overlap mode favors cardinal bars and skips grid fallback; a single glyph may use a few more layers.
    assert overlap_layers <= max(plain_stroke_layers + 3, 14)


def _nearest_cardinal_angle(rotation_deg: float) -> float:
    candidates = (0.0, 45.0, 90.0, 135.0)
    return min(candidates, key=lambda angle: min(abs(rotation_deg - angle), abs(rotation_deg - angle - 180)))


def test_overlap_latin_string_uses_cardinal_angles_only() -> None:
    try:
        from text_fonts import find_font_for_text
        from text_geometry import render_text_mask
        from text_stroke_trace import count_stroke_layers_from_mask
    except Exception:
        return
    sample = "ÆVEXMLIi7"
    font = find_font_for_text(sample)
    if font is None:
        return
    mask = render_text_mask(sample, font_path=font, font_size=120)
    rects = fit_stroke_rectangles_from_mask(mask, prefer_overlap=True)
    plain_stroke_layers = count_stroke_layers_from_mask(mask, prefer_overlap=False)
    assert len(rects) < 45
    assert len(rects) < plain_stroke_layers
    for rect in rects:
        nearest = _nearest_cardinal_angle(rect.rotation_deg)
        assert min(abs(rect.rotation_deg - nearest), abs(rect.rotation_deg - nearest - 180)) < 1.5


def test_overlap_mode_skips_grid_fallback_slivers() -> None:
    try:
        from text_fonts import find_font_for_text
        from text_geometry import render_text_mask
    except Exception:
        return
    font = find_font_for_text("ÆVEXMLIi7")
    if font is None:
        return
    mask = render_text_mask("ÆVEXMLIi7", font_path=font, font_size=120)
    prepared = _prepare_mask(mask)
    pixels = _mask_pixels(prepared)
    rects = fit_stroke_rectangles_from_mask(mask, prefer_overlap=True)
    tiny = [r for r in rects if r.length <= 2.0 and r.width <= 2.0]
    assert len(tiny) <= max(2, len(rects) // 8)


def test_overlap_skeleton_covers_most_pixels() -> None:
    try:
        from text_fonts import find_font_for_text
        from text_geometry import render_text_mask
    except Exception:
        return
    font = find_font_for_text("ÆVEXMLIi7")
    if font is None:
        return
    mask = render_text_mask("ÆVEXMLIi7", font_path=font, font_size=120)
    prepared = _prepare_mask(mask)
    pixels = _mask_pixels(prepared)
    strokes = fit_stroke_rectangles_from_mask(mask, prefer_overlap=True)
    uncovered = _uncovered_pixels(pixels, strokes)
    assert len(strokes) < 45
    assert len(uncovered) / max(1, len(pixels)) < 0.12


def test_stroke_bars_are_elongated_not_square_slabs() -> None:
    try:
        from text_fonts import find_font_for_text
        from text_geometry import render_text_mask
    except Exception:
        return
    font = find_font_for_text("WALKER")
    if font is None:
        return
    mask = render_text_mask("WALKER", font_path=font, font_size=120)
    rects = fit_stroke_rectangles_from_mask(mask)
    long_bars = [r for r in rects if r.length >= r.width * 1.8]
    assert len(long_bars) >= len(rects) // 3
