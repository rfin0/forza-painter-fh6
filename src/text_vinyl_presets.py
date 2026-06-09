"""Named presets for Text vinyl generation options (bvzrays import-friendly defaults)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from text_geometry import (
    SHAPE_MODE_ELLIPSES,
    SHAPE_MODE_RECTANGLES,
)

# Matches the Import tab default; keeps generated JSON within a practical FH6 template size.
DEFAULT_MAX_DRAWABLE_LAYERS = 1800

# Presets exposed in the Text tab combo (legacy / hidden ids omitted).
UI_PRESET_ORDER: List[str] = [
    "custom",
    "efficient_cjk",
    "soft_cjk",
    "smooth_cjk_extra",
]

CJK_DEFAULT_PRESET_ID = "efficient_cjk"


@dataclass(frozen=True)
class TextVinylPreset:
    id: str
    label_key: str
    shape_mode: str
    cell_size: int
    use_forza_font: bool = False
    forza_font_index: int = 1
    fit_layer_budget: bool = False
    extra_shapes: bool = False
    max_drawable_layers: int | None = None


TEXT_VINYL_PRESETS: Dict[str, TextVinylPreset] = {
    "custom": TextVinylPreset(
        id="custom",
        label_key="text_preset_custom",
        shape_mode=SHAPE_MODE_RECTANGLES,
        cell_size=1,
    ),
    "efficient_cjk": TextVinylPreset(
        id="efficient_cjk",
        label_key="text_preset_efficient_cjk",
        shape_mode=SHAPE_MODE_RECTANGLES,
        cell_size=6,
        fit_layer_budget=True,
        max_drawable_layers=DEFAULT_MAX_DRAWABLE_LAYERS,
    ),
    "soft_cjk": TextVinylPreset(
        id="soft_cjk",
        label_key="text_preset_soft_cjk",
        shape_mode=SHAPE_MODE_ELLIPSES,
        cell_size=3,
        fit_layer_budget=True,
        max_drawable_layers=DEFAULT_MAX_DRAWABLE_LAYERS,
    ),
    "smooth_cjk_extra": TextVinylPreset(
        id="smooth_cjk_extra",
        label_key="text_preset_smooth_cjk_extra",
        shape_mode=SHAPE_MODE_RECTANGLES,
        cell_size=2,
        fit_layer_budget=True,
        extra_shapes=True,
        max_drawable_layers=DEFAULT_MAX_DRAWABLE_LAYERS,
    ),
    # Legacy ids kept for stale UI state / old JSON; not shown in the preset combo.
    "forza_latin": TextVinylPreset(
        id="forza_latin",
        label_key="text_preset_custom",
        shape_mode=SHAPE_MODE_RECTANGLES,
        cell_size=1,
    ),
    "sharp_cjk": TextVinylPreset(
        id="sharp_cjk",
        label_key="text_preset_efficient_cjk",
        shape_mode=SHAPE_MODE_RECTANGLES,
        cell_size=6,
        fit_layer_budget=True,
        max_drawable_layers=DEFAULT_MAX_DRAWABLE_LAYERS,
    ),
}

PRESET_ORDER = UI_PRESET_ORDER


def normalize_preset_id(preset_id: str) -> str:
    """Map removed presets to supported defaults."""
    if preset_id == "sharp_cjk":
        return CJK_DEFAULT_PRESET_ID
    if preset_id == "forza_latin":
        return "custom"
    if preset_id in TEXT_VINYL_PRESETS:
        return preset_id
    return "custom"


def get_preset(preset_id: str) -> TextVinylPreset:
    return TEXT_VINYL_PRESETS.get(normalize_preset_id(preset_id)) or TEXT_VINYL_PRESETS["custom"]
