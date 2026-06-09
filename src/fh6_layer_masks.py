"""FH6 vinyl layer masks: boundary bounds, polish overflow clipping, shared helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from pixel_art_geometry import FH6_BOUNDARY_LAYERS
from security_policy import MAX_GEOMETRY_SHAPES

Rect = Tuple[int, int, int, int]
MASK_COLOR = (0, 0, 0, 255)
MASK_ROLE_BOUNDARY = "boundary"
MASK_ROLE_POLISH = "polish"


@dataclass(frozen=True)
class TextMaskOptions:
    include_boundary_masks: bool = False
    include_polish_masks: bool = False
    polish_cell_size: int = 4
    polish_margin: int = 0
    max_drawable_layers: int | None = None

    def reserved_mask_layers(self, *, polish_count: int = 0) -> int:
        total = 0
        if self.include_polish_masks:
            total += max(0, int(polish_count))
        if self.include_boundary_masks:
            total += FH6_BOUNDARY_LAYERS
        return total


def is_fh6_mask_shape(shape: dict) -> bool:
    if not isinstance(shape, dict):
        return False
    for key in ("mask", "is_mask", "isMask"):
        if key in shape and bool(shape.get(key)):
            return True
    data = shape.get("data") or []
    if len(data) > 6:
        try:
            return bool(int(float(data[6])))
        except (TypeError, ValueError):
            return bool(data[6])
    return False


def shape_mask_enabled(shape: dict) -> bool:
    if "mask_enabled" in shape:
        return bool(shape.get("mask_enabled"))
    return is_fh6_mask_shape(shape)


def shape_mask_role(shape: dict) -> str | None:
    role = shape.get("mask_role")
    if isinstance(role, str) and role:
        return role
    if is_fh6_mask_shape(shape):
        return MASK_ROLE_POLISH
    return None


def boundary_mask_center_specs(image_width: int, image_height: int) -> List[Tuple[int, int, float, float]]:
    """Legacy center/size specs matching main.py FH6 save-bounds masks."""
    w = int(image_width)
    h = int(image_height)
    return [
        (-w // 4, h // 2, float(w // 2), float(h * 1.5)),
        (w + w // 4, h // 2, float(w // 2), float(h * 1.5)),
        (w // 2, -h // 4, float(w + w), float(h // 2)),
        (w // 2, h + h // 4, float(w + w), float(h // 2)),
    ]


def make_fh6_mask_shape(
    x0: int,
    y0: int,
    width: int,
    height: int,
    *,
    mask_role: str = MASK_ROLE_POLISH,
) -> dict:
    from text_geometry import SHAPE_MODE_RECTANGLES, _rect_to_typecode_shape

    shape = _rect_to_typecode_shape(x0, y0, width, height, MASK_COLOR, SHAPE_MODE_RECTANGLES)
    shape["mask"] = True
    shape["data"][6] = 1
    shape["mask_role"] = mask_role
    shape["mask_enabled"] = True
    return shape


def build_boundary_mask_shapes(image_width: int, image_height: int) -> List[dict]:
    shapes: List[dict] = []
    for cx, cy, bw, bh in boundary_mask_center_specs(image_width, image_height):
        x0 = int(round(cx - bw / 2.0))
        y0 = int(round(cy - bh / 2.0))
        shapes.append(
            make_fh6_mask_shape(x0, y0, int(bw), int(bh), mask_role=MASK_ROLE_BOUNDARY)
        )
    return shapes


def partition_payload_shapes(shapes: Sequence[dict]) -> tuple[List[dict], List[dict]]:
    drawables: List[dict] = []
    masks: List[dict] = []
    for shape in shapes:
        if is_fh6_mask_shape(shape):
            masks.append(shape)
        else:
            drawables.append(shape)
    return drawables, masks


def summarize_payload_layers(payload: dict) -> dict:
    shapes = list(payload.get("shapes") or [])
    meta = payload.get("mask_metadata") if isinstance(payload.get("mask_metadata"), dict) else {}
    drawables, masks = partition_payload_shapes(shapes)
    polish = sum(1 for shape in masks if shape_mask_role(shape) == MASK_ROLE_POLISH and shape_mask_enabled(shape))
    boundary = sum(
        1 for shape in masks if shape_mask_role(shape) == MASK_ROLE_BOUNDARY and shape_mask_enabled(shape)
    )
    disabled_masks = sum(1 for shape in masks if not shape_mask_enabled(shape))
    return {
        "drawable_count": int(meta.get("drawable_count", len(drawables))),
        "polish_mask_count": int(meta.get("polish_mask_count", polish)),
        "boundary_mask_count": int(meta.get("boundary_mask_count", boundary)),
        "disabled_mask_count": disabled_masks,
        "total_layers": len(shapes),
        "has_masks": bool(masks),
    }


def append_text_masks_to_payload(
    payload: dict,
    ideal_mask,
    *,
    trace_rectangles: Sequence[Rect] | None,
    options: TextMaskOptions,
) -> dict:
    """Append polish and boundary masks; trim drawables to respect layer budget."""
    drawables, existing_masks = partition_payload_shapes(list(payload.get("shapes") or []))
    width, height = ideal_mask.size

    polish_shapes: List[dict] = []
    if options.include_polish_masks and trace_rectangles:
        from text_mask_polish import build_polish_mask_shapes

        polish_shapes = build_polish_mask_shapes(
            ideal_mask,
            trace_rectangles,
            polish_cell_size=options.polish_cell_size,
            margin=options.polish_margin,
        )

    boundary_shapes: List[dict] = []
    if options.include_boundary_masks:
        boundary_shapes = build_boundary_mask_shapes(width, height)

    reserved = len(polish_shapes) + len(boundary_shapes)
    max_drawables = MAX_GEOMETRY_SHAPES - reserved
    if options.max_drawable_layers is not None:
        max_drawables = min(max_drawables, max(1, int(options.max_drawable_layers)))

    if len(drawables) > max_drawables:
        drawables = drawables[:max_drawables]

    masks = polish_shapes + boundary_shapes + [shape for shape in existing_masks if shape not in polish_shapes]
    updated = dict(payload)
    updated["shapes"] = drawables + masks
    updated["mask_metadata"] = {
        "drawable_count": len(drawables),
        "polish_mask_count": len(polish_shapes),
        "boundary_mask_count": len(boundary_shapes),
        "polish_enabled": options.include_polish_masks,
        "boundary_enabled": options.include_boundary_masks,
    }
    return updated


def polish_supported_for_shape_mode(
    shape_mode: str,
    *,
    extra_shapes: bool = False,
    trace_method: str | None = None,
    allow_overlapping_shapes: bool = False,
) -> bool:
    from text_geometry import resolve_text_trace_pipeline

    _method, uses_strokes, _prefer_skeleton = resolve_text_trace_pipeline(
        trace_method=trace_method,
        shape_mode=shape_mode,
        allow_overlapping_shapes=allow_overlapping_shapes,
        extra_shapes=extra_shapes,
    )
    if extra_shapes or uses_strokes:
        return False
    return True
