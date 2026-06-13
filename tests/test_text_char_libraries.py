"""Tests for Text vinyl character libraries."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from text.char_libraries import (
    GRID_COLUMNS,
    LIBRARY_HANZI,
    LIBRARY_HANGUL,
    LIBRARY_HIRAGANA,
    LIBRARY_KANJI,
    LIBRARY_KATAKANA,
    LIBRARY_LATIN,
    PAGE_SIZE,
    filter_library,
    filtered_char_count,
    hiragana_library,
    kanji_library,
    latin_extended_library,
    library_chars,
    library_total,
    paginate_chars,
    paginate_library,
)


def test_library_sizes_in_expected_ranges() -> None:
    assert 300 <= len(latin_extended_library()) <= 900
    assert 80 <= len(hiragana_library()) <= 120
    assert 3000 <= len(kanji_library()) <= 7000
    assert library_total(LIBRARY_HANGUL) == 11172
    assert library_total(LIBRARY_HANZI) >= 6000


def test_all_chars_single_codepoint() -> None:
    for library_id in (
        LIBRARY_LATIN,
        LIBRARY_HIRAGANA,
        LIBRARY_KATAKANA,
        LIBRARY_KANJI,
        LIBRARY_HANGUL,
        LIBRARY_HANZI,
    ):
        for char in library_chars(library_id):
            assert len(char) == 1, f"{library_id!r} contains multi-char entry: {char!r}"


def test_filter_finds_known_chars() -> None:
    assert "é" in filter_library(LIBRARY_LATIN, "é")
    assert "あ" in filter_library(LIBRARY_HIRAGANA, "あ")
    assert "ア" in filter_library(LIBRARY_KATAKANA, "ア")
    assert filter_library(LIBRARY_KANJI, "日")
    assert "가" in filter_library(LIBRARY_HANGUL, "가")
    assert "你" in filter_library(LIBRARY_HANZI, "你")


def test_paginate_slice_length() -> None:
    chars = list(library_chars(LIBRARY_LATIN))
    page_chars, page, total_pages = paginate_chars(chars, 0, page_size=PAGE_SIZE)
    assert len(page_chars) <= PAGE_SIZE
    assert page == 0
    assert total_pages >= 1
    last_page, last_index, total_pages = paginate_chars(chars, 999, page_size=PAGE_SIZE)
    assert last_index == total_pages - 1
    assert len(last_page) <= PAGE_SIZE


def test_grid_columns_positive() -> None:
    assert GRID_COLUMNS >= 8


def test_paginate_library_without_full_list() -> None:
    page_chars, page, total_pages = paginate_library(LIBRARY_HANZI, 0, "")
    assert len(page_chars) <= PAGE_SIZE
    assert page == 0
    assert total_pages >= 1
    assert filtered_char_count(LIBRARY_HANZI, "") == library_total(LIBRARY_HANZI)
