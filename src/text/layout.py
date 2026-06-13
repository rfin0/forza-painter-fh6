"""Writing direction and layout options for text vinyl rasterization."""

from __future__ import annotations

from dataclasses import dataclass

WRITING_MODE_HORIZONTAL_LTR = "horizontal-ltr"
WRITING_MODE_HORIZONTAL_RTL = "horizontal-rtl"
WRITING_MODE_VERTICAL_T2B = "vertical-t2b"
WRITING_MODE_VERTICAL_T2B_RTL = "vertical-t2b-columns-rtl"

WRITING_MODES = (
    WRITING_MODE_HORIZONTAL_LTR,
    WRITING_MODE_HORIZONTAL_RTL,
    WRITING_MODE_VERTICAL_T2B,
    WRITING_MODE_VERTICAL_T2B_RTL,
)

DEFAULT_WRITING_MODE = WRITING_MODE_HORIZONTAL_LTR


@dataclass(frozen=True)
class TextLayoutOptions:
    writing_mode: str = DEFAULT_WRITING_MODE
    line_spacing: float = 1.2
    column_spacing: float = 1.15

    def __post_init__(self) -> None:
        if self.writing_mode not in WRITING_MODES:
            raise ValueError(f"Unsupported writing mode: {self.writing_mode!r}")

    @property
    def is_vertical(self) -> bool:
        return self.writing_mode in (
            WRITING_MODE_VERTICAL_T2B,
            WRITING_MODE_VERTICAL_T2B_RTL,
        )

    @property
    def columns_rtl(self) -> bool:
        return self.writing_mode == WRITING_MODE_VERTICAL_T2B_RTL


def default_writing_mode_for_script(script: str) -> str:
    return DEFAULT_WRITING_MODE


def normalize_writing_mode(value: str | None, *, script: str | None = None) -> str:
    mode = (value or "").strip()
    if mode in WRITING_MODES:
        return mode
    if script:
        return default_writing_mode_for_script(script)
    return DEFAULT_WRITING_MODE


def layout_options_from_writing_mode(
    writing_mode: str | None,
    *,
    script: str | None = None,
) -> TextLayoutOptions:
    return TextLayoutOptions(writing_mode=normalize_writing_mode(writing_mode, script=script))
