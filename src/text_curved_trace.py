"""
Trace text masks using FH6 curve primitives (quarter circle, half circle, rounded square).

Used when Text vinyl "extra shapes" is enabled for smoother CJK/Latin curves.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from fh6_shape_catalog import get_primitive_type_code, get_square_type_code
from pixel_art_geometry import POSITION_SCALE, SIZE_SCALE
from text_geometry import (
    Rect,
    TEXT_TYPECODE_SCORE,
    decompose_mask_to_rectangles,
    normalize_trace_cell_size,
)

ColorRGBA = Tuple[int, int, int, int]
Corner = Tuple[int, int, str]  # row, col, orientation nw|ne|se|sw

_EXTRA_SHAPE_CACHE: dict[str, int] = {}


def _type_code(name: str, fallback: int) -> int:
    if name not in _EXTRA_SHAPE_CACHE:
        code = get_primitive_type_code(name)
        _EXTRA_SHAPE_CACHE[name] = code if code is not None else fallback
    return _EXTRA_SHAPE_CACHE[name]


def extra_shape_type_codes() -> dict[str, int]:
    return {
        "square": get_square_type_code(),
        "circle": _type_code("Circle", 1048687),
        "ellipse": _type_code("Ellipse", 1048715),
        "quarter_circle": _type_code("Quarter Circle", 1048694),
        "half_circle": _type_code("Half Circle", 1048679),
        "rounded_square": _type_code("Rounded Square", 1048692),
    }


def _make_shape(
    type_code: int,
    cx_px: float,
    cy_px: float,
    sx_px: float,
    sy_px: float,
    rotation: float,
    color: ColorRGBA,
) -> dict:
    return {
        "type": int(type_code),
        "data": [
            cx_px * POSITION_SCALE,
            cy_px * POSITION_SCALE,
            max(0.01, sx_px) * SIZE_SCALE,
            max(0.01, sy_px) * SIZE_SCALE,
            float(rotation),
            0.0,
            0,
        ],
        "color": [int(color[0]), int(color[1]), int(color[2]), int(color[3])],
        "score": TEXT_TYPECODE_SCORE,
    }


def _mask_to_grid(mask, cell_size: int) -> tuple[list[list[bool]], int, int]:
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
    return grid, width, height


def _grid_get(grid: list[list[bool]], row: int, col: int) -> bool:
    if row < 0 or col < 0 or row >= len(grid) or col >= len(grid[0]):
        return False
    return grid[row][col]


def find_convex_corners(grid: list[list[bool]]) -> List[Corner]:
    corners: List[Corner] = []
    rows = len(grid)
    if rows == 0:
        return corners
    cols = len(grid[0])
    for row in range(rows):
        for col in range(cols):
            if not grid[row][col]:
                continue
            up = _grid_get(grid, row - 1, col)
            down = _grid_get(grid, row + 1, col)
            left = _grid_get(grid, row, col - 1)
            right = _grid_get(grid, row, col + 1)
            if not up and not left:
                corners.append((row, col, "nw"))
            if not up and not right:
                corners.append((row, col, "ne"))
            if not down and not left:
                corners.append((row, col, "sw"))
            if not down and not right:
                corners.append((row, col, "se"))
    return corners


def _decompose_grid_rectangles(
    grid: list[list[bool]],
    cell_size: int,
    image_width: int,
    image_height: int,
    skip: set[tuple[int, int]],
) -> List[Rect]:
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    visited = [[False] * cols for _ in range(rows)]
    rectangles: List[Rect] = []
    for row in range(rows):
        col = 0
        while col < cols:
            if not grid[row][col] or visited[row][col] or (row, col) in skip:
                col += 1
                continue
            span = 1
            while (
                col + span < cols
                and grid[row][col + span]
                and not visited[row][col + span]
                and (row, col + span) not in skip
            ):
                span += 1
            height_span = 1
            can_grow = True
            while row + height_span < rows and can_grow:
                for dx in range(span):
                    c = col + dx
                    r = row + height_span
                    if not grid[r][c] or visited[r][c] or (r, c) in skip:
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
                    min(image_width - x0, span * cell_size),
                    min(image_height - y0, height_span * cell_size),
                )
            )
            col += span
    return rectangles


def _quarter_circle_shape(
    row: int,
    col: int,
    orientation: str,
    cell_size: int,
    color: ColorRGBA,
    codes: dict[str, int],
) -> dict:
    """Place a quarter-circle primitive on a convex corner cell."""
    cs = float(cell_size)
    x0 = col * cell_size
    y0 = row * cell_size
    diameter = cs * 2.0
  # Cover the corner quadrant generously.
    if orientation == "nw":
        cx = x0 + cs * 0.5
        cy = y0 + cs * 0.5
        rotation = 180.0
    elif orientation == "ne":
        cx = x0 + cs * 1.5
        cy = y0 + cs * 0.5
        rotation = 270.0
    elif orientation == "sw":
        cx = x0 + cs * 0.5
        cy = y0 + cs * 1.5
        rotation = 90.0
    else:  # se
        cx = x0 + cs * 1.5
        cy = y0 + cs * 1.5
        rotation = 0.0
    return _make_shape(codes["quarter_circle"], cx, cy, diameter, diameter, rotation, color)


def _rectangle_to_curved_shape(
    rect: Rect,
    color: ColorRGBA,
    codes: dict[str, int],
) -> dict:
    x0, y0, width, height = rect
    cx = float(x0) + float(width) / 2.0
    cy = float(y0) + float(height) / 2.0
    w = max(1, width)
    h = max(1, height)
    aspect = max(w, h) / max(1, min(w, h))

    if aspect >= 2.4:
        return _make_shape(codes["square"], cx, cy, float(w), float(h), 0.0, color)

    if aspect <= 1.35 and min(w, h) <= max(w, h) * 0.55 + 4:
        side = float(max(w, h))
        if min(w, h) * 2 < max(w, h):
            return _make_shape(codes["half_circle"], cx, cy, float(w), float(h), 0.0, color)
        return _make_shape(codes["circle"], cx, cy, side, side, 0.0, color)

    if aspect <= 1.45:
        side = float(max(w, h))
        return _make_shape(codes["rounded_square"], cx, cy, side, side, 0.0, color)

    return _make_shape(codes["ellipse"], cx, cy, float(w), float(h), 0.0, color)


def build_curved_typecode_shapes(
    mask,
    color: ColorRGBA,
    *,
    cell_size: int = 1,
) -> List[dict]:
    cell_size = normalize_trace_cell_size(cell_size)
    grid, image_width, image_height = _mask_to_grid(mask, cell_size)
    if not any(any(row) for row in grid):
        return []

    codes = extra_shape_type_codes()
    corners = find_convex_corners(grid)
    corner_cells = {(row, col) for row, col, _orient in corners}

    shapes: List[dict] = []
    for row, col, orient in corners:
        shapes.append(_quarter_circle_shape(row, col, orient, cell_size, color, codes))

    rectangles = _decompose_grid_rectangles(
        grid, cell_size, image_width, image_height, corner_cells
    )
    for rect in rectangles:
        shapes.append(_rectangle_to_curved_shape(rect, color, codes))

    if not shapes:
        rectangles = decompose_mask_to_rectangles(mask, cell_size=cell_size)
        for x0, y0, width, height in rectangles:
            shapes.append(_rectangle_to_curved_shape((x0, y0, width, height), color, codes))

    return shapes


def count_curved_shapes_from_mask(mask, *, cell_size: int = 1) -> int:
    return len(build_curved_typecode_shapes(mask, (255, 255, 255, 255), cell_size=cell_size))
