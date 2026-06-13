"""Tests for trace cell size normalization."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from text.geometry import decompose_mask_to_rectangles, normalize_trace_cell_size


def test_normalize_trace_cell_size_allows_one() -> None:
    assert normalize_trace_cell_size(1) == 1
    assert normalize_trace_cell_size(0) == 1
    assert normalize_trace_cell_size(99) == 16
    assert normalize_trace_cell_size("bad", default=1) == 1


def test_decompose_mask_accepts_cell_size_one() -> None:
    from PIL import Image

    mask = Image.new("L", (4, 4), 0)
    mask.putpixel((1, 1), 255)
    rects = decompose_mask_to_rectangles(mask, cell_size=1)
    assert rects
    assert rects[0][2] == 1
    assert rects[0][3] == 1
