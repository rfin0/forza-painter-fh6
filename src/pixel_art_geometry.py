"""Convert pixel grids and raster/SVG sources into FH6 handmade type-code JSON."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Iterator, List, Sequence, Tuple

from fh6_shape_catalog import get_square_type_code
from security_policy import MAX_IMAGE_DIMENSION, MAX_TEMPLATE_LAYER_COUNT

ColorRGBA = Tuple[int, int, int, int]
RectColor = Tuple[int, int, int, int, ColorRGBA]  # x, y, w, h, color

try:
    FH6_SQUARE_TYPECODE = get_square_type_code()
except FileNotFoundError:
    FH6_SQUARE_TYPECODE = 1048677
POSITION_SCALE = 1.28
SIZE_SCALE = 0.01
DEFAULT_SCORE = 0.8008135
FH6_BOUNDARY_LAYERS = 4
MAX_DRAWABLE_LAYERS = max(1, MAX_TEMPLATE_LAYER_COUNT - FH6_BOUNDARY_LAYERS)

MAX_EDITOR_DIMENSION = 256
MAX_IMPORT_DIMENSION = 512
DEFAULT_PALETTE: Tuple[ColorRGBA, ...] = (
    (0, 0, 0, 255),
    (255, 255, 255, 255),
    (136, 0, 0, 255),
    (170, 255, 238, 255),
    (204, 68, 204, 255),
    (0, 204, 85, 255),
    (0, 0, 170, 255),
    (238, 238, 119, 255),
    (221, 136, 85, 255),
    (102, 68, 0, 255),
    (255, 119, 119, 255),
    (51, 51, 51, 255),
    (119, 119, 119, 255),
    (170, 255, 102, 255),
    (0, 136, 255, 255),
    (187, 187, 187, 255),
)


class MergeMode(str, Enum):
    AUTO = "auto"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    GRID_2D = "grid_2d"


MERGE_MODE_ALIASES = {
    "auto": MergeMode.AUTO,
    "horizontal": MergeMode.HORIZONTAL,
    "vertical": MergeMode.VERTICAL,
    "grid_2d": MergeMode.GRID_2D,
    "grid2d": MergeMode.GRID_2D,
    "2d": MergeMode.GRID_2D,
}


def normalize_merge_mode(value: str | None) -> MergeMode:
    if not value:
        return MergeMode.AUTO
    key = str(value).strip().lower().replace("-", "_")
    return MERGE_MODE_ALIASES.get(key, MergeMode.AUTO)


def merge_mode_choices() -> List[str]:
    return [mode.value for mode in MergeMode]


@dataclass
class ColorGrid:
    width: int
    height: int
    cells: Tuple[ColorRGBA | None, ...]

    def __post_init__(self) -> None:
        expected = self.width * self.height
        if len(self.cells) != expected:
            raise ValueError(f"grid expects {expected} cells, got {len(self.cells)}")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("grid dimensions must be positive")

    @classmethod
    def empty(cls, width: int, height: int) -> ColorGrid:
        _validate_dimensions(width, height, max_dim=MAX_EDITOR_DIMENSION)
        return cls(width, height, tuple(None for _ in range(width * height)))

    @classmethod
    def from_flat(cls, width: int, height: int, cells: Sequence[ColorRGBA | None]) -> ColorGrid:
        return cls(width, height, tuple(cells))

    def get(self, x: int, y: int) -> ColorRGBA | None:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return None
        return self.cells[y * self.width + x]

    def set(self, x: int, y: int, color: ColorRGBA | None) -> ColorGrid:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return self
        data = list(self.cells)
        data[y * self.width + x] = color
        return ColorGrid(self.width, self.height, tuple(data))

    def filled_pixel_count(self) -> int:
        return sum(1 for cell in self.cells if cell is not None and cell[3] > 0)

    def copy(self) -> ColorGrid:
        return ColorGrid(self.width, self.height, self.cells)

    def iter_pixels(self) -> Iterator[Tuple[int, int, ColorRGBA]]:
        for y in range(self.height):
            for x in range(self.width):
                color = self.get(x, y)
                if color is not None and color[3] > 0:
                    yield x, y, color


def _validate_dimensions(width: int, height: int, *, max_dim: int) -> None:
    width = int(width)
    height = int(height)
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if width > max_dim or height > max_dim:
        raise ValueError(f"dimensions exceed limit {max_dim}x{max_dim}")
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise ValueError(f"dimensions exceed limit {MAX_IMAGE_DIMENSION}px")


def _load_pillow():
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required for pixel art conversion.") from exc
    return Image


def _clamp_byte(value: float | int) -> int:
    return max(0, min(255, int(round(value))))


def parse_hex_color(value: str) -> ColorRGBA:
    return _parse_hex_color(value)


def _parse_hex_color(value: str) -> ColorRGBA:
    raw = str(value or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        raise ValueError(f"invalid hex color: {value!r}")
    return (
        int(raw[0:2], 16),
        int(raw[2:4], 16),
        int(raw[4:6], 16),
        255,
    )


def _colors_close(a: ColorRGBA, b: ColorRGBA, tolerance: int) -> bool:
    if tolerance <= 0:
        return a == b
    return all(abs(int(a[i]) - int(b[i])) <= tolerance for i in range(3))


def _maybe_downscale(image, *, target_width: int | None, target_height: int | None):
    Image = _load_pillow()
    width, height = image.size
    tw = int(target_width) if target_width else width
    th = int(target_height) if target_height else height
    if tw <= 0 or th <= 0:
        raise ValueError("target width and height must be positive")
    if tw == width and th == height:
        return image
    return image.resize((tw, th), Image.Resampling.NEAREST)


def _quantize_image(image, max_colors: int):
    if max_colors <= 0 or max_colors >= 256:
        return image
    alpha = image.getchannel("A") if "A" in image.getbands() else None
    rgb = image.convert("RGB")
    quantized = rgb.quantize(colors=max(2, int(max_colors)), method=_load_pillow().Quantize.MEDIANCUT)
    result = quantized.convert("RGBA")
    if alpha is not None:
        result.putalpha(alpha)
    return result


def grid_from_raster(
    path: Path,
    *,
    alpha_threshold: int = 128,
    background_color: ColorRGBA | None = None,
    color_tolerance: int = 0,
    max_colors: int = 0,
    target_width: int | None = None,
    target_height: int | None = None,
) -> ColorGrid:
    Image = _load_pillow()
    path = Path(path)
    with Image.open(path) as source:
        image = source.convert("RGBA")
    image = _maybe_downscale(image, target_width=target_width, target_height=target_height)
    if max_colors > 0:
        image = _quantize_image(image, max_colors)
    width, height = image.size
    _validate_dimensions(width, height, max_dim=MAX_IMPORT_DIMENSION)
    pixels = image.load()
    cells: List[ColorRGBA | None] = []
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a < alpha_threshold:
                cells.append(None)
                continue
            color = (_clamp_byte(r), _clamp_byte(g), _clamp_byte(b), 255)
            if background_color is not None and _colors_close(color, background_color, color_tolerance):
                cells.append(None)
                continue
            cells.append(color)
    return ColorGrid(width, height, tuple(cells))


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _parse_length(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    match = re.match(r"^\s*(-?\d+(?:\.\d+)?)", str(value))
    if not match:
        return default
    return float(match.group(1))


def _svg_canvas_size(root: ET.Element) -> Tuple[int, int]:
    width = int(round(_parse_length(root.get("width"))))
    height = int(round(_parse_length(root.get("height"))))
    if width > 0 and height > 0:
        return width, height
    view_box = root.get("viewBox") or root.get("viewbox")
    if view_box:
        parts = [float(part) for part in re.split(r"[\s,]+", view_box.strip()) if part]
        if len(parts) == 4:
            return max(1, int(round(parts[2]))), max(1, int(round(parts[3])))
    raise ValueError("SVG is missing width/height or viewBox")


def _parse_svg_paint(element: ET.Element) -> ColorRGBA | None:
    for key in ("fill", "{http://www.w3.org/1999/xlink}fill"):
        raw = element.get(key)
        if raw is None:
            continue
        value = raw.strip().lower()
        if value in ("none", "transparent"):
            return None
        if value.startswith("#"):
            return _parse_hex_color(value)
    return (0, 0, 0, 255)


def grid_from_svg(path: Path) -> ColorGrid:
    path = Path(path)
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"invalid SVG: {path.name}") from exc
    width, height = _svg_canvas_size(root)
    _validate_dimensions(width, height, max_dim=MAX_IMPORT_DIMENSION)
    cells: List[ColorRGBA | None] = [None] * (width * height)
    found_rect = False
    for element in root.iter():
        if _local_tag(element.tag) != "rect":
            continue
        fill = _parse_svg_paint(element)
        if fill is None:
            continue
        x = int(round(_parse_length(element.get("x"))))
        y = int(round(_parse_length(element.get("y"))))
        w = max(1, int(round(_parse_length(element.get("width"), 1.0))))
        h = max(1, int(round(_parse_length(element.get("height"), 1.0))))
        found_rect = True
        for py in range(y, y + h):
            for px in range(x, x + w):
                if px < 0 or py < 0 or px >= width or py >= height:
                    continue
                cells[py * width + px] = fill
    if not found_rect:
        raise ValueError("SVG contains no filled <rect> elements")
    return ColorGrid(width, height, tuple(cells))


def load_color_grid(
    path: Path,
    *,
    alpha_threshold: int = 128,
    background_color: ColorRGBA | None = None,
    color_tolerance: int = 0,
    max_colors: int = 0,
    target_width: int | None = None,
    target_height: int | None = None,
) -> ColorGrid:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".svg":
        grid = grid_from_svg(path)
        if target_width or target_height:
            grid = _resize_grid(
                grid,
                target_width or grid.width,
                target_height or grid.height,
            )
        if max_colors > 0:
            grid = _reduce_grid_colors(grid, max_colors)
        return grid
    if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"}:
        return grid_from_raster(
            path,
            alpha_threshold=alpha_threshold,
            background_color=background_color,
            color_tolerance=color_tolerance,
            max_colors=max_colors,
            target_width=target_width,
            target_height=target_height,
        )
    raise ValueError(f"unsupported file type: {suffix or '(none)'}")


def _resize_grid(grid: ColorGrid, width: int, height: int) -> ColorGrid:
    width = max(1, int(width))
    height = max(1, int(height))
    _validate_dimensions(width, height, max_dim=MAX_IMPORT_DIMENSION)
    if width == grid.width and height == grid.height:
        return grid
    cells: List[ColorRGBA | None] = []
    for y in range(height):
        sy = min(grid.height - 1, int(y * grid.height / height))
        for x in range(width):
            sx = min(grid.width - 1, int(x * grid.width / width))
            cells.append(grid.get(sx, sy))
    return ColorGrid(width, height, tuple(cells))


def _reduce_grid_colors(grid: ColorGrid, max_colors: int) -> ColorGrid:
    Image = _load_pillow()
    image = Image.new("RGBA", (grid.width, grid.height), (0, 0, 0, 0))
    pixels = image.load()
    for x, y, color in grid.iter_pixels():
        pixels[x, y] = color
    reduced = _quantize_image(image, max_colors)
    return grid_from_raster_data(reduced)


def grid_from_raster_data(image) -> ColorGrid:
    width, height = image.size
    pixels = image.convert("RGBA").load()
    cells: List[ColorRGBA | None] = []
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a <= 0:
                cells.append(None)
            else:
                cells.append((_clamp_byte(r), _clamp_byte(g), _clamp_byte(b), 255))
    return ColorGrid(width, height, tuple(cells))


def merge_rectangles(grid: ColorGrid, mode: MergeMode | str) -> List[RectColor]:
    mode = normalize_merge_mode(mode.value if isinstance(mode, MergeMode) else mode)
    if mode == MergeMode.AUTO:
        horizontal = _merge_horizontal(grid)
        vertical = _merge_vertical(grid)
        grid2d = _merge_grid_2d(grid)
        candidates = (horizontal, vertical, grid2d)
        return min(candidates, key=len)
    if mode == MergeMode.HORIZONTAL:
        return _merge_horizontal(grid)
    if mode == MergeMode.VERTICAL:
        return _merge_vertical(grid)
    return _merge_grid_2d(grid)


def _merge_horizontal(grid: ColorGrid) -> List[RectColor]:
    rects: List[RectColor] = []
    for y in range(grid.height):
        x = 0
        while x < grid.width:
            color = grid.get(x, y)
            if color is None:
                x += 1
                continue
            width = 1
            while x + width < grid.width and grid.get(x + width, y) == color:
                width += 1
            rects.append((x, y, width, 1, color))
            x += width
    return rects


def _merge_vertical(grid: ColorGrid) -> List[RectColor]:
    rects: List[RectColor] = []
    for x in range(grid.width):
        y = 0
        while y < grid.height:
            color = grid.get(x, y)
            if color is None:
                y += 1
                continue
            height = 1
            while y + height < grid.height and grid.get(x, y + height) == color:
                height += 1
            rects.append((x, y, 1, height, color))
            y += height
    return rects


def _merge_grid_2d(grid: ColorGrid) -> List[RectColor]:
    visited = [[False] * grid.width for _ in range(grid.height)]
    rects: List[RectColor] = []
    for y in range(grid.height):
        for x in range(grid.width):
            if visited[y][x]:
                continue
            color = grid.get(x, y)
            if color is None:
                visited[y][x] = True
                continue
            span = 1
            while x + span < grid.width and not visited[y][x + span] and grid.get(x + span, y) == color:
                span += 1
            height = 1
            can_grow = True
            while y + height < grid.height and can_grow:
                for dx in range(span):
                    if visited[y + height][x + dx] or grid.get(x + dx, y + height) != color:
                        can_grow = False
                        break
                if can_grow:
                    height += 1
            for dy in range(height):
                for dx in range(span):
                    visited[y + dy][x + dx] = True
            rects.append((x, y, span, height, color))
    return rects


def estimate_layer_count(grid: ColorGrid, mode: MergeMode | str = MergeMode.AUTO) -> int:
    return len(merge_rectangles(grid, mode))


def rect_to_typecode_shape(x: int, y: int, width: int, height: int, color: ColorRGBA) -> dict:
    cx = float(x) * POSITION_SCALE + (float(width) * POSITION_SCALE) / 2.0
    cy = float(y) * POSITION_SCALE + (float(height) * POSITION_SCALE) / 2.0
    return {
        "type": FH6_SQUARE_TYPECODE,
        "data": [
            cx,
            cy,
            SIZE_SCALE * float(width),
            SIZE_SCALE * float(height),
            0.0,
            0.0,
            0,
        ],
        "color": [_clamp_byte(color[0]), _clamp_byte(color[1]), _clamp_byte(color[2]), _clamp_byte(color[3])],
        "score": DEFAULT_SCORE,
    }


def build_typecode_payload(rects: Iterable[RectColor]) -> dict:
    shapes = [rect_to_typecode_shape(x, y, w, h, color) for x, y, w, h, color in rects]
    if not shapes:
        raise ValueError("no drawable pixels found")
    return {
        "format": "fh6_pixel_art_typecode_v1",
        "created_by": "forza-painter-fh6",
        "coordinate_model": "endarz_pixel_grid_v1",
        "shapes": shapes,
    }


def build_typecode_json_from_grid(grid: ColorGrid, mode: MergeMode | str = MergeMode.AUTO) -> dict:
    rects = merge_rectangles(grid, mode)
    payload = build_typecode_payload(rects)
    if len(payload["shapes"]) > MAX_DRAWABLE_LAYERS:
        raise ValueError(
            f"merged output uses {len(payload['shapes'])} layers (FH6 drawable limit ~{MAX_DRAWABLE_LAYERS}). "
            "Reduce canvas size, lower color count, or simplify the art."
        )
    return payload


def build_typecode_json_from_path(
    path: Path,
    *,
    merge_mode: MergeMode | str = MergeMode.AUTO,
    alpha_threshold: int = 128,
    background_color: ColorRGBA | None = None,
    color_tolerance: int = 0,
    max_colors: int = 0,
    target_width: int | None = None,
    target_height: int | None = None,
) -> dict:
    grid = load_color_grid(
        path,
        alpha_threshold=alpha_threshold,
        background_color=background_color,
        color_tolerance=color_tolerance,
        max_colors=max_colors,
        target_width=target_width,
        target_height=target_height,
    )
    return build_typecode_json_from_grid(grid, merge_mode)


def write_typecode_json(path: Path, payload: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def layer_budget_message(layer_count: int) -> str:
    if layer_count <= MAX_DRAWABLE_LAYERS:
        return f"{layer_count} / {MAX_DRAWABLE_LAYERS} drawable layers"
    return f"{layer_count} / {MAX_DRAWABLE_LAYERS} drawable layers (over FH6 limit)"


def read_source_dimensions(path: Path) -> tuple[int, int]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".svg":
        root = ET.parse(path).getroot()
        return _svg_canvas_size(root)
    Image = _load_pillow()
    with Image.open(path) as image:
        return image.size


def _color_key(color: ColorRGBA) -> tuple[int, int, int]:
    return (_clamp_byte(color[0]), _clamp_byte(color[1]), _clamp_byte(color[2]))


def _count_colors_on_grid(grid: ColorGrid) -> dict[tuple[int, int, int], int]:
    counts: dict[tuple[int, int, int], int] = {}
    for _x, _y, color in grid.iter_pixels():
        key = _color_key(color)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _analyze_payload_shapes(payload: dict) -> dict:
    shapes = payload.get("shapes")
    if not isinstance(shapes, list):
        raise ValueError("payload does not contain shapes")
    filled_pixels = 0
    color_counts: dict[tuple[int, int, int], int] = {}
    min_x = min_y = 10**9
    max_x = max_y = -1
    for shape in shapes:
        if not isinstance(shape, dict):
            continue
        data = shape.get("data") or []
        if len(data) < 4:
            continue
        sx = float(data[2])
        sy = float(data[3])
        width = max(1, int(round(sx / SIZE_SCALE)))
        height = max(1, int(round(sy / SIZE_SCALE)))
        filled_pixels += width * height
        cx = float(data[0])
        cy = float(data[1])
        x0 = int(round(cx / POSITION_SCALE - width / 2.0))
        y0 = int(round(cy / POSITION_SCALE - height / 2.0))
        min_x = min(min_x, x0)
        min_y = min(min_y, y0)
        max_x = max(max_x, x0 + width)
        max_y = max(max_y, y0 + height)
        color = shape.get("color") or [255, 255, 255, 255]
        if len(color) >= 3:
            key = (_clamp_byte(color[0]), _clamp_byte(color[1]), _clamp_byte(color[2]))
            color_counts[key] = color_counts.get(key, 0) + (width * height)
    canvas_size = None
    if max_x >= min_x and max_y >= min_y:
        canvas_size = (max(1, max_x - min_x), max(1, max_y - min_y))
    merged_layers = len(shapes)
    return {
        "filled_pixels": filled_pixels,
        "merged_layers": merged_layers,
        "color_counts": color_counts,
        "canvas_size": canvas_size,
        "layer_budget": layer_budget_message(merged_layers),
    }


def analyze_pixel_art(
    *,
    grid: ColorGrid | None = None,
    payload: dict | None = None,
    merge_mode: MergeMode | str = MergeMode.AUTO,
) -> dict:
    if grid is not None:
        color_counts = _count_colors_on_grid(grid)
        merged_layers = estimate_layer_count(grid, merge_mode)
        return {
            "filled_pixels": grid.filled_pixel_count(),
            "merged_layers": merged_layers,
            "color_counts": color_counts,
            "canvas_size": (grid.width, grid.height),
            "layer_budget": layer_budget_message(merged_layers),
        }
    if payload is not None:
        return _analyze_payload_shapes(payload)
    raise ValueError("grid or payload is required")


def analyze_pixel_art_json(path: Path, *, merge_mode: MergeMode | str = MergeMode.AUTO) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return analyze_pixel_art(payload=payload, merge_mode=merge_mode)


def render_color_grid_preview(grid: ColorGrid, max_size=None) -> bytes | None:
    """Rasterize a pixel grid for UI previews (matches source art, not merged vinyl rects)."""
    from utils import load_pillow

    loaded = load_pillow()
    if not loaded:
        return None
    Image, ImageDraw = loaded
    if max_size is None:
        max_w = max_h = 640
    elif isinstance(max_size, (tuple, list)) and len(max_size) >= 2:
        max_w, max_h = int(max_size[0]), int(max_size[1])
    else:
        try:
            max_w = max_h = int(max_size)
        except (TypeError, ValueError):
            max_w = max_h = 640
    max_w = max(1, max_w)
    max_h = max(1, max_h)
    cell = max(
        1,
        min(max_w // max(1, grid.width), max_h // max(1, grid.height)),
    )
    preview_w = max(1, grid.width * cell)
    preview_h = max(1, grid.height * cell)
    preview = Image.new("RGB", (preview_w, preview_h), (38, 38, 38))
    draw = ImageDraw.Draw(preview)
    checker = (58, 58, 58)
    for y in range(grid.height):
        for x in range(grid.width):
            x0 = x * cell
            y0 = y * cell
            if (x + y) % 2 == 0:
                draw.rectangle((x0, y0, x0 + cell, y0 + cell), fill=checker)
            color = grid.get(x, y)
            if color is None or color[3] <= 0:
                continue
            inset = max(0, cell // 8)
            draw.rectangle(
                (x0 + inset, y0 + inset, x0 + cell - inset, y0 + cell - inset),
                fill=(color[0], color[1], color[2]),
            )
    import io

    buffer = io.BytesIO()
    preview.save(buffer, format="PNG")
    return buffer.getvalue()


SCALED_TRACE_COORDINATE_MODELS = frozenset(
    {
        "forza_painter_text_trace_v1",
        "forza_painter_text_stroke_v1",
        "forza_painter_text_curved_v1",
    }
)


def is_scaled_trace_payload(payload: dict) -> bool:
    model = str(payload.get("coordinate_model", "")).strip().lower()
    if model in SCALED_TRACE_COORDINATE_MODELS:
        return True
    return str(payload.get("format", "")).strip().lower() == "fh6_text_typecode_v1"


def scaled_trace_to_memory_fields(data: Sequence[float | int]) -> dict[str, float]:
    """Map text-vinyl scaled trace coords to FH6 live-layer memory fields."""
    cx, cy, sx, sy = [float(v) for v in data[:4]]
    rotation = float(data[4]) if len(data) >= 5 else 0.0
    skew = float(data[5]) if len(data) > 5 else 0.0
    return {
        "x": cx,
        "y": -cy,
        "sx": sx,
        "sy": sy,
        "rotation": float((360.0 - rotation) % 360.0),
        "skew": skew,
    }


def _rotated_rect_points(cx: float, cy: float, width: float, height: float, degrees: float) -> list[tuple[float, float]]:
    import math

    half_w = float(width) / 2.0
    half_h = float(height) / 2.0
    theta = math.radians(float(degrees))
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    points: list[tuple[float, float]] = []
    for x, y in ((-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h)):
        points.append((cx + x * cos_t - y * sin_t, cy + x * sin_t + y * cos_t))
    return points


def scaled_trace_preview_shapes(payload: dict) -> list[dict]:
    out: list[dict] = []
    for shape in payload.get("shapes") or []:
        if not isinstance(shape, dict):
            continue
        data = list(shape.get("data") or [])
        color = list(shape.get("color") or [])
        if len(data) < 4 or len(color) < 4:
            continue
        try:
            cx, cy, sx, sy = [float(v) for v in data[:4]]
            rotation = float(data[4]) if len(data) >= 5 else 0.0
            rgba = [max(0, min(255, int(round(float(v))))) for v in color[:4]]
        except (TypeError, ValueError):
            continue
        if rgba[3] <= 0:
            continue
        width = max(1.0, sx / SIZE_SCALE)
        height = max(1.0, sy / SIZE_SCALE)
        px = cx / POSITION_SCALE
        py = cy / POSITION_SCALE
        points = _rotated_rect_points(px, py, width, height, rotation)
        try:
            data_mask = bool(int(float(data[6]))) if len(data) >= 7 else False
        except (TypeError, ValueError):
            data_mask = bool(data[6]) if len(data) >= 7 else False
        is_mask = bool(shape.get("mask") or shape.get("is_mask") or shape.get("isMask") or data_mask)
        out.append({"polygons": [points], "color": rgba, "word": 0, "type_code": None, "mask": is_mask})
    return out
