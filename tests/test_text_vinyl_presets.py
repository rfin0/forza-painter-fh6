"""Text vinyl preset definitions aligned with bvzrays import defaults."""

from text_geometry import SHAPE_MODE_ELLIPSES, SHAPE_MODE_RECTANGLES
from text_vinyl_presets import (
    CJK_DEFAULT_PRESET_ID,
    DEFAULT_MAX_DRAWABLE_LAYERS,
    UI_PRESET_ORDER,
    get_preset,
    normalize_preset_id,
)


def test_ui_preset_order_excludes_removed_presets() -> None:
    assert "sharp_cjk" not in UI_PRESET_ORDER
    assert "forza_latin" not in UI_PRESET_ORDER
    assert UI_PRESET_ORDER[0] == "custom"
    assert CJK_DEFAULT_PRESET_ID in UI_PRESET_ORDER


def test_normalize_preset_id_migrates_legacy_ids() -> None:
    assert normalize_preset_id("sharp_cjk") == CJK_DEFAULT_PRESET_ID
    assert normalize_preset_id("forza_latin") == "custom"
    assert normalize_preset_id("efficient_cjk") == "efficient_cjk"
    assert normalize_preset_id("unknown") == "custom"


def test_cjk_presets_fit_layer_budget_and_cap_layers() -> None:
    for preset_id in ("efficient_cjk", "soft_cjk", "smooth_cjk_extra"):
        preset = get_preset(preset_id)
        assert preset.fit_layer_budget is True
        assert preset.max_drawable_layers == DEFAULT_MAX_DRAWABLE_LAYERS


def test_efficient_cjk_uses_rectangles() -> None:
    preset = get_preset("efficient_cjk")
    assert preset.shape_mode == SHAPE_MODE_RECTANGLES
    assert preset.cell_size == 6


def test_soft_cjk_uses_ellipses() -> None:
    preset = get_preset("soft_cjk")
    assert preset.shape_mode == SHAPE_MODE_ELLIPSES
    assert preset.cell_size == 3


def test_smooth_cjk_extra_enables_extra_shapes() -> None:
    preset = get_preset("smooth_cjk_extra")
    assert preset.extra_shapes is True
    assert preset.shape_mode == SHAPE_MODE_RECTANGLES
    assert preset.cell_size == 2
