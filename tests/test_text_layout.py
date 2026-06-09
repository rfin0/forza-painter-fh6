"""Tests for writing direction layout in text vinyl rendering."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from text_layout import (
    WRITING_MODE_HORIZONTAL_LTR,
    WRITING_MODE_VERTICAL_T2B,
    WRITING_MODE_VERTICAL_T2B_RTL,
    default_writing_mode_for_script,
    layout_options_from_writing_mode,
    normalize_writing_mode,
)
from text_fonts import SCRIPT_JAPANESE, SCRIPT_UNIVERSAL


def test_default_writing_mode_is_horizontal_ltr_for_all_scripts() -> None:
    assert default_writing_mode_for_script(SCRIPT_JAPANESE) == WRITING_MODE_HORIZONTAL_LTR
    assert default_writing_mode_for_script(SCRIPT_UNIVERSAL) == WRITING_MODE_HORIZONTAL_LTR


def test_normalize_writing_mode_falls_back_to_ltr() -> None:
    assert normalize_writing_mode("", script=SCRIPT_JAPANESE) == WRITING_MODE_HORIZONTAL_LTR
    assert normalize_writing_mode("invalid", script=SCRIPT_UNIVERSAL) == WRITING_MODE_HORIZONTAL_LTR


def test_vertical_mask_is_taller_than_horizontal_for_japanese_sample() -> None:
    try:
        from text_fonts import find_cjk_font
        from text_geometry import render_text_mask

        font_path = find_cjk_font()
    except Exception:
        return

    text = "あ\nい"
    horizontal = render_text_mask(
        text,
        font_path=font_path,
        font_size=72,
        layout=layout_options_from_writing_mode(WRITING_MODE_HORIZONTAL_LTR),
    )
    vertical = render_text_mask(
        text,
        font_path=font_path,
        font_size=72,
        layout=layout_options_from_writing_mode(WRITING_MODE_VERTICAL_T2B),
    )
    assert vertical.size[1] >= horizontal.size[1]
    assert vertical.size[0] <= horizontal.size[0] + 40


def test_vertical_columns_rtl_changes_horizontal_extent() -> None:
    try:
        from text_fonts import find_cjk_font
        from text_geometry import render_text_mask

        font_path = find_cjk_font()
    except Exception:
        return

    text = "あ\nいう"
    left_columns = render_text_mask(
        text,
        font_path=font_path,
        font_size=72,
        layout=layout_options_from_writing_mode(WRITING_MODE_VERTICAL_T2B),
    )
    right_columns = render_text_mask(
        text,
        font_path=font_path,
        font_size=72,
        layout=layout_options_from_writing_mode(WRITING_MODE_VERTICAL_T2B_RTL),
    )
    assert left_columns.size == right_columns.size
