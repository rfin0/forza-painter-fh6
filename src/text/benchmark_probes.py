"""Benchmark text probes for font complexity ranking and quick examples."""

from __future__ import annotations

import random
from typing import Sequence, TypedDict

from text.fonts import (
    SCRIPT_CHINESE,
    SCRIPT_JAPANESE,
    SCRIPT_KOREAN,
    SCRIPT_UNIVERSAL,
)

CHINESE_BENCHMARK_TEXT = "我的作物长势良好，灌溉是未来的发展方向。"
CHINESE_GROUND_UP_TEXT = "从零开始打造！"
KOREAN_BENCHMARK_TEXT = "홀로라이브 시계 소녀가 최고예요."
KOREAN_GROUND_UP_TEXT = "처음부터 새로 만들었어요！"
JAPANESE_GROUND_UP_TEXT = "ゼロから構築しました！"

LATIN_BENCHMARK_EXAMPLES: tuple[str, ...] = (
    "F0RZ4-P41N73R",
    "AgMm8@",
    "8U1L7 Phr0M 73H 9R0uNd up!",
    "Built from the ground-up!",
)

# Backward-compatible alias for tests and docs.
LATIN_BENCHMARK_TEXT = LATIN_BENCHMARK_EXAMPLES[0]


class JapaneseBenchmarkExample(TypedDict):
    label: str
    text: str


JAPANESE_BENCHMARK_EXAMPLES: tuple[JapaneseBenchmarkExample, ...] = (
    {"label": "Mori Calliope", "text": "森カリオペ"},
    {"label": "Takanashi Kiara", "text": "小鳥遊キアラ"},
    {"label": "Ninomae Ina'nis", "text": "一伊那尓栖"},
    {"label": "Watson Amelia", "text": "ワトソン・アメリア"},
    {"label": "IRyS", "text": "IRyS"},
    {"label": "Ouro Kronii", "text": "オーロ・クロニー"},
    {"label": "Hakos Baelz", "text": "ハコス・ベールズ"},
    {"label": "Shiori Novella", "text": "シオリ・ノヴェラ"},
    {"label": "Koseki Bijou", "text": "古石ビジュー"},
    {"label": "Nerissa Ravencroft", "text": "ネリッサ・レイヴンクロフト"},
    {"label": "Fuwawa Abyssgard", "text": "フワワ・アビスガード"},
    {"label": "Mococo Abyssgard", "text": "モココ・アビスガード"},
    {"label": "Elizabeth Rose Bloodflame", "text": "エリザベス・ローズ・ブラッドフレイム"},
    {"label": "Gigi Murin", "text": "ジジ・ムリン"},
    {"label": "Cecilia Immergreen", "text": "セシリア・イマーグリーン"},
    {"label": "Raora Panthera", "text": "ラオーラ・パンテーラ"},
    {"label": "Gawr Gura", "text": "がうる・ぐら"},
    {"label": "Tsukumo Sana", "text": "九十九佐命"},
    {"label": "Ceres Fauna", "text": "セレス・ファウナ"},
    {"label": "Nanashi Mumei", "text": "七詩ムメイ"},
    {"label": "Ground up", "text": JAPANESE_GROUND_UP_TEXT},
)

CHINESE_BENCHMARK_EXAMPLES: tuple[str, ...] = (
    CHINESE_BENCHMARK_TEXT,
    CHINESE_GROUND_UP_TEXT,
)

KOREAN_BENCHMARK_EXAMPLES: tuple[str, ...] = (
    KOREAN_BENCHMARK_TEXT,
    KOREAN_GROUND_UP_TEXT,
)

TEXT_BENCHMARK_PROBES: dict[str, str] = {
    SCRIPT_CHINESE: CHINESE_BENCHMARK_TEXT,
    SCRIPT_KOREAN: KOREAN_BENCHMARK_TEXT,
    SCRIPT_UNIVERSAL: "\n".join(LATIN_BENCHMARK_EXAMPLES),
    SCRIPT_JAPANESE: "\n".join(example["text"] for example in JAPANESE_BENCHMARK_EXAMPLES),
}


def benchmark_texts_for_script(script: str) -> tuple[str, ...]:
    """Return one or more probe strings used to score font complexity for *script*."""
    if script == SCRIPT_JAPANESE:
        return tuple(example["text"] for example in JAPANESE_BENCHMARK_EXAMPLES)
    if script == SCRIPT_UNIVERSAL:
        return LATIN_BENCHMARK_EXAMPLES
    if script == SCRIPT_CHINESE:
        return CHINESE_BENCHMARK_EXAMPLES
    if script == SCRIPT_KOREAN:
        return KOREAN_BENCHMARK_EXAMPLES
    probe = TEXT_BENCHMARK_PROBES.get(script)
    if not probe:
        return ()
    return (probe,)


def primary_benchmark_text(script: str) -> str:
    """Default combined probe text for a script (used internally, not shown in UI)."""
    return TEXT_BENCHMARK_PROBES.get(script, "")


def random_benchmark_text(script: str) -> str:
    """Pick a random benchmark string for *script* (single choice for most tabs)."""
    choices = benchmark_texts_for_script(script)
    if not choices:
        return ""
    return random.choice(tuple(choices))


def japanese_benchmark_examples() -> Sequence[JapaneseBenchmarkExample]:
    return JAPANESE_BENCHMARK_EXAMPLES
