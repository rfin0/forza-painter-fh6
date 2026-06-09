"""Tests for FH6 layer mask helpers and text polish masks."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fh6_layer_masks import (
    MASK_ROLE_BOUNDARY,
    MASK_ROLE_POLISH,
    TextMaskOptions,
    append_text_masks_to_payload,
    build_boundary_mask_shapes,
    is_fh6_mask_shape,
    summarize_payload_layers,
)
from text_geometry import (
    SHAPE_MODE_RECTANGLES,
    TEXT_TYPECODE_FORMAT,
    build_typecode_payload_from_mask,
    decompose_mask_to_rectangles,
)
from text_mask_polish import build_polish_mask_rectangles, rasterize_trace_rectangles


def test_boundary_masks_are_flagged_and_count_four() -> None:
    shapes = build_boundary_mask_shapes(120, 80)
    assert len(shapes) == 4
    for shape in shapes:
        assert is_fh6_mask_shape(shape)
        assert shape["mask_role"] == MASK_ROLE_BOUNDARY
        assert shape["data"][6] == 1


def test_append_boundary_masks_to_payload() -> None:
    from PIL import Image

    mask = Image.new("L", (20, 10), 0)
    for x in range(4, 8):
        for y in range(3, 7):
            mask.putpixel((x, y), 255)
    payload = build_typecode_payload_from_mask(
        mask,
        (255, 255, 255, 255),
        cell_size=2,
        shape_mode=SHAPE_MODE_RECTANGLES,
        mask_options=TextMaskOptions(include_boundary_masks=True, include_polish_masks=False),
    )
    summary = summarize_payload_layers(payload)
    assert summary["drawable_count"] >= 1
    assert summary["boundary_mask_count"] == 4
    assert summary["total_layers"] == summary["drawable_count"] + 4


def test_polish_masks_clip_overflow() -> None:
    from PIL import Image

    ideal = Image.new("L", (8, 8), 0)
    for x in range(2, 6):
        for y in range(3, 6):
            ideal.putpixel((x, y), 255)
    oversized_trace = [(0, 2, 8, 4)]
    overflow_before = build_polish_mask_rectangles(ideal, oversized_trace, polish_cell_size=1)
    assert overflow_before
    payload = {
        "format": TEXT_TYPECODE_FORMAT,
        "shapes": [
            {
                "type": 1048677,
                "data": [5.12, 5.12, 0.08, 0.08, 0.0, 0.0, 0],
                "color": [255, 255, 255, 255],
            }
        ],
    }
    updated = append_text_masks_to_payload(
        payload,
        ideal,
        trace_rectangles=oversized_trace,
        options=TextMaskOptions(
            include_boundary_masks=False,
            include_polish_masks=True,
            polish_cell_size=1,
        ),
    )
    polish_shapes = [shape for shape in updated["shapes"] if is_fh6_mask_shape(shape)]
    assert polish_shapes
    assert all(shape["mask_role"] == MASK_ROLE_POLISH for shape in polish_shapes)


def test_mask_metadata_round_trip() -> None:
    from PIL import Image

    mask = Image.new("L", (12, 12), 0)
    for y in range(4, 8):
        for x in range(4, 8):
            mask.putpixel((x, y), 255)
    rects = decompose_mask_to_rectangles(mask, cell_size=2)
    payload = {
        "format": TEXT_TYPECODE_FORMAT,
        "shapes": [{"type": 1048677, "data": [1, 1, 1, 1, 0, 0, 0], "color": [255, 255, 255, 255]}],
    }
    updated = append_text_masks_to_payload(
        payload,
        mask,
        trace_rectangles=rects,
        options=TextMaskOptions(include_boundary_masks=True, include_polish_masks=True),
    )
    summary = summarize_payload_layers(updated)
    assert summary["total_layers"] == len(updated["shapes"])
    assert summary["boundary_mask_count"] == 4
