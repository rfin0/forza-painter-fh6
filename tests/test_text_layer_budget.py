"""Tests for text vinyl layer estimation and cell-size budgeting."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from text.layer_masks import TextMaskOptions
from text.geometry import resolve_cell_size_for_layer_budget


def test_resolve_cell_size_for_layer_budget() -> None:
    try:
        from text.fonts import find_cjk_font

        font = find_cjk_font()
    except Exception:
        return
    cell, count = resolve_cell_size_for_layer_budget(
        "MMMMMMMMMM",
        font_path=font,
        font_size=48,
        max_layers=8,
        mask_options=TextMaskOptions(include_boundary_masks=False, include_polish_masks=False),
    )
    assert cell >= 1
    assert count <= 8
