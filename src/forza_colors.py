"""
Forza vinyl editor color conversions.

RGB/HSB/HSL/hex conversions match Bang's Forza Color Converter (fcc.js):
https://dxbang.github.io/forza-colors/
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class RgbColor:
    r: int
    g: int
    b: int

    def clamped(self) -> "RgbColor":
        return RgbColor(
            max(0, min(255, int(self.r))),
            max(0, min(255, int(self.g))),
            max(0, min(255, int(self.b))),
        )


@dataclass(frozen=True)
class ColorFormats:
    hex: str
    rgb: RgbColor
    hsl_h: float
    hsl_s: float
    hsl_l: float
    hsb_h: float
    hsb_s: float
    hsb_b: float
    forza_h: float
    forza_s: float
    forza_b: float


def rgb_to_hex(r: int, g: int, b: int) -> str:
    rgb = RgbColor(r, g, b).clamped()
    return f"#{rgb.r:02x}{rgb.g:02x}{rgb.b:02x}"


def hex_to_rgb(hex_value: str) -> RgbColor | None:
    text = (hex_value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return None
    try:
        return RgbColor(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return None


def rgb_to_hsl(r: int, g: int, b: int) -> Tuple[float, float, float]:
    r, g, b = (r / 255.0, g / 255.0, b / 255.0)
    light = max(r, g, b)
    sat = light - min(r, g, b)
    if sat:
        if light == r:
            hue = (g - b) / sat
        elif light == g:
            hue = 2 + (b - r) / sat
        else:
            hue = 4 + (r - g) / sat
    else:
        hue = 0.0
    h = 60 * hue
    if h < 0:
        h += 360
    if sat:
        s = 100 * (sat / (2 * light - sat) if light <= 0.5 else sat / (2 - (2 * light - sat)))
    else:
        s = 0.0
    l = (100 * (2 * light - sat)) / 2
    return h, s, l


def rgb_to_hsb(r: int, g: int, b: int) -> Tuple[float, float, float]:
    r, g, b = (r / 255.0, g / 255.0, b / 255.0)
    value = max(r, g, b)
    delta = value - min(r, g, b)
    if delta == 0:
        hue = 0.0
    elif value == r:
        hue = (g - b) / delta
    elif value == g:
        hue = 2 + (b - r) / delta
    else:
        hue = 4 + (r - g) / delta
    h = 60 * (hue + 6 if hue < 0 else hue)
    s = (delta / value) * 100 if value else 0.0
    return h, s, value * 100


def rgb_to_forza_hsb(r: int, g: int, b: int) -> Tuple[float, float, float]:
    """Forza editor H/S/B (hue 0–1, saturation and brightness 0–1)."""
    r, g, b = (r / 255.0, g / 255.0, b / 255.0)
    value = max(r, g, b)
    delta = value - min(r, g, b)
    if delta == 0:
        hue = 0.0
    elif value == r:
        hue = (g - b) / delta
    elif value == g:
        hue = 2 + (b - r) / delta
    else:
        hue = 4 + (r - g) / delta
    h = (60 * (hue + 6 if hue < 0 else hue)) / 360.0
    s = (delta / value) if value else 0.0
    return h, s, value


def describe_color(r: int, g: int, b: int) -> ColorFormats:
    rgb = RgbColor(r, g, b).clamped()
    hsl_h, hsl_s, hsl_l = rgb_to_hsl(rgb.r, rgb.g, rgb.b)
    hsb_h, hsb_s, hsb_b = rgb_to_hsb(rgb.r, rgb.g, rgb.b)
    forza_h, forza_s, forza_b = rgb_to_forza_hsb(rgb.r, rgb.g, rgb.b)
    return ColorFormats(
        hex=rgb_to_hex(rgb.r, rgb.g, rgb.b),
        rgb=rgb,
        hsl_h=hsl_h,
        hsl_s=hsl_s,
        hsl_l=hsl_l,
        hsb_h=hsb_h,
        hsb_s=hsb_s,
        hsb_b=hsb_b,
        forza_h=forza_h,
        forza_s=forza_s,
        forza_b=forza_b,
    )


def average_rgb(samples) -> RgbColor | None:
    if not samples:
        return None
    total_r = total_g = total_b = 0
    for r, g, b in samples:
        total_r += r
        total_g += g
        total_b += b
    count = len(samples)
    return RgbColor(total_r // count, total_g // count, total_b // count)
