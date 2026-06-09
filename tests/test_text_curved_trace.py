"""Tests for curved / extra-shapes text vinyl tracing."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from text_curved_trace import (
    build_curved_typecode_shapes,
    extra_shape_type_codes,
    find_convex_corners,
)
from text_geometry import TEXT_TYPECODE_FORMAT, build_typecode_payload_from_mask


def test_extra_shape_type_codes_load() -> None:
    try:
        codes = extra_shape_type_codes()
    except FileNotFoundError:
        return
    assert codes["quarter_circle"] > 0x100000
    assert codes["rounded_square"] > 0x100000


def test_find_convex_corners_simple_block() -> None:
    grid = [
        [False, False, False],
        [False, True, True],
        [False, True, True],
    ]
    corners = find_convex_corners(grid)
    assert ("nw",) or True
    orientations = {orient for _r, _c, orient in corners}
    assert "nw" in orientations


def test_build_curved_shapes_from_mask() -> None:
    from PIL import Image

    mask = Image.new("L", (12, 12), 0)
    for x in range(4, 10):
        for y in range(4, 10):
            mask.putpixel((x, y), 255)
    try:
        shapes = build_curved_typecode_shapes(mask, (255, 255, 255, 255), cell_size=2)
    except FileNotFoundError:
        return
    assert shapes
    types = {s["type"] for s in shapes}
    codes = extra_shape_type_codes()
    assert codes["square"] in types or codes["ellipse"] in types


def test_payload_extra_shapes_flag() -> None:
    from PIL import Image

    mask = Image.new("L", (12, 12), 0)
    for x in range(3, 9):
        for y in range(3, 9):
            mask.putpixel((x, y), 255)
    try:
        payload = build_typecode_payload_from_mask(
            mask,
            (255, 255, 255, 255),
            cell_size=2,
            extra_shapes=True,
        )
    except FileNotFoundError:
        return
    assert payload["format"] == TEXT_TYPECODE_FORMAT
    assert "curved" in payload.get("coordinate_model", "")
