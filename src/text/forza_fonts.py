"""Place FH6 in-game font glyph vinyls (Forza_Font_1 … 11) from Latin text."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict, List, Tuple

from fh6_shape_catalog import ShapeCatalogEntry, load_catalog
from pixel_art_geometry import POSITION_SCALE, SIZE_SCALE
from text.geometry import TEXT_TYPECODE_FORMAT, TEXT_TYPECODE_SCORE, _load_pillow

ColorRGBA = Tuple[int, int, int, int]

FORZA_FONT_COUNT = 11
FORZA_GLYPH_SCALE = 2.55
FORZA_COORDINATE_MODEL = "forza_painter_forza_font_v1"

# Characters the in-game vinyl text tool supports (alphabet-focused).
_FORZA_LATIN_RE = re.compile(r"^[\x20-\x7E]+$")


def forza_font_family(index: int) -> str:
    if not 1 <= int(index) <= FORZA_FONT_COUNT:
        raise ValueError(f"Forza font index must be 1–{FORZA_FONT_COUNT}")
    return f"Forza_Font_{int(index)}"


def forza_font_label(index: int) -> str:
    return f"Forza Font {int(index)}"


def list_forza_font_labels() -> List[str]:
    return [forza_font_label(i) for i in range(1, FORZA_FONT_COUNT + 1)]


def parse_forza_font_label(label: str) -> int:
    text = str(label).strip()
    match = re.search(r"(\d+)\s*$", text)
    if match:
        return int(match.group(1))
    raise ValueError(f"Unknown Forza font label: {label!r}")


def is_forza_latin_text(text: str) -> bool:
    if not text or not text.strip():
        return False
    return _FORZA_LATIN_RE.match(text) is not None


def unsupported_forza_chars(text: str, *, font_index: int) -> List[str]:
    missing: List[str] = []
    for char in text:
        if char in (" ", "\t", "\n", "\r"):
            continue
        if lookup_forza_glyph(char, font_index=font_index) is None:
            missing.append(char)
    return missing


@lru_cache(maxsize=1)
def _glyph_lookup_index() -> Dict[Tuple[str, str, str], ShapeCatalogEntry]:
    try:
        catalog = load_catalog()
    except FileNotFoundError:
        return {}
    index: Dict[Tuple[str, str, str], ShapeCatalogEntry] = {}
    for entry in catalog.entries_by_code.values():
        if entry.section != "font_glyph":
            continue
        if not entry.family or not entry.glyph:
            continue
        key = (entry.family, (entry.glyph_block or "").strip(), entry.glyph.strip())
        index.setdefault(key, entry)
    return index


def _glyph_keys_for_char(char: str) -> List[Tuple[str, str]]:
    if len(char) != 1:
        return []
    if "A" <= char <= "Z":
        return [("upper", char)]
    if "a" <= char <= "z":
        return [("lower", char)]
    if "0" <= char <= "9":
        return [("number", char)]
    return [("upper_symbol", char), ("lower_symbol", char)]


def lookup_forza_glyph(char: str, *, font_index: int) -> ShapeCatalogEntry | None:
    if len(char) != 1:
        return None
    family = forza_font_family(font_index)
    index = _glyph_lookup_index()
    if not index:
        return None
    for block, glyph in _glyph_keys_for_char(char):
        entry = index.get((family, block, glyph))
        if entry is not None:
            return entry
    return None


def _measure_glyph_layout(
    text: str,
    *,
    font_size: int,
) -> Tuple[List[Tuple[str, int, int, int, int]], int, int]:
    """Return (char, x0, y0, width, height) boxes using system metrics for spacing."""
    from text.fonts import _LATIN_FALLBACKS

    Image, ImageDraw, ImageFont = _load_pillow()
    font = None
    for candidate in _LATIN_FALLBACKS:
        if candidate.is_file():
            try:
                font = ImageFont.truetype(str(candidate), font_size)
                break
            except OSError:
                continue
    if font is None:
        font = ImageFont.load_default()

    padding = max(8, font_size // 4)
    probe = Image.new("L", (4, 4), 0)
    draw = ImageDraw.Draw(probe)
    x_cursor = padding
    y_cursor = padding
    row_height = font_size
    boxes: List[Tuple[str, int, int, int, int]] = []

    for char in text:
        if char == "\n":
            x_cursor = padding
            y_cursor += int(row_height * 1.15)
            continue
        if char in (" ", "\t"):
            space_w = int(font_size * (0.35 if char == " " else 0.55))
            x_cursor += space_w
            continue
        bbox = draw.textbbox((0, 0), char, font=font)
        width = max(1, bbox[2] - bbox[0])
        height = max(1, bbox[3] - bbox[1])
        x0 = x_cursor - bbox[0]
        y0 = y_cursor - bbox[1]
        boxes.append((char, x0, y0, width, height))
        x_cursor += width + max(1, font_size // 16)
        row_height = max(row_height, height)

    canvas_w = max(padding * 2, x_cursor + padding)
    canvas_h = max(padding * 2, y_cursor + row_height + padding)
    return boxes, canvas_w, canvas_h


def _glyph_shape(
    entry: ShapeCatalogEntry,
    x0: int,
    y0: int,
    width: int,
    height: int,
    color: ColorRGBA,
    *,
    font_size: int,
) -> dict:
    side = max(width, height, 1)
    target = max(font_size, side)
    cx = (float(x0) + float(width) / 2.0) * POSITION_SCALE
    cy = (float(y0) + float(height) / 2.0) * POSITION_SCALE
    scale = float(target) * SIZE_SCALE * FORZA_GLYPH_SCALE
    return {
        "type": int(entry.type_code),
        "data": [cx, cy, scale, scale, 0.0, 0.0, 0],
        "color": [int(color[0]), int(color[1]), int(color[2]), int(color[3])],
        "score": TEXT_TYPECODE_SCORE,
    }


def build_typecode_from_forza_font(
    text: str,
    *,
    font_index: int = 1,
    color: ColorRGBA = (255, 255, 255, 255),
    font_size: int = 120,
) -> dict:
    if not text or not text.strip():
        raise ValueError("Text is empty")
    if not is_forza_latin_text(text):
        raise ValueError(
            "In-game Forza fonts only support Latin letters, digits, and basic symbols "
            "(same as FH6 Enter Text). Use trace mode for other scripts."
        )
    missing = unsupported_forza_chars(text, font_index=font_index)
    if missing:
        shown = "".join(dict.fromkeys(missing))[:24]
        raise ValueError(
            f"Forza Font {font_index} has no glyph for {len(missing)} character(s): {shown!r}"
        )

    boxes, _, _ = _measure_glyph_layout(text, font_size=font_size)
    shapes: List[dict] = []
    for char, x0, y0, width, height in boxes:
        entry = lookup_forza_glyph(char, font_index=font_index)
        if entry is None:
            continue
        shapes.append(
            _glyph_shape(entry, x0, y0, width, height, color, font_size=font_size)
        )
    if not shapes:
        raise ValueError("No placeable Forza font glyphs in text")

    return {
        "format": TEXT_TYPECODE_FORMAT,
        "created_by": "forza-painter-fh6",
        "coordinate_model": FORZA_COORDINATE_MODEL,
        "forza_font": forza_font_family(font_index),
        "shapes": shapes,
    }


def estimate_forza_font_layer_count(text: str) -> int:
    return sum(
        1
        for char in text
        if char not in (" ", "\t", "\n", "\r")
    )
