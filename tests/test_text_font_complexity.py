"""Tests for benchmark probes used by the Text vinyl tab."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from text_benchmark_probes import (
    CHINESE_BENCHMARK_TEXT,
    CHINESE_GROUND_UP_TEXT,
    JAPANESE_BENCHMARK_EXAMPLES,
    JAPANESE_GROUND_UP_TEXT,
    KOREAN_BENCHMARK_TEXT,
    KOREAN_GROUND_UP_TEXT,
    LATIN_BENCHMARK_EXAMPLES,
    benchmark_texts_for_script,
    primary_benchmark_text,
    random_benchmark_text,
)
from text_fonts import (
    SCRIPT_CHINESE,
    SCRIPT_JAPANESE,
    SCRIPT_KOREAN,
    SCRIPT_UNIVERSAL,
)


def test_japanese_benchmark_examples_include_hololive_names() -> None:
    texts = {example["text"] for example in JAPANESE_BENCHMARK_EXAMPLES}
    assert "エリザベス・ローズ・ブラッドフレイム" in texts
    assert "古石ビジュー" in texts
    assert "小鳥遊キアラ" in texts
    assert "がうる・ぐら" in texts
    assert JAPANESE_GROUND_UP_TEXT in texts
    assert len(JAPANESE_BENCHMARK_EXAMPLES) == 21


def test_benchmark_texts_for_script() -> None:
    assert CHINESE_BENCHMARK_TEXT in benchmark_texts_for_script(SCRIPT_CHINESE)
    assert CHINESE_GROUND_UP_TEXT in benchmark_texts_for_script(SCRIPT_CHINESE)
    assert KOREAN_GROUND_UP_TEXT in benchmark_texts_for_script(SCRIPT_KOREAN)
    assert len(benchmark_texts_for_script(SCRIPT_UNIVERSAL)) == 4
    assert len(benchmark_texts_for_script(SCRIPT_JAPANESE)) == 21
    assert "\n" in primary_benchmark_text(SCRIPT_JAPANESE)


def test_random_benchmark_text_japanese() -> None:
    choices = set(benchmark_texts_for_script(SCRIPT_JAPANESE))
    seen = {random_benchmark_text(SCRIPT_JAPANESE) for _ in range(32)}
    assert seen.issubset(choices)
    assert len(choices) == 21


def test_random_benchmark_text_latin_pool() -> None:
    choices = set(LATIN_BENCHMARK_EXAMPLES)
    seen = {random_benchmark_text(SCRIPT_UNIVERSAL) for _ in range(16)}
    assert seen.issubset(choices)
    assert len(choices) == 4
