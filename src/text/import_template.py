"""FH6 import template shape detection for text vinyl JSON."""

from __future__ import annotations

from typing import Any

SHAPE_BYTE_SQUARE = 101
SHAPE_BYTE_CIRCLE = 102

_TEMPLATE_MATCH_RATIO = 0.90

_SHAPE_MODE_RECTANGLES = "rectangles"
_SHAPE_MODE_SQUARES = "squares"
_SHAPE_MODE_ELLIPSES = "ellipses"
_SHAPE_MODE_CIRCLES = "circles"
_SHAPE_MODE_TRIANGLES = "triangles"
_SHAPE_MODE_MIXED = "mixed"
_SHAPE_MODE_STROKES = "strokes"

_TRACE_METHOD_BARS_FULL = "bars_full"
_TRACE_METHOD_BARS_SKELETON = "bars_skeleton"


def _parse_shape_type_code(shape: dict[str, Any]) -> int | None:
    raw = shape.get("type")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def type_code_to_template_shape_byte(type_code: int) -> int:
    """Map a FH6 vinyl type code to the in-game template layer shape byte."""
    from fh6_shape_catalog import get_primitive_type_code, get_square_type_code

    square_code = int(get_square_type_code(allow_fallback=True))
    if int(type_code) == square_code:
        return SHAPE_BYTE_SQUARE
    circle_code = get_primitive_type_code("Circle", allow_fallback=True)
    if circle_code is not None and int(type_code) == int(circle_code):
        return SHAPE_BYTE_CIRCLE
    ellipse_code = get_primitive_type_code("Ellipse", allow_fallback=True)
    if ellipse_code is not None and int(type_code) == int(ellipse_code):
        return SHAPE_BYTE_CIRCLE
    return SHAPE_BYTE_CIRCLE


def dominant_template_shape_byte(payload: dict[str, Any]) -> int:
    """Pick square vs circle template from the dominant primitive in JSON shapes."""
    counts = {SHAPE_BYTE_SQUARE: 0, SHAPE_BYTE_CIRCLE: 0}
    for shape in payload.get("shapes") or []:
        if not isinstance(shape, dict):
            continue
        type_code = _parse_shape_type_code(shape)
        if type_code is None:
            continue
        byte = type_code_to_template_shape_byte(type_code)
        counts[byte] = counts.get(byte, 0) + 1
    if counts[SHAPE_BYTE_SQUARE] >= counts[SHAPE_BYTE_CIRCLE]:
        return SHAPE_BYTE_SQUARE if counts[SHAPE_BYTE_SQUARE] > 0 else SHAPE_BYTE_CIRCLE
    return SHAPE_BYTE_CIRCLE


def template_shape_byte_for_generation(
    shape_mode: str,
    *,
    extra_shapes: bool = False,
    trace_method: str | None = None,
) -> int:
    """Return the FH6 template shape byte users should prepare before import."""
    from text.geometry import normalize_text_shape_mode, normalize_text_trace_method

    if extra_shapes:
        return SHAPE_BYTE_CIRCLE
    mode = normalize_text_shape_mode(shape_mode)
    method = normalize_text_trace_method(trace_method)
    if method in (_TRACE_METHOD_BARS_FULL, _TRACE_METHOD_BARS_SKELETON):
        return SHAPE_BYTE_SQUARE
    if mode in (_SHAPE_MODE_RECTANGLES, _SHAPE_MODE_SQUARES, _SHAPE_MODE_STROKES):
        return SHAPE_BYTE_SQUARE
    if mode in (_SHAPE_MODE_ELLIPSES, _SHAPE_MODE_CIRCLES, _SHAPE_MODE_TRIANGLES, _SHAPE_MODE_MIXED):
        return SHAPE_BYTE_CIRCLE
    return SHAPE_BYTE_SQUARE


def required_template_shape_byte(payload: dict[str, Any]) -> int:
    """Shape byte encoded in JSON metadata for hints; import still uses circle templates."""
    meta = payload.get("text_generation")
    if isinstance(meta, dict) and meta.get("shape_mode"):
        return template_shape_byte_for_generation(
            str(meta.get("shape_mode")),
            extra_shapes=bool(meta.get("extra_shapes")),
            trace_method=meta.get("trace_method"),
        )
    return dominant_template_shape_byte(payload)


def attach_text_generation_metadata(
    payload: dict[str, Any],
    *,
    shape_mode: str,
    trace_method: str | None = None,
    extra_shapes: bool = False,
) -> dict[str, Any]:
    """Record generation options on the JSON for import routing and UI hints."""
    from text.geometry import normalize_text_shape_mode, normalize_text_trace_method

    payload = dict(payload)
    payload["text_generation"] = {
        "shape_mode": normalize_text_shape_mode(shape_mode),
        "trace_method": normalize_text_trace_method(trace_method),
        "extra_shapes": bool(extra_shapes),
        "template_shape_byte": template_shape_byte_for_generation(
            shape_mode,
            extra_shapes=extra_shapes,
            trace_method=trace_method,
        ),
    }
    return payload


def template_match_ratio() -> float:
    return _TEMPLATE_MATCH_RATIO


def template_shape_label(shape_byte: int) -> str:
    if int(shape_byte) == SHAPE_BYTE_SQUARE:
        return "square"
    return "circle"


def uses_square_template(shape_mode: str, *, extra_shapes: bool = False, trace_method: str | None = None) -> bool:
    return (
        template_shape_byte_for_generation(shape_mode, extra_shapes=extra_shapes, trace_method=trace_method)
        == SHAPE_BYTE_SQUARE
    )
