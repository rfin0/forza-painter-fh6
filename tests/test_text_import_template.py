"""Tests for text vinyl import template shape detection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from text.geometry import (
    SHAPE_MODE_CIRCLES,
    SHAPE_MODE_RECTANGLES,
    TEXT_TYPECODE_FORMAT,
    build_typecode_payload_from_mask,
)
from text.import_template import (
    SHAPE_BYTE_CIRCLE,
    SHAPE_BYTE_SQUARE,
    attach_text_generation_metadata,
    dominant_template_shape_byte,
    required_template_shape_byte,
    template_shape_byte_for_generation,
    type_code_to_template_shape_byte,
)


def test_type_code_to_template_shape_byte_square() -> None:
    assert type_code_to_template_shape_byte(1048677) == SHAPE_BYTE_SQUARE


def test_type_code_to_template_shape_byte_circle() -> None:
    assert type_code_to_template_shape_byte(1048687) == SHAPE_BYTE_CIRCLE


def test_template_shape_byte_for_rectangles_mode() -> None:
    assert template_shape_byte_for_generation(SHAPE_MODE_RECTANGLES) == SHAPE_BYTE_SQUARE


def test_template_shape_byte_for_circles_mode() -> None:
    assert template_shape_byte_for_generation(SHAPE_MODE_CIRCLES) == SHAPE_BYTE_CIRCLE


def test_dominant_template_shape_byte_from_mask_payload() -> None:
    from PIL import Image

    mask = Image.new("L", (4, 4), 0)
    mask.putpixel((1, 1), 255)
    payload = build_typecode_payload_from_mask(
        mask,
        (255, 255, 255, 255),
        cell_size=1,
        shape_mode=SHAPE_MODE_RECTANGLES,
    )
    assert dominant_template_shape_byte(payload) == SHAPE_BYTE_SQUARE


def test_required_template_shape_byte_uses_metadata() -> None:
    payload = {
        "format": TEXT_TYPECODE_FORMAT,
        "shapes": [{"type": 1048687, "data": [0, 0, 1, 1, 0, 0, 0]}],
        "text_generation": {
            "shape_mode": SHAPE_MODE_RECTANGLES,
            "trace_method": "grid",
            "extra_shapes": False,
            "template_shape_byte": SHAPE_BYTE_SQUARE,
        },
    }
    assert required_template_shape_byte(payload) == SHAPE_BYTE_SQUARE


def test_attach_text_generation_metadata() -> None:
    payload = attach_text_generation_metadata(
        {"format": TEXT_TYPECODE_FORMAT, "shapes": []},
        shape_mode=SHAPE_MODE_CIRCLES,
        trace_method="grid",
        extra_shapes=False,
    )
    meta = payload["text_generation"]
    assert meta["shape_mode"] == SHAPE_MODE_CIRCLES
    assert meta["template_shape_byte"] == SHAPE_BYTE_CIRCLE
