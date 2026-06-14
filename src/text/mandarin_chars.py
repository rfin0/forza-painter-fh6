"""
GB2312 Level-1 hanzi and helpers for the Text vinyl character library.

Level 1 is the standard 3755 simplified Chinese characters used in mainland
publishing and input methods. The set is generated at runtime so we do not
ship a multi-megabyte glyph table.
"""

from __future__ import annotations

import functools
import re
from typing import Iterable, List, Set, Tuple

# Punctuation and symbols often used beside hanzi in vinyl text.
MANDARIN_EXTRA_CHARS = "，。！？、；：""''（）【】《》…—·0123456789"

# Hiragana/Katakana, CJK ideographs, halfwidth kana, and Hangul (Jamo + syllables).
_CJK_RE = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f"
    r"\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]"
)
_HANGUL_RE = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]")


@functools.lru_cache(maxsize=1)
def gb2312_level1_chars() -> str:
    """Return all 3755 GB2312 Level-1 hanzi in Unicode code-point order."""
    chars: List[str] = []
    for byte1 in range(0xB0, 0xD8):
        for byte2 in range(0xA1, 0xFF):
            try:
                chars.append(bytes([byte1, byte2]).decode("gb2312"))
            except UnicodeDecodeError:
                continue
    return "".join(chars)


@functools.lru_cache(maxsize=1)
def gb2312_hanzi_chars() -> str:
    """Return all 6763 GB2312 hanzi (Level 1 + Level 2)."""
    chars: List[str] = []
    for byte1 in range(0xB0, 0xF8):
        for byte2 in range(0xA1, 0xFF):
            try:
                chars.append(bytes([byte1, byte2]).decode("gb2312"))
            except UnicodeDecodeError:
                continue
    return "".join(chars)


@functools.lru_cache(maxsize=1)
def mandarin_character_library() -> str:
    """Hanzi library plus common punctuation for the in-app picker."""
    return gb2312_hanzi_chars() + MANDARIN_EXTRA_CHARS


def is_cjk_char(char: str) -> bool:
    return len(char) == 1 and bool(_CJK_RE.fullmatch(char))


def is_hangul_char(char: str) -> bool:
    return len(char) == 1 and bool(_HANGUL_RE.fullmatch(char))


def text_contains_hangul(text: str) -> bool:
    return any(is_hangul_char(char) for char in text)


def text_scripts(text: str) -> Tuple[str, ...]:
    """Return coarse script tags present in text: sc, tc, jp, kr."""
    tags: List[str] = []
    for char in text:
        if not is_cjk_char(char):
            continue
        if is_hangul_char(char):
            if "kr" not in tags:
                tags.append("kr")
            continue
        code = ord(char)
        if 0x3040 <= code <= 0x30FF or 0xFF66 <= code <= 0xFF9F:
            if "jp" not in tags:
                tags.append("jp")
        elif 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
            # Han — may be SC/TC/JP; treat as generic CJK for font picking.
            if "sc" not in tags:
                tags.append("sc")
    return tuple(tags)


def unique_chars(text: str) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for char in text:
        if char in seen:
            continue
        seen.add(char)
        ordered.append(char)
    return ordered


def filter_mandarin_library(query: str, limit: int = 400) -> List[str]:
    """Filter the GB2312 library by substring or single-character match."""
    library = mandarin_character_library()
    query = (query or "").strip()
    if not query:
        return list(library[:limit])
    if len(query) == 1 and query in library:
        return [query]
    matches = [char for char in library if query in char]
    return matches[:limit]
