"""Polish mask generation: clip coarse trace overflow with FH6 mask layers."""

from __future__ import annotations

from typing import List, Sequence, Tuple

from fh6_layer_masks import MASK_ROLE_POLISH, make_fh6_mask_shape

Rect = Tuple[int, int, int, int]


def _load_pillow():
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("Pillow is required for polish masks.") from exc
    return Image, ImageDraw


def rasterize_trace_rectangles(width: int, height: int, rectangles: Sequence[Rect]):
    Image, ImageDraw = _load_pillow()
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    for x0, y0, rect_w, rect_h in rectangles:
        if rect_w <= 0 or rect_h <= 0:
            continue
        draw.rectangle((x0, y0, x0 + rect_w - 1, y0 + rect_h - 1), fill=255)
    return image


def build_overflow_bitmap(ideal_mask, coverage_mask, *, margin: int = 0):
    Image, _ImageDraw = _load_pillow()
    width, height = ideal_mask.size
    ideal = ideal_mask.convert("L")
    coverage = coverage_mask.convert("L")
    if margin > 0:
        from text_geometry import normalize_trace_cell_size

        shrink = max(1, normalize_trace_cell_size(margin))
        eroded = Image.new("L", (width, height), 0)
        ideal_px = ideal.load()
        eroded_px = eroded.load()
        for y in range(height):
            for x in range(width):
                if ideal_px[x, y] < 128:
                    continue
                keep = True
                for dy in range(-shrink, shrink + 1):
                    for dx in range(-shrink, shrink + 1):
                        nx = x + dx
                        ny = y + dy
                        if nx < 0 or ny < 0 or nx >= width or ny >= height or ideal_px[nx, ny] < 128:
                            keep = False
                            break
                    if not keep:
                        break
                if keep:
                    eroded_px[x, y] = 255
        ideal = eroded

    overflow = Image.new("L", (width, height), 0)
    ideal_px = ideal.load()
    coverage_px = coverage.load()
    overflow_px = overflow.load()
    for y in range(height):
        for x in range(width):
            if coverage_px[x, y] >= 128 and ideal_px[x, y] < 128:
                overflow_px[x, y] = 255
    return overflow


def build_polish_mask_rectangles(
    ideal_mask,
    trace_rectangles: Sequence[Rect],
    *,
    polish_cell_size: int = 4,
    margin: int = 0,
) -> List[Rect]:
    if not trace_rectangles:
        return []
    width, height = ideal_mask.size
    coverage = rasterize_trace_rectangles(width, height, trace_rectangles)
    overflow = build_overflow_bitmap(ideal_mask, coverage, margin=margin)
    if overflow.getextrema()[1] <= 0:
        return []
    from text_geometry import decompose_mask_to_rectangles, normalize_trace_cell_size

    return decompose_mask_to_rectangles(overflow, cell_size=normalize_trace_cell_size(polish_cell_size))


def build_polish_mask_shapes(
    ideal_mask,
    trace_rectangles: Sequence[Rect],
    *,
    polish_cell_size: int = 4,
    margin: int = 0,
) -> List[dict]:
    rectangles = build_polish_mask_rectangles(
        ideal_mask,
        trace_rectangles,
        polish_cell_size=polish_cell_size,
        margin=margin,
    )
    return [
        make_fh6_mask_shape(x0, y0, rect_w, rect_h, mask_role=MASK_ROLE_POLISH)
        for x0, y0, rect_w, rect_h in rectangles
    ]


def estimate_polish_mask_layers(
    ideal_mask,
    trace_rectangles: Sequence[Rect],
    *,
    polish_cell_size: int = 4,
    margin: int = 0,
) -> int:
    return len(
        build_polish_mask_rectangles(
            ideal_mask,
            trace_rectangles,
            polish_cell_size=polish_cell_size,
            margin=margin,
        )
    )
