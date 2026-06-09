"""Tests for FH6 text vinyl type-code JSON generation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from text_geometry import (
    SHAPE_MODE_CIRCLES,
    SHAPE_MODE_ELLIPSES,
    SHAPE_MODE_RECTANGLES,
    SHAPE_MODE_STROKES,
    SHAPE_MODE_TRIANGLES,
    TEXT_TYPECODE_FORMAT,
    build_typecode_payload_from_mask,
    coerce_text_shape_mode_for_ui,
    estimate_layer_count,
    is_text_typecode_payload,
    text_shape_mode_choices,
)


def test_build_typecode_from_mask_circles() -> None:
    from PIL import Image

    mask = Image.new("L", (6, 6), 0)
    mask.putpixel((2, 2), 255)
    mask.putpixel((3, 2), 255)
    payload = build_typecode_payload_from_mask(
        mask,
        (200, 100, 50, 255),
        cell_size=1,
        shape_mode=SHAPE_MODE_CIRCLES,
    )
    assert payload["format"] == TEXT_TYPECODE_FORMAT
    assert len(payload["shapes"]) == 1
    assert payload["shapes"][0]["type"] == 1048687


def test_build_typecode_from_mask_rectangles_use_square() -> None:
    from PIL import Image

    mask = Image.new("L", (4, 4), 0)
    mask.putpixel((1, 1), 255)
    payload = build_typecode_payload_from_mask(
        mask,
        (255, 255, 255, 255),
        cell_size=1,
        shape_mode=SHAPE_MODE_RECTANGLES,
    )
    assert payload["shapes"][0]["type"] == 1048677


def test_build_typecode_from_mask_triangles() -> None:
    from PIL import Image

    mask = Image.new("L", (5, 3), 0)
    for x in range(5):
        mask.putpixel((x, 1), 255)
    payload = build_typecode_payload_from_mask(
        mask,
        (255, 255, 255, 255),
        cell_size=1,
        shape_mode=SHAPE_MODE_TRIANGLES,
    )
    assert payload["shapes"][0]["type"] == 1048697
    assert payload["shapes"][0]["data"][4] == 0.0


def test_estimate_layer_count_typecode_payload() -> None:
    payload = {"format": TEXT_TYPECODE_FORMAT, "shapes": [{"type": 1048677}, {"type": 1048687}]}
    assert is_text_typecode_payload(payload)
    assert estimate_layer_count(payload) == 2


def test_scaled_trace_preview_upright_orientation() -> None:
    from PIL import Image

    from pixel_art_geometry import is_scaled_trace_payload, scaled_trace_preview_shapes

    mask = Image.new("L", (8, 12), 0)
    mask.putpixel((3, 2), 255)
    mask.putpixel((3, 9), 255)
    payload = build_typecode_payload_from_mask(
        mask,
        (255, 255, 255, 255),
        cell_size=1,
        shape_mode=SHAPE_MODE_RECTANGLES,
    )
    assert is_scaled_trace_payload(payload)
    shapes = scaled_trace_preview_shapes(payload)
    assert shapes
    assert len(shapes) >= 2

    def center_y(item: dict) -> float:
        points = item["polygons"][0]
        return sum(point[1] for point in points) / len(points)

    centers = sorted(center_y(item) for item in shapes)
    assert centers[0] < centers[-1], "Top glyph should appear above bottom glyph in preview space"


def test_scaled_trace_to_memory_fields_flips_y() -> None:
    from PIL import Image

    from pixel_art_geometry import scaled_trace_to_memory_fields

    mask = Image.new("L", (8, 12), 0)
    mask.putpixel((3, 2), 255)
    mask.putpixel((3, 9), 255)
    payload = build_typecode_payload_from_mask(
        mask,
        (255, 255, 255, 255),
        cell_size=1,
        shape_mode=SHAPE_MODE_RECTANGLES,
    )
    shapes_by_cy = sorted(payload["shapes"], key=lambda shape: float(shape["data"][1]))
    top_trace = shapes_by_cy[0]["data"]
    bottom_trace = shapes_by_cy[-1]["data"]
    top = scaled_trace_to_memory_fields(top_trace)
    bottom = scaled_trace_to_memory_fields(bottom_trace)
    assert top["y"] == -float(top_trace[1])
    assert bottom["y"] == -float(bottom_trace[1])
    assert top["y"] > bottom["y"], "FH6 memory Y should increase upward for upright text"
    assert float(top_trace[1]) < float(bottom_trace[1])


def test_text_shape_mode_ui_choices_are_rectangles_ellipses_circles() -> None:
    assert text_shape_mode_choices() == ["rectangles", "ellipses", "circles"]


def test_text_trace_method_ui_choices() -> None:
    from text_geometry import (
        TRACE_METHOD_BARS_FULL,
        TRACE_METHOD_BARS_SKELETON,
        TRACE_METHOD_GRID,
        normalize_text_trace_method,
        text_trace_method_choices,
        trace_method_uses_grid,
        trace_uses_stroke_fitting,
    )

    assert text_trace_method_choices() == ["grid", "bars_full", "bars_skeleton"]
    assert normalize_text_trace_method("skeleton") == TRACE_METHOD_BARS_SKELETON
    assert normalize_text_trace_method("strokes") == TRACE_METHOD_BARS_FULL
    assert trace_method_uses_grid(TRACE_METHOD_GRID)
    assert not trace_method_uses_grid(TRACE_METHOD_BARS_FULL)
    assert trace_uses_stroke_fitting(trace_method=TRACE_METHOD_BARS_FULL)
    assert not trace_uses_stroke_fitting(trace_method=TRACE_METHOD_GRID)


def test_coerce_text_shape_mode_for_ui_maps_hidden_modes() -> None:
    assert coerce_text_shape_mode_for_ui(SHAPE_MODE_RECTANGLES) == SHAPE_MODE_RECTANGLES
    assert coerce_text_shape_mode_for_ui(SHAPE_MODE_ELLIPSES) == SHAPE_MODE_ELLIPSES
    assert coerce_text_shape_mode_for_ui(SHAPE_MODE_CIRCLES) == SHAPE_MODE_CIRCLES
    assert coerce_text_shape_mode_for_ui("squares") == SHAPE_MODE_RECTANGLES
    assert coerce_text_shape_mode_for_ui(SHAPE_MODE_TRIANGLES) == SHAPE_MODE_RECTANGLES
    assert coerce_text_shape_mode_for_ui(SHAPE_MODE_STROKES) == SHAPE_MODE_RECTANGLES
