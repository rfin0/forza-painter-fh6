"""Character libraries for Text vinyl grid pickers (generated at runtime)."""

from __future__ import annotations

import functools
from typing import List, Tuple

from text.mandarin_chars import mandarin_character_library

LIBRARY_LATIN = "latin_extended"
LIBRARY_HIRAGANA = "hiragana"
LIBRARY_KATAKANA = "katakana"
LIBRARY_KANJI = "kanji"
LIBRARY_HANGUL = "hangul"
LIBRARY_HANZI = "hanzi"

LIBRARY_IDS = (
    LIBRARY_LATIN,
    LIBRARY_HIRAGANA,
    LIBRARY_KATAKANA,
    LIBRARY_KANJI,
    LIBRARY_HANGUL,
    LIBRARY_HANZI,
)

PAGE_SIZE = 256
GRID_COLUMNS = 16

# Symbols often used beside Latin vinyl text.
_LATIN_EXTRA = "©®™°±×÷€£¥¢§¶†‡•…—–‚„""''«»‹›¡¿¨´¸¹³²¼½¾"


def _chars_in_ranges(ranges: List[Tuple[int, int]], *, predicate=None) -> str:
    out: List[str] = []
    seen = set()
    for start, end in ranges:
        for code in range(start, end + 1):
            char = chr(code)
            if char in seen:
                continue
            if predicate is not None and not predicate(char):
                continue
            if not char.isprintable():
                continue
            seen.add(char)
            out.append(char)
    return "".join(out)


def _is_kanji_char(char: str) -> bool:
    code = ord(char)
    if 0x4E00 <= code <= 0x9FFF:
        return True
    if 0x3400 <= code <= 0x4DBF:
        return True
    return False


def _is_kana_char(char: str) -> bool:
    code = ord(char)
    return 0x3040 <= code <= 0x30FF or 0xFF66 <= code <= 0xFF9F


@functools.lru_cache(maxsize=1)
def latin_extended_library() -> str:
    """Latin accented letters and common Western symbols."""
    ranges = [
        (0x00A1, 0x00FF),  # Latin-1 Supplement
        (0x0100, 0x017F),  # Latin Extended-A
        (0x0180, 0x024F),  # Latin Extended-B (partial)
    ]
    base = _chars_in_ranges(
        ranges,
        predicate=lambda c: c.isalpha() or c in _LATIN_EXTRA or (not c.isspace() and ord(c) < 0x0300),
    )
    extras = [c for c in _LATIN_EXTRA if c not in base]
    return base + "".join(extras)


@functools.lru_cache(maxsize=1)
def hiragana_library() -> str:
    chars = [chr(c) for c in range(0x3041, 0x3097)]
    for extra in "ゝゞ・ー":
        if extra not in chars:
            chars.append(extra)
    return "".join(chars)


@functools.lru_cache(maxsize=1)
def katakana_library() -> str:
    chars = [chr(c) for c in range(0x30A1, 0x30FA)]
    for extra in "ヽヾ・ー":
        if extra not in chars:
            chars.append(extra)
    for code in range(0xFF66, 0xFFA0):
        char = chr(code)
        if char.isprintable():
            chars.append(char)
    return "".join(chars)


@functools.lru_cache(maxsize=1)
def shift_jis_kanji_chars() -> str:
    """JIS X 0208-style kanji via Shift_JIS decode (excludes kana)."""
    seen = set()
    ordered: List[str] = []

    def add_pair(b1: int, b2: int) -> None:
        if b2 == 0x7F:
            return
        try:
            char = bytes([b1, b2]).decode("shift_jis")
        except UnicodeDecodeError:
            return
        if len(char) != 1:
            return
        if not _is_kanji_char(char) or _is_kana_char(char):
            return
        if char in seen:
            return
        seen.add(char)
        ordered.append(char)

    for b1 in range(0x81, 0xA0):
        for b2 in range(0x40, 0xFD):
            add_pair(b1, b2)
    for b1 in range(0xE0, 0xF0):
        for b2 in range(0x40, 0xFD):
            add_pair(b1, b2)
    return "".join(ordered)


@functools.lru_cache(maxsize=1)
def kanji_library() -> str:
    """Joyō-scale kanji set: Shift_JIS JIS kanji block, sorted by code point."""
    return shift_jis_kanji_chars()


@functools.lru_cache(maxsize=1)
def hangul_library() -> str:
    return "".join(chr(c) for c in range(0xAC00, 0xD7A4))


@functools.lru_cache(maxsize=1)
def hanzi_library() -> str:
    return mandarin_character_library()


def library_chars(library_id: str) -> str:
    builders = {
        LIBRARY_LATIN: latin_extended_library,
        LIBRARY_HIRAGANA: hiragana_library,
        LIBRARY_KATAKANA: katakana_library,
        LIBRARY_KANJI: kanji_library,
        LIBRARY_HANGUL: hangul_library,
        LIBRARY_HANZI: hanzi_library,
    }
    builder = builders.get(library_id)
    if builder is None:
        raise ValueError(f"Unknown character library: {library_id}")
    return builder()


def library_total(library_id: str) -> int:
    return len(library_chars(library_id))


def filtered_char_count(library_id: str, query: str) -> int:
    """Character count after search filter (without materializing the full library)."""
    library = library_chars(library_id)
    query = (query or "").strip()
    if not query:
        return len(library)
    if len(query) == 1 and query in library:
        return 1
    return sum(1 for char in library if query in char)


def filter_library(library_id: str, query: str) -> List[str]:
    """Return matching characters in library order (list for pagination)."""
    library = library_chars(library_id)
    query = (query or "").strip()
    if not query:
        return list(library)
    if len(query) == 1 and query in library:
        return [query]
    return [char for char in library if query in char]


def paginate_library(
    library_id: str,
    page: int,
    query: str = "",
    *,
    page_size: int = PAGE_SIZE,
) -> Tuple[List[str], int, int]:
    """Return one page of characters without building a full list when the search is empty."""
    library = library_chars(library_id)
    query = (query or "").strip()
    if not query:
        total = len(library)
        if total <= 0:
            return [], 0, 1
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(0, min(page, total_pages - 1))
        start = page * page_size
        return list(library[start : start + page_size]), page, total_pages
    filtered = filter_library(library_id, query)
    return paginate_chars(filtered, page, page_size=page_size)


def paginate_chars(
    chars: List[str],
    page: int,
    *,
    page_size: int = PAGE_SIZE,
) -> Tuple[List[str], int, int]:
    if not chars:
        return [], 0, 1
    total_pages = max(1, (len(chars) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    return chars[start : start + page_size], page, total_pages
