"""
Build Forza-compatible geometry JSON from Unicode text or raster text images.

Traces glyph masks into importable primitives (rectangles, squares, ellipses, etc.)
so CJK scripts such as katakana can be used when in-game text does not support them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Sequence, Tuple

from geometry_json import RECTANGLE, ROTATED_ELLIPSE, normalize_geometry_payload
from security_policy import MAX_GEOMETRY_SHAPES, MAX_IMAGE_DIMENSION
from text.mandarin_chars import is_cjk_char, is_hangul_char
from text.fonts import find_cjk_font, find_font_for_text, format_missing_chars, validate_text_coverage

ColorRGBA = Tuple[int, int, int, int]
Rect = Tuple[int, int, int, int]  # x0, y0, width, height in pixels

SHAPE_MODE_RECTANGLES = "rectangles"
SHAPE_MODE_SQUARES = "squares"
SHAPE_MODE_ELLIPSES = "ellipses"
SHAPE_MODE_CIRCLES = "circles"
SHAPE_MODE_TRIANGLES = "triangles"
SHAPE_MODE_MIXED = "mixed"
SHAPE_MODE_STROKES = "strokes"

TRACE_METHOD_GRID = "grid"
TRACE_METHOD_BARS_FULL = "bars_full"
TRACE_METHOD_BARS_SKELETON = "bars_skeleton"

TEXT_SHAPE_MODES = (
    SHAPE_MODE_RECTANGLES,
    SHAPE_MODE_SQUARES,
    SHAPE_MODE_ELLIPSES,
    SHAPE_MODE_CIRCLES,
    SHAPE_MODE_TRIANGLES,
    SHAPE_MODE_MIXED,
    SHAPE_MODE_STROKES,
)

# Modes exposed in the Text tab and CLI (--shape-mode).
TEXT_SHAPE_MODE_UI_CHOICES = (
    SHAPE_MODE_RECTANGLES,
    SHAPE_MODE_ELLIPSES,
    SHAPE_MODE_CIRCLES,
)

TEXT_TRACE_METHOD_UI_CHOICES = (
    TRACE_METHOD_GRID,
    TRACE_METHOD_BARS_FULL,
    TRACE_METHOD_BARS_SKELETON,
)

_TRACE_METHOD_ALIASES = {
    "grid": TRACE_METHOD_GRID,
    "bars": TRACE_METHOD_BARS_FULL,
    "bars_full": TRACE_METHOD_BARS_FULL,
    "full": TRACE_METHOD_BARS_FULL,
    "strokes": TRACE_METHOD_BARS_FULL,
    "stroke": TRACE_METHOD_BARS_FULL,
    "rotated_bars": TRACE_METHOD_BARS_FULL,
    "rotated_bars_full": TRACE_METHOD_BARS_FULL,
    "bars_skeleton": TRACE_METHOD_BARS_SKELETON,
    "skeleton": TRACE_METHOD_BARS_SKELETON,
    "overlap": TRACE_METHOD_BARS_SKELETON,
    "overlapping": TRACE_METHOD_BARS_SKELETON,
    "rotated_bars_skeleton": TRACE_METHOD_BARS_SKELETON,
}

_HIDDEN_SHAPE_MODE_UI_FALLBACK = {
    SHAPE_MODE_SQUARES: SHAPE_MODE_RECTANGLES,
    SHAPE_MODE_TRIANGLES: SHAPE_MODE_RECTANGLES,
    SHAPE_MODE_MIXED: SHAPE_MODE_RECTANGLES,
    SHAPE_MODE_STROKES: SHAPE_MODE_RECTANGLES,
}

_SHAPE_MODE_ALIASES = {
    "rect": SHAPE_MODE_RECTANGLES,
    "rectangle": SHAPE_MODE_RECTANGLES,
    "rectangles": SHAPE_MODE_RECTANGLES,
    "square": SHAPE_MODE_SQUARES,
    "squares": SHAPE_MODE_SQUARES,
    "ellipse": SHAPE_MODE_ELLIPSES,
    "ellipses": SHAPE_MODE_ELLIPSES,
    "ellipsis": SHAPE_MODE_ELLIPSES,
    "circle": SHAPE_MODE_CIRCLES,
    "circles": SHAPE_MODE_CIRCLES,
    "triangle": SHAPE_MODE_TRIANGLES,
    "triangles": SHAPE_MODE_TRIANGLES,
    "diamond": SHAPE_MODE_TRIANGLES,
    "diamonds": SHAPE_MODE_TRIANGLES,
    "mixed": SHAPE_MODE_MIXED,
    "auto": SHAPE_MODE_MIXED,
    "stroke": SHAPE_MODE_STROKES,
    "strokes": SHAPE_MODE_STROKES,
    "rotated_rectangle": SHAPE_MODE_STROKES,
    "rotated_rectangles": SHAPE_MODE_STROKES,
}


def normalize_text_shape_mode(value: str | None) -> str:
    if not value:
        return SHAPE_MODE_RECTANGLES
    key = str(value).strip().lower().replace("-", "_")
    return _SHAPE_MODE_ALIASES.get(key, SHAPE_MODE_RECTANGLES)


def coerce_text_shape_mode_for_ui(value: str | None) -> str:
    """Map legacy/hidden trace modes to a supported UI choice."""
    mode = normalize_text_shape_mode(value)
    if mode in TEXT_SHAPE_MODE_UI_CHOICES:
        return mode
    return _HIDDEN_SHAPE_MODE_UI_FALLBACK.get(mode, SHAPE_MODE_RECTANGLES)


def text_shape_mode_choices() -> List[str]:
    return list(TEXT_SHAPE_MODE_UI_CHOICES)


def normalize_text_trace_method(value: str | None) -> str:
    if not value:
        return TRACE_METHOD_GRID
    key = str(value).strip().lower().replace("-", "_")
    if key in _TRACE_METHOD_ALIASES:
        return _TRACE_METHOD_ALIASES[key]
    if key in TEXT_TRACE_METHOD_UI_CHOICES:
        return key
    return TRACE_METHOD_GRID


def text_trace_method_choices() -> List[str]:
    return list(TEXT_TRACE_METHOD_UI_CHOICES)


def resolve_text_trace_pipeline(
    *,
    trace_method: str | None = None,
    shape_mode: str = SHAPE_MODE_RECTANGLES,
    allow_overlapping_shapes: bool = False,
    extra_shapes: bool = False,
) -> tuple[str, bool, bool]:
    """Return (trace_method, uses_stroke_fitting, prefer_skeleton)."""
    if extra_shapes:
        return TRACE_METHOD_GRID, False, False
    if trace_method is not None:
        method = normalize_text_trace_method(trace_method)
    elif allow_overlapping_shapes:
        method = TRACE_METHOD_BARS_SKELETON
    elif normalize_text_shape_mode(shape_mode) == SHAPE_MODE_STROKES:
        method = TRACE_METHOD_BARS_FULL
    else:
        method = TRACE_METHOD_GRID
    uses_strokes = method in (TRACE_METHOD_BARS_FULL, TRACE_METHOD_BARS_SKELETON)
    prefer_skeleton = method == TRACE_METHOD_BARS_SKELETON
    return method, uses_strokes, prefer_skeleton


def trace_uses_stroke_fitting(
    shape_mode: str = SHAPE_MODE_RECTANGLES,
    *,
    trace_method: str | None = None,
    allow_overlapping_shapes: bool = False,
    extra_shapes: bool = False,
) -> bool:
    """True when generation should use rotated-bar stroke fitting instead of grid fill."""
    _method, uses_strokes, _prefer_skeleton = resolve_text_trace_pipeline(
        trace_method=trace_method,
        shape_mode=shape_mode,
        allow_overlapping_shapes=allow_overlapping_shapes,
        extra_shapes=extra_shapes,
    )
    return uses_strokes


def trace_method_uses_grid(trace_method: str | None) -> bool:
    return normalize_text_trace_method(trace_method) == TRACE_METHOD_GRID


def template_hint_for_shape_mode(
    shape_mode: str,
    *,
    extra_shapes: bool = False,
    trace_method: str | None = None,
) -> str:
    del shape_mode, extra_shapes, trace_method
    return (
        "FH6 text vinyl JSON may use squares, rectangles, circles, or curves. "
        "Use a fresh ungrouped white circle (sphere) template (save, reopen, ungroup) with enough layers "
        "to match your JSON. Square or rectangle text may look circular in-game until you save and reload "
        "the vinyl group."
    )


TEXT_TYPECODE_FORMAT = "fh6_text_typecode_v1"
TEXT_TYPECODE_COORDINATE_MODEL = "forza_painter_text_trace_v1"
TEXT_TYPECODE_CURVED_COORDINATE_MODEL = "forza_painter_text_curved_v1"
TEXT_TYPECODE_SCORE = 0.0


def _typecode_rotation_for_rect(shape_mode: str, width: int, height: int) -> float:
    mode = normalize_text_shape_mode(shape_mode)
    if mode == SHAPE_MODE_TRIANGLES:
        if width > height * 1.35:
            return 0.0
        if height > width * 1.35:
            return 90.0
        return 0.0
    if mode == SHAPE_MODE_MIXED:
        aspect = max(width, height) / max(1, min(width, height))
        if aspect >= 2.2:
            return 0.0
        return 45.0 if width != height else 0.0
    return 0.0


def _fh6_type_code_for_shape_mode(shape_mode: str, width: int, height: int) -> int:
    from fh6_shape_catalog import get_primitive_type_code, get_square_type_code

    mode = normalize_text_shape_mode(shape_mode)
    if mode in (SHAPE_MODE_RECTANGLES, SHAPE_MODE_SQUARES):
        return get_square_type_code()
    if mode == SHAPE_MODE_CIRCLES:
        return get_primitive_type_code("Circle") or 1048687
    if mode == SHAPE_MODE_ELLIPSES:
        return get_primitive_type_code("Ellipse") or 1048715
    if mode in (SHAPE_MODE_TRIANGLES, SHAPE_MODE_MIXED):
        return get_primitive_type_code("Triangle") or 1048697
    return get_square_type_code()


def _rect_to_typecode_shape(
    x0: int,
    y0: int,
    width: int,
    height: int,
    color: ColorRGBA,
    shape_mode: str,
) -> dict:
    from pixel_art_geometry import POSITION_SCALE, SIZE_SCALE

    if width <= 0 or height <= 0:
        raise ValueError("invalid trace rectangle")
    cx = (float(x0) + float(width) / 2.0) * POSITION_SCALE
    cy = (float(y0) + float(height) / 2.0) * POSITION_SCALE
    mode = normalize_text_shape_mode(shape_mode)
    if mode == SHAPE_MODE_CIRCLES:
        diameter = max(1, min(width, height))
        sx = float(diameter) * SIZE_SCALE
        sy = sx
    elif mode == SHAPE_MODE_TRIANGLES:
        if width > height * 1.35:
            sx = float(width) * SIZE_SCALE
            sy = float(max(1, height // 2)) * SIZE_SCALE
        elif height > width * 1.35:
            sx = float(max(1, width // 2)) * SIZE_SCALE
            sy = float(height) * SIZE_SCALE
        else:
            side = float(max(1, min(width, height))) * SIZE_SCALE
            sx = side
            sy = side
    else:
        sx = float(width) * SIZE_SCALE
        sy = float(height) * SIZE_SCALE
    rotation = _typecode_rotation_for_rect(shape_mode, width, height)
    return {
        "type": _fh6_type_code_for_shape_mode(shape_mode, width, height),
        "data": [cx, cy, sx, sy, rotation, 0.0, 0],
        "color": [int(color[0]), int(color[1]), int(color[2]), int(color[3])],
        "score": TEXT_TYPECODE_SCORE,
    }


def rectangles_to_typecode_shapes(
    rectangles: Sequence[Rect],
    color: ColorRGBA,
    shape_mode: str = SHAPE_MODE_RECTANGLES,
) -> List[dict]:
    return [
        _rect_to_typecode_shape(x0, y0, width, height, color, shape_mode)
        for x0, y0, width, height in rectangles
    ]


def build_typecode_payload_from_mask(
    mask,
    color: ColorRGBA,
    cell_size: int = 1,
    shape_mode: str = SHAPE_MODE_RECTANGLES,
    *,
    extra_shapes: bool = False,
    trace_method: str | None = None,
    allow_overlapping_shapes: bool = False,
    mask_options=None,
    capture_trace_rectangles: bool = False,
    vertical: bool = False,
) -> dict:
    trace_rectangles: List[Rect] | None = None
    resolved_method, uses_strokes, prefer_skeleton = resolve_text_trace_pipeline(
        trace_method=trace_method,
        shape_mode=shape_mode,
        allow_overlapping_shapes=allow_overlapping_shapes,
        extra_shapes=extra_shapes,
    )
    if extra_shapes:
        from text.curved_trace import build_curved_typecode_shapes

        shapes = build_curved_typecode_shapes(mask, color, cell_size=cell_size)
        coordinate_model = TEXT_TYPECODE_CURVED_COORDINATE_MODEL
    elif uses_strokes:
        from text.stroke_trace import STROKE_COORDINATE_MODEL, build_stroke_typecode_shapes

        shapes = build_stroke_typecode_shapes(
            mask,
            color,
            vertical=vertical,
            prefer_overlap=prefer_skeleton,
        )
        coordinate_model = STROKE_COORDINATE_MODEL
    else:
        rectangles = decompose_mask_to_rectangles(mask, cell_size=cell_size)
        if not rectangles:
            raise ValueError("No text pixels detected in image mask")
        if capture_trace_rectangles or (
            mask_options is not None
            and getattr(mask_options, "include_polish_masks", False)
        ):
            trace_rectangles = rectangles
        shapes = rectangles_to_typecode_shapes(rectangles, color, shape_mode=shape_mode)
        coordinate_model = TEXT_TYPECODE_COORDINATE_MODEL
    if not shapes:
        raise ValueError("No text pixels detected in image mask")
    if len(shapes) > MAX_GEOMETRY_SHAPES:
        raise ValueError(
            f"Text trace produced {len(shapes)} shapes (limit {MAX_GEOMETRY_SHAPES}). "
            "Increase cell size, choose a simpler shape mode, or reduce font size / resolution."
        )
    payload = {
        "format": TEXT_TYPECODE_FORMAT,
        "created_by": "forza-painter-fh6",
        "coordinate_model": coordinate_model,
        "shapes": shapes,
    }
    if mask_options is not None:
        from text.layer_masks import TextMaskOptions, append_text_masks_to_payload, polish_supported_for_shape_mode

        if mask_options.include_polish_masks and not polish_supported_for_shape_mode(
            shape_mode,
            extra_shapes=extra_shapes,
            trace_method=resolved_method,
            allow_overlapping_shapes=prefer_skeleton,
        ):
            mask_options = TextMaskOptions(
                include_boundary_masks=mask_options.include_boundary_masks,
                include_polish_masks=False,
                polish_cell_size=mask_options.polish_cell_size,
                polish_margin=mask_options.polish_margin,
                max_drawable_layers=mask_options.max_drawable_layers,
            )
        payload = append_text_masks_to_payload(
            payload,
            mask,
            trace_rectangles=trace_rectangles,
            options=mask_options,
        )
    from text.import_template import attach_text_generation_metadata

    return attach_text_generation_metadata(
        payload,
        shape_mode=shape_mode,
        trace_method=resolved_method,
        extra_shapes=extra_shapes,
    )


def build_typecode_from_text(
    text: str,
    color: ColorRGBA = (255, 255, 255, 255),
    font_path: Path | None = None,
    font_size: int = 120,
    cell_size: int = 1,
    bold: bool = False,
    strict_glyph_check: bool = True,
    shape_mode: str = SHAPE_MODE_RECTANGLES,
    *,
    extra_shapes: bool = False,
    trace_method: str | None = None,
    allow_overlapping_shapes: bool = False,
    mask_options=None,
    layout=None,
    writing_mode: str | None = None,
) -> dict:
    resolved_font = Path(font_path) if font_path else find_font_for_text(text)
    if strict_glyph_check:
        ok, missing = validate_text_coverage(text, resolved_font)
        if not ok:
            hint = (
                " For Korean, choose a [KR] font such as Malgun Gothic."
                if any(is_hangul_char(char) for char in text)
                else " Choose a text font that supports every character in your input."
            )
            raise ValueError(
                f"Font {resolved_font.name} is missing {len(missing)} character(s): "
                f"{format_missing_chars(missing)}. Choose another font or install a fuller CJK face.{hint}"
            )
    from text.layout import layout_options_from_writing_mode

    layout_opts = layout if layout is not None else layout_options_from_writing_mode(writing_mode)
    mask = render_text_mask(
        text,
        font_path=resolved_font,
        font_size=font_size,
        bold=bold,
        layout=layout_opts,
    )
    return build_typecode_payload_from_mask(
        mask,
        color=color,
        cell_size=cell_size,
        shape_mode=shape_mode,
        extra_shapes=extra_shapes,
        trace_method=trace_method,
        allow_overlapping_shapes=allow_overlapping_shapes,
        mask_options=mask_options,
        vertical=layout_opts.is_vertical,
    )


def build_typecode_from_text_image(
    image_path: Path,
    color: ColorRGBA | None = None,
    cell_size: int = 1,
    invert: bool = False,
    threshold: int = 128,
    sample_text_color: bool = True,
    shape_mode: str = SHAPE_MODE_RECTANGLES,
    *,
    extra_shapes: bool = False,
    trace_method: str | None = None,
    allow_overlapping_shapes: bool = False,
    mask_options=None,
) -> dict:
    mask = load_text_image_mask(image_path, invert=invert, threshold=threshold)
    if color is None and sample_text_color:
        color = _sample_ink_color(image_path, mask, threshold, invert)
    if color is None:
        color = (255, 255, 255, 255)
    return build_typecode_payload_from_mask(
        mask,
        color=color,
        cell_size=cell_size,
        shape_mode=shape_mode,
        extra_shapes=extra_shapes,
        trace_method=trace_method,
        allow_overlapping_shapes=allow_overlapping_shapes,
        mask_options=mask_options,
    )


def is_text_typecode_payload(payload: dict) -> bool:
    return "typecode" in str(payload.get("format", "")).lower()


def write_text_design_json(path: Path, payload: dict) -> Path:
    if is_text_typecode_payload(payload):
        from pixel_art_geometry import write_typecode_json

        return write_typecode_json(path, payload)
    return write_geometry_json(path, payload)


def _load_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required for text vinyl generation. Install requirements.txt.") from exc
    return Image, ImageDraw, ImageFont


def _load_text_font(font_path: Path, font_size: int, *, bold: bool = False):
    _, _, ImageFont = _load_pillow()
    font_path = Path(font_path)
    if bold and font_path.suffix.lower() == ".ttc":
        font = None
        for index in (1, 0):
            try:
                font = ImageFont.truetype(str(font_path), font_size, index=index)
                break
            except OSError:
                continue
        if font is None:
            font = ImageFont.truetype(str(font_path), font_size)
        return font
    try:
        return ImageFont.truetype(str(font_path), font_size)
    except OSError as exc:
        raise FileNotFoundError(f"Cannot load font: {font_path}") from exc


def _glyph_bbox(draw, char: str, font) -> tuple[int, int, int, int]:
    return draw.textbbox((0, 0), char, font=font)


def _render_horizontal_ltr_mask(text: str, font, *, padding: int) -> object:
    Image, ImageDraw, _ = _load_pillow()
    probe = Image.new("L", (4, 4), 0)
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = max(4, bbox[2] - bbox[0] + padding * 2)
    height = max(4, bbox[3] - bbox[1] + padding * 2)
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise ValueError(f"Rendered text exceeds {MAX_IMAGE_DIMENSION}px; reduce font size")
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    origin = (padding - bbox[0], padding - bbox[1])
    draw.text(origin, text, fill=255, font=font)
    return image


def _render_vertical_mask(
    text: str,
    font,
    *,
    padding: int,
    columns_rtl: bool,
    line_spacing: float,
    column_spacing: float,
) -> object:
    Image, ImageDraw, _ = _load_pillow()
    columns = text.split("\n")
    if not columns:
        columns = [""]

    probe = Image.new("L", (4, 4), 0)
    probe_draw = ImageDraw.Draw(probe)

    measured: list[tuple[int, int, list[tuple[int, int, str]]]] = []
    for column_text in columns:
        glyphs: list[tuple[int, int, str]] = []
        col_width = 0
        col_height = 0
        for char in column_text:
            bbox = _glyph_bbox(probe_draw, char, font)
            glyph_w = max(1, bbox[2] - bbox[0])
            glyph_h = max(1, bbox[3] - bbox[1])
            glyphs.append((glyph_w, glyph_h, char))
            col_width = max(col_width, glyph_w)
            col_height += max(1, int(round(glyph_h * line_spacing)))
        if not glyphs and column_text == "":
            col_width = max(1, font.size // 2 if hasattr(font, "size") else 8)
            col_height = max(1, font.size if hasattr(font, "size") else 16)
        measured.append((col_width, col_height, glyphs))

    total_width = padding * 2
    total_height = padding * 2
    if measured:
        total_height += max(height for _w, height, _glyphs in measured)
        gaps = max(0, len(measured) - 1)
        total_width += sum(width for width, _h, _g in measured) + int(
            round(gaps * column_spacing * (font.size if hasattr(font, "size") else 16))
        )

    if total_width > MAX_IMAGE_DIMENSION or total_height > MAX_IMAGE_DIMENSION:
        raise ValueError(f"Rendered text exceeds {MAX_IMAGE_DIMENSION}px; reduce font size")

    image = Image.new("L", (max(4, total_width), max(4, total_height)), 0)
    draw = ImageDraw.Draw(image)
    col_gap = int(round(column_spacing * (font.size if hasattr(font, "size") else 16) * 0.35))
    ordered = list(reversed(measured)) if columns_rtl else measured
    x_cursor = padding
    if columns_rtl:
        x_cursor = max(padding, total_width - padding - sum(w for w, _h, _g in ordered))

    for col_width, _col_height, glyphs in ordered:
        y_cursor = padding
        for glyph_w, glyph_h, char in glyphs:
            bbox = _glyph_bbox(draw, char, font)
            x_offset = x_cursor + max(0, (col_width - (bbox[2] - bbox[0])) // 2) - bbox[0]
            y_offset = y_cursor - bbox[1]
            draw.text((x_offset, y_offset), char, fill=255, font=font)
            y_cursor += max(1, int(round(glyph_h * line_spacing)))
        x_cursor += col_width + col_gap

    return image


def render_text_mask(
    text: str,
    font_path: Path | None = None,
    font_size: int = 120,
    padding: int = 24,
    bold: bool = False,
    layout=None,
):
    if not text or not text.strip():
        raise ValueError("Text is empty")
    from text.layout import (
        WRITING_MODE_HORIZONTAL_RTL,
        TextLayoutOptions,
        layout_options_from_writing_mode,
    )

    Image, _, _ = _load_pillow()
    font_path = Path(font_path) if font_path else find_cjk_font()
    font = _load_text_font(font_path, font_size, bold=bold)
    options = layout if isinstance(layout, TextLayoutOptions) else layout_options_from_writing_mode(layout)

    if options.writing_mode == WRITING_MODE_HORIZONTAL_RTL:
        return _render_horizontal_ltr_mask(text, font, padding=padding)

    if options.is_vertical:
        return _render_vertical_mask(
            text,
            font,
            padding=padding,
            columns_rtl=options.columns_rtl,
            line_spacing=options.line_spacing,
            column_spacing=options.column_spacing,
        )

    return _render_horizontal_ltr_mask(text, font, padding=padding)


def load_text_image_mask(path: Path, invert: bool = False, threshold: int = 128):
    Image, _, _ = _load_pillow()
    path = Path(path)
    image = Image.open(path).convert("L")
    if invert:
        image = Image.eval(image, lambda value: 255 - value)
    width, height = image.size
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise ValueError(f"Image exceeds {MAX_IMAGE_DIMENSION}px; crop or downscale first")
    pixels = list(image.getdata())
    binary = Image.new("L", image.size, 0)
    binary.putdata([255 if value >= threshold else 0 for value in pixels])
    return binary


def normalize_trace_cell_size(cell_size: int | str | None, *, default: int = 1) -> int:
    """Clamp trace cell size to the supported 1–16 pixel grid range."""
    try:
        value = int(cell_size)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        value = default
    return max(1, min(16, value))


def decompose_mask_to_rectangles(mask, cell_size: int = 1) -> List[Rect]:
    """Merge grid cells into larger axis-aligned rectangles."""
    cell_size = normalize_trace_cell_size(cell_size)
    width, height = mask.size
    pixels = mask.load()
    threshold = 128
    cols = (width + cell_size - 1) // cell_size
    rows = (height + cell_size - 1) // cell_size
    grid = [[False] * cols for _ in range(rows)]

    for row in range(rows):
        y0 = row * cell_size
        y1 = min(height, y0 + cell_size)
        for col in range(cols):
            x0 = col * cell_size
            x1 = min(width, x0 + cell_size)
            filled = 0
            total = 0
            for y in range(y0, y1):
                for x in range(x0, x1):
                    total += 1
                    if pixels[x, y] >= threshold:
                        filled += 1
            grid[row][col] = filled > total * 0.45

    visited = [[False] * cols for _ in range(rows)]
    rectangles: List[Rect] = []
    for row in range(rows):
        col = 0
        while col < cols:
            if not grid[row][col] or visited[row][col]:
                col += 1
                continue
            span = 1
            while col + span < cols and grid[row][col + span] and not visited[row][col + span]:
                span += 1
            height_span = 1
            can_grow = True
            while row + height_span < rows and can_grow:
                for dx in range(span):
                    if not grid[row + height_span][col + dx] or visited[row + height_span][col + dx]:
                        can_grow = False
                        break
                if can_grow:
                    height_span += 1
            for dy in range(height_span):
                for dx in range(span):
                    visited[row + dy][col + dx] = True
            x0 = col * cell_size
            y0 = row * cell_size
            rectangles.append(
                (
                    x0,
                    y0,
                    min(width - x0, span * cell_size),
                    min(height - y0, height_span * cell_size),
                )
            )
            col += span
    return rectangles


def _rect_to_primitive_shapes(
    x0: int,
    y0: int,
    width: int,
    height: int,
    color: ColorRGBA,
    shape_mode: str,
) -> List[dict]:
    if width <= 0 or height <= 0:
        return []
    mode = normalize_text_shape_mode(shape_mode)
    cx = int(x0 + width / 2)
    cy = int(y0 + height / 2)
    w = int(width)
    h = int(height)

    if mode == SHAPE_MODE_SQUARES:
        side = max(w, h)
        return [
            {
                "type": RECTANGLE,
                "data": [cx, cy, side, side],
                "color": list(color),
                "score": 0,
            }
        ]

    if mode == SHAPE_MODE_ELLIPSES:
        return [
            {
                "type": ROTATED_ELLIPSE,
                "data": [cx, cy, max(1, w), max(1, h), 0],
                "color": list(color),
                "score": 0,
            }
        ]

    if mode == SHAPE_MODE_CIRCLES:
        diameter = max(1, min(w, h))
        return [
            {
                "type": ROTATED_ELLIPSE,
                "data": [cx, cy, diameter, diameter, 0],
                "color": list(color),
                "score": 0,
            }
        ]

    if mode == SHAPE_MODE_TRIANGLES:
        # Legacy geometry JSON: diamond ellipses approximate sharp strokes.
        diameter = max(1, min(w, h))
        if w > h * 1.35:
            rot = 0
            axes = [max(1, w), max(1, h // 2 or 1)]
        elif h > w * 1.35:
            rot = 90
            axes = [max(1, w // 2 or 1), max(1, h)]
        else:
            rot = 45
            axes = [diameter, diameter]
        return [
            {
                "type": ROTATED_ELLIPSE,
                "data": [cx, cy, axes[0], axes[1], rot],
                "color": list(color),
                "score": 0,
            }
        ]

    if mode == SHAPE_MODE_MIXED:
        aspect = max(w, h) / max(1, min(w, h))
        if aspect >= 2.2:
            return [
                {
                    "type": RECTANGLE,
                    "data": [cx, cy, w, h],
                    "color": list(color),
                    "score": 0,
                }
            ]
        diameter = max(1, min(w, h))
        return [
            {
                "type": ROTATED_ELLIPSE,
                "data": [cx, cy, diameter, diameter, 45 if w != h else 0],
                "color": list(color),
                "score": 0,
            }
        ]

    return [
        {
            "type": RECTANGLE,
            "data": [cx, cy, w, h],
            "color": list(color),
            "score": 0,
        }
    ]


def rectangles_to_shapes(
    rectangles: Sequence[Rect],
    image_width: int,
    image_height: int,
    color: ColorRGBA,
    shape_mode: str = SHAPE_MODE_RECTANGLES,
) -> List[dict]:
    shapes = []
    for x0, y0, width, height in rectangles:
        shapes.extend(_rect_to_primitive_shapes(x0, y0, width, height, color, shape_mode))
    if len(shapes) > MAX_GEOMETRY_SHAPES:
        raise ValueError(
            f"Text trace produced {len(shapes)} shapes (limit {MAX_GEOMETRY_SHAPES}). "
            "Increase cell size, choose a simpler shape mode, or reduce font size / resolution."
        )
    background = {
        "type": RECTANGLE,
        "data": [0, 0, int(image_width), int(image_height)],
        "color": [0, 0, 0, 0],
        "score": 0,
    }
    return [background] + shapes


def build_geometry_from_mask(
    mask,
    color: ColorRGBA,
    cell_size: int = 1,
    shape_mode: str = SHAPE_MODE_RECTANGLES,
) -> dict:
    rectangles = decompose_mask_to_rectangles(mask, cell_size=cell_size)
    if not rectangles:
        raise ValueError("No text pixels detected in image mask")
    width, height = mask.size
    payload = {
        "shapes": rectangles_to_shapes(
            rectangles,
            width,
            height,
            color,
            shape_mode=shape_mode,
        )
    }
    return normalize_geometry_payload(payload)


def build_geometry_from_text(
    text: str,
    color: ColorRGBA = (255, 255, 255, 255),
    font_path: Path | None = None,
    font_size: int = 120,
    cell_size: int = 1,
    bold: bool = False,
    strict_glyph_check: bool = True,
    shape_mode: str = SHAPE_MODE_RECTANGLES,
) -> dict:
    resolved_font = Path(font_path) if font_path else find_font_for_text(text)
    if strict_glyph_check:
        ok, missing = validate_text_coverage(text, resolved_font)
        if not ok:
            hint = (
                " For Korean, choose a [KR] font such as Malgun Gothic."
                if any(is_hangul_char(char) for char in text)
                else " Choose a text font that supports every character in your input."
            )
            raise ValueError(
                f"Font {resolved_font.name} is missing {len(missing)} character(s): "
                f"{format_missing_chars(missing)}. Choose another font or install a fuller CJK face.{hint}"
            )
    mask = render_text_mask(text, font_path=resolved_font, font_size=font_size, bold=bold)
    return build_geometry_from_mask(mask, color=color, cell_size=cell_size, shape_mode=shape_mode)


def build_geometry_from_text_image(
    image_path: Path,
    color: ColorRGBA | None = None,
    cell_size: int = 1,
    invert: bool = False,
    threshold: int = 128,
    sample_text_color: bool = True,
    shape_mode: str = SHAPE_MODE_RECTANGLES,
) -> dict:
    mask = load_text_image_mask(image_path, invert=invert, threshold=threshold)
    if color is None and sample_text_color:
        color = _sample_ink_color(image_path, mask, threshold, invert)
    if color is None:
        color = (255, 255, 255, 255)
    return build_geometry_from_mask(mask, color=color, cell_size=cell_size, shape_mode=shape_mode)


def _sample_ink_color(image_path: Path, mask, threshold: int, invert: bool) -> ColorRGBA:
    Image, _, _ = _load_pillow()
    source = Image.open(image_path).convert("RGBA")
    if invert:
        from PIL import ImageOps

        source = ImageOps.invert(source.convert("RGB")).convert("RGBA")
    mask_pixels = mask.load()
    totals = [0, 0, 0]
    count = 0
    width, height = source.size
    for y in range(min(height, mask.size[1])):
        for x in range(min(width, mask.size[0])):
            if mask_pixels[x, y] < threshold:
                continue
            r, g, b, a = source.getpixel((x, y))
            if a < 16:
                continue
            totals[0] += r
            totals[1] += g
            totals[2] += b
            count += 1
    if not count:
        return (255, 255, 255, 255)
    return (
        int(totals[0] / count),
        int(totals[1] / count),
        int(totals[2] / count),
        255,
    )


def write_geometry_json(path: Path, payload: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def contains_cjk(text: str) -> bool:
    return any(is_cjk_char(char) for char in text)


def estimate_layer_count(payload: dict) -> int:
    if is_text_typecode_payload(payload):
        return len(payload.get("shapes", []))
    return max(0, len(payload.get("shapes", [])) - 1)


def count_drawable_trace_layers_from_mask(
    mask,
    *,
    cell_size: int = 1,
    shape_mode: str = SHAPE_MODE_RECTANGLES,
    extra_shapes: bool = False,
    trace_method: str | None = None,
    allow_overlapping_shapes: bool = False,
    vertical: bool = False,
) -> tuple[int, List[Rect] | None]:
    _method, uses_strokes, prefer_skeleton = resolve_text_trace_pipeline(
        trace_method=trace_method,
        shape_mode=shape_mode,
        allow_overlapping_shapes=allow_overlapping_shapes,
        extra_shapes=extra_shapes,
    )
    if extra_shapes:
        from text.curved_trace import count_curved_shapes_from_mask

        return count_curved_shapes_from_mask(mask, cell_size=cell_size), None
    if uses_strokes:
        from text.stroke_trace import count_stroke_layers_from_mask

        return (
            count_stroke_layers_from_mask(
                mask,
                vertical=vertical,
                prefer_overlap=prefer_skeleton,
            ),
            None,
        )
    rectangles = decompose_mask_to_rectangles(mask, cell_size=cell_size)
    if not rectangles:
        return 0, None
    shapes = rectangles_to_typecode_shapes(rectangles, (255, 255, 255, 255), shape_mode=shape_mode)
    return len(shapes), rectangles


def count_trace_layers_from_mask(
    mask,
    *,
    cell_size: int = 1,
    shape_mode: str = SHAPE_MODE_RECTANGLES,
    extra_shapes: bool = False,
    trace_method: str | None = None,
    allow_overlapping_shapes: bool = False,
    mask_options=None,
    vertical: bool = False,
) -> int:
    from text.layer_masks import TextMaskOptions, polish_supported_for_shape_mode
    from pixel_art_geometry import FH6_BOUNDARY_LAYERS
    from text.mask_polish import estimate_polish_mask_layers

    options = mask_options if mask_options is not None else TextMaskOptions()
    resolved_method, _uses_strokes, prefer_skeleton = resolve_text_trace_pipeline(
        trace_method=trace_method,
        shape_mode=shape_mode,
        allow_overlapping_shapes=allow_overlapping_shapes,
        extra_shapes=extra_shapes,
    )
    drawable, trace_rectangles = count_drawable_trace_layers_from_mask(
        mask,
        cell_size=cell_size,
        shape_mode=shape_mode,
        extra_shapes=extra_shapes,
        trace_method=trace_method,
        allow_overlapping_shapes=allow_overlapping_shapes,
        vertical=vertical,
    )
    polish = 0
    if (
        options.include_polish_masks
        and trace_rectangles
        and polish_supported_for_shape_mode(
            shape_mode,
            extra_shapes=extra_shapes,
            trace_method=resolved_method,
            allow_overlapping_shapes=prefer_skeleton,
        )
    ):
        polish = estimate_polish_mask_layers(
            mask,
            trace_rectangles,
            polish_cell_size=options.polish_cell_size,
            margin=options.polish_margin,
        )
    boundary = FH6_BOUNDARY_LAYERS if options.include_boundary_masks else 0
    return drawable + polish + boundary


def estimate_traced_text_layers(
    text: str,
    *,
    font_path: Path | None = None,
    font_size: int = 120,
    cell_size: int = 1,
    shape_mode: str = SHAPE_MODE_RECTANGLES,
    bold: bool = False,
    extra_shapes: bool = False,
    trace_method: str | None = None,
    allow_overlapping_shapes: bool = False,
    mask_options=None,
    writing_mode: str | None = None,
    layout=None,
) -> int:
    from text.layout import layout_options_from_writing_mode

    resolved_font = Path(font_path) if font_path else find_font_for_text(text)
    layout_opts = layout if layout is not None else layout_options_from_writing_mode(writing_mode)
    mask = render_text_mask(
        text,
        font_path=resolved_font,
        font_size=font_size,
        bold=bold,
        layout=layout_opts,
    )
    return count_trace_layers_from_mask(
        mask,
        cell_size=cell_size,
        shape_mode=shape_mode,
        extra_shapes=extra_shapes,
        trace_method=trace_method,
        allow_overlapping_shapes=allow_overlapping_shapes,
        mask_options=mask_options,
        vertical=layout_opts.is_vertical,
    )


def resolve_cell_size_for_layer_budget(
    text: str,
    *,
    font_path: Path | None = None,
    font_size: int = 120,
    shape_mode: str = SHAPE_MODE_RECTANGLES,
    max_layers: int,
    bold: bool = False,
    extra_shapes: bool = False,
    mask_options=None,
    writing_mode: str | None = None,
    layout=None,
) -> tuple[int, int]:
    """Increase cell_size until traced drawable count is <= max_layers (or cell_size is 16)."""
    from text.layer_masks import TextMaskOptions
    from text.layout import layout_options_from_writing_mode

    options = mask_options if mask_options is not None else TextMaskOptions()
    budget = max(1, int(max_layers))
    resolved_font = Path(font_path) if font_path else find_font_for_text(text)
    layout_opts = layout if layout is not None else layout_options_from_writing_mode(writing_mode)
    mask = render_text_mask(
        text,
        font_path=resolved_font,
        font_size=font_size,
        bold=bold,
        layout=layout_opts,
    )
    vertical = layout_opts.is_vertical
    for cell_size in range(1, 17):
        last_count, _ = count_drawable_trace_layers_from_mask(
            mask,
            cell_size=cell_size,
            shape_mode=shape_mode,
            extra_shapes=extra_shapes,
            vertical=vertical,
        )
        if last_count <= budget:
            total = count_trace_layers_from_mask(
                mask,
                cell_size=cell_size,
                shape_mode=shape_mode,
                extra_shapes=extra_shapes,
                mask_options=options,
                vertical=vertical,
            )
            return cell_size, total
    total = count_trace_layers_from_mask(
        mask,
        cell_size=16,
        shape_mode=shape_mode,
        extra_shapes=extra_shapes,
        mask_options=options,
        vertical=vertical,
    )
    return 16, total


def build_typecode_from_text_with_options(
    text: str,
    *,
    color: ColorRGBA = (255, 255, 255, 255),
    font_path: Path | None = None,
    font_size: int = 120,
    cell_size: int = 1,
    bold: bool = False,
    strict_glyph_check: bool = True,
    shape_mode: str = SHAPE_MODE_RECTANGLES,
    use_forza_font: bool = False,
    forza_font_index: int = 1,
    fit_layer_budget: bool = False,
    max_drawable_layers: int | None = None,
    extra_shapes: bool = False,
    trace_method: str | None = None,
    allow_overlapping_shapes: bool = False,
    mask_options=None,
    writing_mode: str | None = None,
    layout=None,
) -> tuple[dict, int]:
    """Build type-code JSON; return (payload, cell_size_used)."""
    from text.layer_masks import TextMaskOptions
    from text.layout import layout_options_from_writing_mode

    options = mask_options if mask_options is not None else TextMaskOptions()
    layout_opts = layout if layout is not None else layout_options_from_writing_mode(writing_mode)
    resolved_method, _uses_strokes, _prefer_skeleton = resolve_text_trace_pipeline(
        trace_method=trace_method,
        shape_mode=shape_mode,
        allow_overlapping_shapes=allow_overlapping_shapes,
        extra_shapes=extra_shapes,
    )
    if max_drawable_layers is not None:
        options = TextMaskOptions(
            include_boundary_masks=options.include_boundary_masks,
            include_polish_masks=options.include_polish_masks,
            polish_cell_size=options.polish_cell_size,
            polish_margin=options.polish_margin,
            max_drawable_layers=max_drawable_layers,
        )
    if use_forza_font:
        from text.forza_fonts import build_typecode_from_forza_font

        payload = build_typecode_from_forza_font(
            text,
            font_index=forza_font_index,
            color=color,
            font_size=font_size,
        )
        return payload, 1

    resolved_cell = normalize_trace_cell_size(cell_size)
    if (
        fit_layer_budget
        and options.max_drawable_layers is not None
        and trace_method_uses_grid(resolved_method)
    ):
        resolved_cell, _ = resolve_cell_size_for_layer_budget(
            text,
            font_path=font_path,
            font_size=font_size,
            shape_mode=shape_mode,
            max_layers=options.max_drawable_layers,
            bold=bold,
            extra_shapes=extra_shapes,
            mask_options=options,
            layout=layout_opts,
        )

    payload = build_typecode_from_text(
        text,
        color=color,
        font_path=font_path,
        font_size=font_size,
        cell_size=resolved_cell,
        bold=bold,
        strict_glyph_check=strict_glyph_check,
        shape_mode=shape_mode,
        extra_shapes=extra_shapes,
        trace_method=trace_method,
        allow_overlapping_shapes=allow_overlapping_shapes,
        mask_options=options,
        layout=layout_opts,
    )
    return payload, resolved_cell


def estimate_typed_text_layers(
    text: str,
    *,
    font_path: Path | None = None,
    font_size: int = 120,
    cell_size: int = 1,
    shape_mode: str = SHAPE_MODE_RECTANGLES,
    use_forza_font: bool = False,
    forza_font_index: int = 1,
    fit_layer_budget: bool = False,
    max_drawable_layers: int | None = None,
    extra_shapes: bool = False,
    trace_method: str | None = None,
    allow_overlapping_shapes: bool = False,
    mask_options=None,
    writing_mode: str | None = None,
    layout=None,
) -> tuple[int, int, dict]:
    """Return (total_layers, cell_size_used, layer_summary)."""
    from text.layer_masks import TextMaskOptions, polish_supported_for_shape_mode
    from pixel_art_geometry import FH6_BOUNDARY_LAYERS
    from text.layout import layout_options_from_writing_mode
    from text.mask_polish import estimate_polish_mask_layers

    empty_summary = {
        "drawable_count": 0,
        "polish_mask_count": 0,
        "boundary_mask_count": 0,
        "total_layers": 0,
    }
    if not text or not text.strip():
        return 0, normalize_trace_cell_size(cell_size), empty_summary

    options = mask_options if mask_options is not None else TextMaskOptions()
    resolved_method, _uses_strokes, prefer_skeleton = resolve_text_trace_pipeline(
        trace_method=trace_method,
        shape_mode=shape_mode,
        allow_overlapping_shapes=allow_overlapping_shapes,
        extra_shapes=extra_shapes,
    )
    if max_drawable_layers is not None:
        options = TextMaskOptions(
            include_boundary_masks=options.include_boundary_masks,
            include_polish_masks=options.include_polish_masks,
            polish_cell_size=options.polish_cell_size,
            polish_margin=options.polish_margin,
            max_drawable_layers=max_drawable_layers,
        )

    if use_forza_font:
        from text.forza_fonts import estimate_forza_font_layer_count

        count = estimate_forza_font_layer_count(text)
        summary = {
            "drawable_count": count,
            "polish_mask_count": 0,
            "boundary_mask_count": 0,
            "total_layers": count,
        }
        return count, 1, summary

    resolved_cell = normalize_trace_cell_size(cell_size)
    resolved_font = Path(font_path) if font_path else find_font_for_text(text)
    layout_opts = layout if layout is not None else layout_options_from_writing_mode(writing_mode)
    mask = render_text_mask(
        text,
        font_path=resolved_font,
        font_size=font_size,
        layout=layout_opts,
    )
    vertical = layout_opts.is_vertical

    if fit_layer_budget and options.max_drawable_layers is not None and trace_method_uses_grid(resolved_method):
        resolved_cell, total = resolve_cell_size_for_layer_budget(
            text,
            font_path=font_path,
            font_size=font_size,
            shape_mode=shape_mode,
            max_layers=options.max_drawable_layers,
            extra_shapes=extra_shapes,
            mask_options=options,
            layout=layout_opts,
        )
    else:
        total = count_trace_layers_from_mask(
            mask,
            cell_size=resolved_cell,
            shape_mode=shape_mode,
            extra_shapes=extra_shapes,
            trace_method=trace_method,
            allow_overlapping_shapes=allow_overlapping_shapes,
            mask_options=options,
            vertical=vertical,
        )

    drawable, trace_rectangles = count_drawable_trace_layers_from_mask(
        mask,
        cell_size=resolved_cell,
        shape_mode=shape_mode,
        extra_shapes=extra_shapes,
        trace_method=trace_method,
        allow_overlapping_shapes=allow_overlapping_shapes,
        vertical=vertical,
    )
    polish = 0
    if (
        options.include_polish_masks
        and trace_rectangles
        and polish_supported_for_shape_mode(
            shape_mode,
            extra_shapes=extra_shapes,
            trace_method=resolved_method,
            allow_overlapping_shapes=prefer_skeleton,
        )
    ):
        polish = estimate_polish_mask_layers(
            mask,
            trace_rectangles,
            polish_cell_size=options.polish_cell_size,
            margin=options.polish_margin,
        )
    boundary = FH6_BOUNDARY_LAYERS if options.include_boundary_masks else 0
    summary = {
        "drawable_count": drawable,
        "polish_mask_count": polish,
        "boundary_mask_count": boundary,
        "total_layers": drawable + polish + boundary,
    }
    return summary["total_layers"], resolved_cell, summary
