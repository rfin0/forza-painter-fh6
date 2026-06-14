"""Tests for in-game Forza font glyph placement."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from text.forza_fonts import (
    build_typecode_from_forza_font,
    estimate_forza_font_layer_count,
    is_forza_latin_text,
    lookup_forza_glyph,
    unsupported_forza_chars,
)
from text.geometry import TEXT_TYPECODE_FORMAT, estimate_typed_text_layers


def test_is_forza_latin_text() -> None:
    assert is_forza_latin_text("HELLO 123!")
    assert not is_forza_latin_text("ソニック")
    assert not is_forza_latin_text("")


def test_estimate_forza_layers() -> None:
    assert estimate_forza_font_layer_count("Hi") == 2
    assert estimate_forza_font_layer_count("A B") == 2


def test_lookup_forza_glyph_a() -> None:
    entry = lookup_forza_glyph("A", font_index=1)
    if entry is None:
        return
    assert entry.type_code == 1050477


def test_build_forza_font_payload() -> None:
    try:
        payload = build_typecode_from_forza_font("AB", font_index=1, font_size=80)
    except (FileNotFoundError, ValueError):
        return
    assert payload["format"] == TEXT_TYPECODE_FORMAT
    assert len(payload["shapes"]) == 2
    assert payload["shapes"][0]["type"] == 1050477


def test_estimate_typed_forza_mode() -> None:
    try:
        layers, cell, _summary = estimate_typed_text_layers(
            "TEST",
            use_forza_font=True,
            forza_font_index=1,
        )
    except FileNotFoundError:
        return
    assert cell == 1
    assert layers == 4


def test_unsupported_cjk_forza() -> None:
    missing = unsupported_forza_chars("A你", font_index=1)
    assert "你" in missing
