"""
Discover CJK-capable fonts on the local machine and validate glyph coverage.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from mandarin_chars import is_hangul_char, text_contains_hangul, text_scripts, unique_chars

_FONT_EXTS = {".ttf", ".ttc", ".otf", ".fon"}
_PROBE_SIZE = 48
_PROBE_CHARS = "中文测试ソニック가"

_SC_HINTS = (
    "yahei",
    "simhei",
    "simsun",
    "simkai",
    "dengxian",
    "noto sans sc",
    "noto sans cjk sc",
    "source han sans sc",
    "source han sans cn",
    "pingfang sc",
    "stkaiti",
    "fangsong",
)
_TC_HINTS = (
    "mingliu",
    "pmingliu",
    "microsoft jhenghei",
    "kaiti tc",
    "noto sans tc",
    "noto sans cjk tc",
    "pingfang tc",
)
_JP_HINTS = ("meiryo", "yu goth", "msgothic", "ms gothic", "ms mincho", "noto sans jp", "noto sans cjk jp")
_KR_HINTS = ("malgun", "gulim", "dotum", "batang", "noto sans kr", "noto sans cjk kr")
_CJK_HINTS = _SC_HINTS + _TC_HINTS + _JP_HINTS + _KR_HINTS

SCRIPT_UNIVERSAL = "universal"
SCRIPT_JAPANESE = "japanese"
SCRIPT_KOREAN = "korean"
SCRIPT_CHINESE = "chinese"
TEXT_SCRIPT_IDS = (SCRIPT_UNIVERSAL, SCRIPT_JAPANESE, SCRIPT_KOREAN, SCRIPT_CHINESE)

_LATIN_HINTS = (
    "segoe",
    "arial",
    "calibri",
    "cambria",
    "times new",
    "verdana",
    "tahoma",
    "helvetica",
    "roboto",
    "noto sans",
    "georgia",
    "trebuchet",
    "consolas",
    "franklin",
    "garamond",
    "constantia",
    "corbel",
    "bahnschrift",
    "lucida",
    "century gothic",
    "book antiqua",
    "palatino",
    "courier new",
    "comic sans",
    "impact",
    "gabriola",
)
_LATIN_PROBE = "ABCabcPhoenix0123456789"
_SYMBOL_FONT_HINTS = (
    "icons",
    "icon ",
    " icon",
    "mdl2",
    "webdings",
    "wingdings",
    "wingding",
    "marlett",
    "symbol",
    "seguiemj",
    "emoji",
    "holomdl2",
    "monotype sorts",
    "extra symbols",
    "math",
    "arrow",
    "gadugi",
    "ebrima",
    "sylfaen",
    "ms outlook",
    "mt extra",
)
_LATIN_FALLBACKS = [
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path(r"C:\Windows\Fonts\calibri.ttf"),
    Path(r"C:\Windows\Fonts\tahoma.ttf"),
    Path(r"C:\Windows\Fonts\verdana.ttf"),
    Path(r"C:\Windows\Fonts\times.ttf"),
    Path(r"C:\Windows\Fonts\consola.ttf"),
    Path(r"C:\Windows\Fonts\cour.ttf"),
    Path(r"C:\Windows\Fonts\seguisym.ttf"),
]
_CJK_NAME_RE = re.compile(
    r"sim|hei|song|kai|fang|yuan|ming|gothic|mincho|meiryo|malgun|gulim|batang|dotum|"
    r"noto|source han|pingfang|hiragino|cjk|\bhan\b|han-|dengxian|fangsong|stkaiti",
    re.IGNORECASE,
)

_LEGACY_FALLBACKS = [
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\msyhbd.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
    Path(r"C:\Windows\Fonts\simsun.ttc"),
    Path(r"C:\Windows\Fonts\NotoSansSC-VF.ttf"),
    Path(r"C:\Windows\Fonts\NotoSansCJKsc-Regular.otf"),
    Path(r"C:\Windows\Fonts\malgun.ttf"),
    Path(r"C:\Windows\Fonts\malgunbd.ttf"),
    Path(r"C:\Windows\Fonts\NotoSansKR-VF.ttf"),
    Path(r"C:\Windows\Fonts\NotoSansCJKkr-Regular.otf"),
    Path(r"C:\Windows\Fonts\meiryo.ttc"),
    Path(r"C:\Windows\Fonts\YuGothM.ttc"),
    Path(r"/System/Library/Fonts/PingFang.ttc"),
    Path(r"/System/Library/Fonts/STHeiti Light.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
]


@dataclass(frozen=True)
class DiscoveredFont:
    display_name: str
    path: Path
    script_tags: Tuple[str, ...]
    score: int

    @property
    def label(self) -> str:
        tag_labels = {
            "latin": "LATIN",
            "symbol": "SYMBOL",
            "sc": "SC",
            "tc": "TC",
            "jp": "JP",
            "kr": "KR",
            "cjk": "CJK",
        }
        if self.script_tags:
            tags = "/".join(tag_labels.get(tag, tag.upper()) for tag in self.script_tags)
        else:
            tags = "CJK"
        return f"{self.display_name} [{tags}]"


_font_file_entries_cache: Dict[str, Path] | None = None
_discover_cache: dict[tuple[str, bool], tuple[DiscoveredFont, ...]] = {}


def clear_font_discovery_cache() -> None:
    global _font_file_entries_cache
    _font_file_entries_cache = None
    _discover_cache.clear()


def _fonts_directory() -> Path:
    return Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"


WINDOWS_FONT_SETTINGS_URI = "ms-settings:fonts"


def open_system_font_settings() -> None:
    """Open Windows Settings > Personalization > Fonts (not the legacy Fonts folder)."""
    if os.name != "nt":
        raise OSError("Font settings are only available on Windows.")
    try:
        os.startfile(WINDOWS_FONT_SETTINGS_URI)  # type: ignore[attr-defined]
    except OSError:
        # Older builds or policy blocks may reject the settings URI; fall back to the folder.
        os.startfile(_fonts_directory())  # type: ignore[attr-defined]


def _name_looks_cjk(name: str) -> bool:
    return bool(_CJK_NAME_RE.search(name))


def _name_is_symbol_font(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in _SYMBOL_FONT_HINTS)


def _name_looks_latin(name: str) -> bool:
    lowered = name.lower()
    if _name_is_symbol_font(lowered):
        return False
    if any(hint in lowered for hint in _LATIN_HINTS):
        if "segoe" in lowered and "segoe ui" not in lowered:
            return False
        return True
    return False


def _name_latin_tags(name: str) -> Tuple[str, ...]:
    return ("latin",) if _name_looks_latin(name) else ()


def _score_latin_font(name: str) -> int:
    lowered = name.lower()
    if _name_is_symbol_font(lowered):
        return -1000
    score = 0
    if "segoe ui" in lowered:
        score += 120
    if "arial" in lowered:
        score += 110
    if "calibri" in lowered:
        score += 100
    if "tahoma" in lowered or "verdana" in lowered:
        score += 90
    if "times new roman" in lowered:
        score += 85
    if "consolas" in lowered:
        score += 70
    if "noto sans" in lowered and "cjk" not in lowered and "sc" not in lowered:
        score += 65
    if lowered.endswith("(truetype)"):
        score -= 5
    return score


@lru_cache(maxsize=512)
def _latin_probe_cached(path_str: str, mtime_ns: int) -> bool:
    path = Path(path_str)
    if not path.exists():
        return False
    return all(font_has_glyph(path, char) for char in _LATIN_PROBE)


def font_supports_latin(font_path: Path) -> bool:
    path = Path(font_path)
    if not path.exists():
        return False
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return _latin_probe_cached(str(path.resolve()), 0)
    return _latin_probe_cached(str(path.resolve()), mtime_ns)


def _name_tags(name: str) -> Tuple[str, ...]:
    lowered = name.lower()
    tags: List[str] = []
    if any(hint in lowered for hint in _SC_HINTS):
        tags.append("sc")
    if any(hint in lowered for hint in _TC_HINTS):
        tags.append("tc")
    if any(hint in lowered for hint in _JP_HINTS):
        tags.append("jp")
    if any(hint in lowered for hint in _KR_HINTS):
        tags.append("kr")
    if not tags and any(hint in lowered for hint in ("cjk", "han", "pingfang", "source han")):
        tags.append("cjk")
    return tuple(tags)


def _score_font(name: str, tags: Tuple[str, ...]) -> int:
    lowered = name.lower()
    score = 0
    if "sc" in tags:
        score += 120
    if "tc" in tags:
        score += 80
    if "jp" in tags:
        score += 60
    if "kr" in tags:
        score += 40
    if "cjk" in tags:
        score += 50
    if "yahei" in lowered or "microsoft yahei" in lowered:
        score += 40
    if "simhei" in lowered:
        score += 35
    if "noto sans sc" in lowered or "noto sans cjk sc" in lowered:
        score += 30
    if "simsun" in lowered:
        score += 20
    if lowered.endswith("(truetype)"):
        score -= 5
    return score


def _registry_font_entries() -> Dict[str, Path]:
    global _font_file_entries_cache
    if _font_file_entries_cache is not None:
        return dict(_font_file_entries_cache)

    entries: Dict[str, Path] = {}
    try:
        import winreg
    except ImportError:
        return entries

    fonts_dir = _fonts_directory()
    try:
        try:
            from defender_audit import log_registry_read

            log_registry_read(
                r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
                purpose="font enumeration",
            )
        except Exception:
            pass
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
        ) as key:
            index = 0
            while True:
                try:
                    display_name, value, _ = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                path = Path(str(value))
                if not path.is_absolute():
                    path = fonts_dir / path
                if path.suffix.lower() not in _FONT_EXTS:
                    continue
                if path.exists():
                    entries[display_name] = path.resolve()
    except OSError:
        pass
    _font_file_entries_cache = dict(entries)
    return entries


def _glob_font_files() -> Dict[str, Path]:
    return _registry_font_entries()


def _all_font_entries() -> Dict[str, Path]:
    fonts_dir = _fonts_directory()
    registry = _registry_font_entries()
    if not fonts_dir.exists():
        return registry
    found: Dict[str, Path] = dict(registry)
    for path in fonts_dir.iterdir():
        if path.suffix.lower() not in _FONT_EXTS:
            continue
        if path.is_file():
            found.setdefault(path.stem, path.resolve())
    return found


def discover_cjk_fonts(deep_scan: bool = False) -> Tuple[DiscoveredFont, ...]:
    """Return installed fonts likely to support CJK, best matches first."""
    by_path: Dict[Path, DiscoveredFont] = {}
    entries = _all_font_entries()
    for display_name, path in entries.items():
        path = path.resolve()
        if path.suffix.lower() not in _FONT_EXTS:
            continue
        tags = _name_tags(display_name)
        if not tags and not _name_looks_cjk(display_name):
            if path.stem.lower() not in {p.stem.lower() for p in _LEGACY_FALLBACKS}:
                continue
            tags = ("cjk",)
        score = _score_font(display_name, tags)
        existing = by_path.get(path)
        if existing is None or score > existing.score:
            by_path[path] = DiscoveredFont(
                display_name=display_name.replace("(TrueType)", "").strip(),
                path=path,
                script_tags=tags,
                score=score,
            )

    for fallback in _LEGACY_FALLBACKS:
        if not fallback.exists():
            continue
        path = fallback.resolve()
        if path in by_path:
            continue
        name = path.stem
        tags = _name_tags(name)
        by_path[path] = DiscoveredFont(
            display_name=name,
            path=path,
            script_tags=tags or ("cjk",),
            score=_score_font(name, tags or ("cjk",)),
        )

    if deep_scan:
        for display_name, path in entries.items():
            path = Path(path).resolve()
            if path in by_path or path.suffix.lower() not in _FONT_EXTS:
                continue
            tags_probe = _name_tags(display_name) or ("cjk",)
            require_hangul = "kr" in tags_probe
            if not path.exists() or not font_supports_sample(path, require_hangul=require_hangul):
                continue
            tags = _name_tags(display_name) or ("cjk",)
            by_path[path] = DiscoveredFont(
                display_name=display_name.replace("(TrueType)", "").strip(),
                path=path,
                script_tags=tags,
                score=_score_font(display_name, tags) + 5,
            )

    return tuple(sorted(by_path.values(), key=lambda item: (-item.score, item.display_name.lower())))


def discover_latin_fonts(deep_scan: bool = False) -> Tuple[DiscoveredFont, ...]:
    """Return installed fonts suitable for Latin / universal text."""
    by_path: Dict[Path, DiscoveredFont] = {}
    entries = _all_font_entries()
    for display_name, path in entries.items():
        path = Path(path).resolve()
        if path.suffix.lower() not in _FONT_EXTS:
            continue
        if not _name_looks_latin(display_name) and path.stem.lower() not in {p.stem.lower() for p in _LATIN_FALLBACKS}:
            continue
        if _name_looks_cjk(display_name) and not _name_looks_latin(display_name):
            continue
        if not font_supports_latin(path):
            continue
        score = _score_latin_font(display_name)
        existing = by_path.get(path)
        if existing is None or score > existing.score:
            by_path[path] = DiscoveredFont(
                display_name=display_name.replace("(TrueType)", "").strip(),
                path=path,
                script_tags=("latin",),
                score=score,
            )

    for fallback in _LATIN_FALLBACKS:
        if not fallback.exists():
            continue
        path = fallback.resolve()
        if path in by_path:
            continue
        if not font_supports_latin(path):
            continue
        name = path.stem
        by_path[path] = DiscoveredFont(
            display_name=name,
            path=path,
            script_tags=("latin",),
            score=_score_latin_font(name),
        )

    if deep_scan:
        for display_name, path in entries.items():
            path = Path(path).resolve()
            if path in by_path or path.suffix.lower() not in _FONT_EXTS or not path.exists():
                continue
            if _name_looks_cjk(display_name) and not _name_looks_latin(display_name):
                continue
            if not font_supports_latin(path):
                continue
            by_path[path] = DiscoveredFont(
                display_name=display_name.replace("(TrueType)", "").strip(),
                path=path,
                script_tags=("latin",),
                score=_score_latin_font(display_name) + 5,
            )

    return tuple(sorted(by_path.values(), key=lambda item: (-item.score, item.display_name.lower())))


def font_matches_script(font: DiscoveredFont, script: str) -> bool:
    tags = font.script_tags
    if script == SCRIPT_UNIVERSAL:
        return "latin" in tags
    if script == SCRIPT_JAPANESE:
        return "jp" in tags or "cjk" in tags
    if script == SCRIPT_KOREAN:
        return "kr" in tags
    if script == SCRIPT_CHINESE:
        return "sc" in tags or "tc" in tags or "cjk" in tags
    return True


def filter_fonts_for_script(fonts: Sequence[DiscoveredFont], script: str) -> Tuple[DiscoveredFont, ...]:
    return tuple(font for font in fonts if font_matches_script(font, script))


def filter_font_labels(
    fonts: Sequence[DiscoveredFont],
    search_query: str = "",
) -> Tuple[DiscoveredFont, ...]:
    query = (search_query or "").strip().lower()
    if not query:
        return tuple(fonts)
    tokens = [part for part in re.split(r"\s+", query) if part]
    matched: List[DiscoveredFont] = []
    for font in fonts:
        haystack = f"{font.display_name} {font.label}".lower()
        if all(token in haystack for token in tokens):
            matched.append(font)
    return tuple(matched)


def discover_fonts_for_script(script: str, deep_scan: bool = False) -> Tuple[DiscoveredFont, ...]:
    if script == SCRIPT_UNIVERSAL:
        return discover_latin_fonts(deep_scan=deep_scan)
    return filter_fonts_for_script(discover_cjk_fonts(deep_scan=deep_scan), script)


def discover_fonts_for_script_cached(script: str, deep_scan: bool = False) -> Tuple[DiscoveredFont, ...]:
    key = (script, bool(deep_scan))
    cached = _discover_cache.get(key)
    if cached is not None:
        return cached
    fonts = discover_fonts_for_script(script, deep_scan=deep_scan)
    _discover_cache[key] = fonts
    return fonts


def _discovered_font_from_path(path: Path, *, script_tags: Tuple[str, ...], display_name: str | None = None) -> DiscoveredFont:
    path = path.resolve()
    name = (display_name or path.stem).replace("(TrueType)", "").strip()
    tags = script_tags or _name_tags(name) or ("cjk",)
    if "latin" in tags:
        score = _score_latin_font(name)
    else:
        score = _score_font(name, tags)
    return DiscoveredFont(display_name=name, path=path, script_tags=tags, score=score)


def default_font_path_for_script(script: str) -> Path | None:
    """Preferred default font path for a script tab, when installed."""
    return None


def default_fonts_for_script(script: str) -> Tuple[DiscoveredFont, ...]:
    """Fast tier-1 fonts (known paths) without scanning the full machine."""
    by_path: Dict[Path, DiscoveredFont] = {}

    def add(path: Path, tags: Tuple[str, ...], display_name: str | None = None) -> None:
        if not path.exists():
            return
        resolved = path.resolve()
        font = _discovered_font_from_path(resolved, script_tags=tags, display_name=display_name)
        existing = by_path.get(resolved)
        if existing is None or font.score > existing.score:
            by_path[resolved] = font

    if script == SCRIPT_UNIVERSAL:
        for path in _LATIN_FALLBACKS:
            add(path, ("latin",))
    elif script == SCRIPT_KOREAN:
        for path in (
            Path(r"C:\Windows\Fonts\malgun.ttf"),
            Path(r"C:\Windows\Fonts\malgunbd.ttf"),
            Path(r"C:\Windows\Fonts\NotoSansKR-VF.ttf"),
        ):
            add(path, ("kr",))
    elif script == SCRIPT_JAPANESE:
        for path in (
            Path(r"C:\Windows\Fonts\meiryo.ttc"),
            Path(r"C:\Windows\Fonts\YuGothM.ttc"),
            Path(r"C:\Windows\Fonts\msgothic.ttc"),
        ):
            add(path, ("jp",))
    elif script == SCRIPT_CHINESE:
        for path in (
            Path(r"C:\Windows\Fonts\msyh.ttc"),
            Path(r"C:\Windows\Fonts\msyhbd.ttc"),
            Path(r"C:\Windows\Fonts\simhei.ttf"),
            Path(r"C:\Windows\Fonts\simsun.ttc"),
            Path(r"C:\Windows\Fonts\NotoSansSC-VF.ttf"),
            Path(r"C:\Windows\Fonts\NotoSansCJKsc-Regular.otf"),
        ):
            tags = _name_tags(path.stem) or ("sc",)
            add(path, tags)

    return tuple(sorted(by_path.values(), key=lambda item: (-item.score, item.display_name.lower())))


def _font_covers_text(font: DiscoveredFont, text: str) -> bool:
    if not text.strip():
        return True
    missing = missing_glyphs(text, font.path)
    return not missing


def _score_font_for_text(font: DiscoveredFont, text: str) -> int:
    score = font.score
    scripts = text_scripts(text)
    if "kr" in scripts:
        if "kr" in font.script_tags:
            score += 200
        elif "cjk" in font.script_tags:
            score += 30
        else:
            score -= 80
    if "jp" in scripts and "jp" in font.script_tags:
        score += 80
    if "sc" in scripts and "sc" in font.script_tags:
        score += 40
    if text.strip() and _font_covers_text(font, text):
        score += 100
    return score


def find_font_for_text(
    text: str = "",
    preferred: Path | None = None,
    script: str | None = None,
) -> Path:
    """Pick a font that matches the scripts in *text* (Hangul → Korean faces first)."""
    if preferred is not None:
        path = Path(preferred)
        if path.exists():
            return path.resolve()
        raise FileNotFoundError(f"Font not found: {path}")

    if script:
        fonts = discover_fonts_for_script(script)
    else:
        fonts = discover_cjk_fonts()
    if text.strip() and fonts:
        recommendation = recommend_font_for_text(text, script=script)
        if recommendation.font is not None:
            return recommendation.font.path
        ranked = sorted(fonts, key=lambda item: (-_score_font_for_text(item, text), item.display_name.lower()))
        return ranked[0].path

    return find_cjk_font()


def find_cjk_font(preferred: Path | None = None) -> Path:
    """Resolve the best font path for Mandarin-first text rendering."""
    return find_font_for_text("", preferred=preferred)


def resolve_font_path(selection: str | None = None, browse_path: Path | None = None) -> Path:
    if browse_path is not None:
        path = Path(browse_path)
        if path.exists():
            return path.resolve()
        raise FileNotFoundError(f"Font not found: {path}")

    selection = (selection or "").strip()
    if not selection:
        return find_cjk_font()

    for font in discover_cjk_fonts():
        if font.label == selection or font.display_name == selection:
            return font.path

    path = Path(selection)
    if path.exists():
        return path.resolve()

    return find_cjk_font()


def _load_truetype(path: Path, size: int, bold: bool = False):
    from PIL import ImageFont

    path = Path(path)
    if path.suffix.lower() == ".ttc" and bold:
        for index in (1, 0):
            try:
                return ImageFont.truetype(str(path), size, index=index)
            except OSError:
                continue
    return ImageFont.truetype(str(path), size)


@lru_cache(maxsize=256)
def _notdef_fingerprint(path_str: str, mtime_ns: int, size: int) -> tuple[int, int, bytes] | None:
    path = Path(path_str)
    if not path.exists():
        return None
    try:
        font = _load_truetype(path, size)
    except OSError:
        return None
    for probe in ("\uFFFF", "\uFFFE", "\uFFF0"):
        try:
            mask = font.getmask(probe)
            if mask.size[0] > 0 and mask.size[1] > 0:
                payload = mask.tobytes() if hasattr(mask, "tobytes") else bytes(mask)
                return (mask.size[0], mask.size[1], payload)
        except Exception:
            continue
    return None


def _mask_fingerprint(font, char: str) -> tuple[int, int, bytes] | None:
    try:
        mask = font.getmask(char)
    except Exception:
        return None
    if mask.size[0] <= 0 or mask.size[1] <= 0:
        return None
    payload = mask.tobytes() if hasattr(mask, "tobytes") else bytes(mask)
    return (mask.size[0], mask.size[1], payload)


def font_has_glyph(font_path: Path, char: str, size: int = _PROBE_SIZE) -> bool:
    if len(char) != 1:
        return False
    path = Path(font_path)
    if not path.exists():
        return False
    try:
        font = _load_truetype(path, size)
    except OSError:
        return False

    if hasattr(font, "has_glyph"):
        try:
            if not bool(font.has_glyph(char)):
                return False
        except Exception:
            pass

    fingerprint = _mask_fingerprint(font, char)
    if fingerprint is None:
        return False

    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        mtime_ns = 0
    notdef = _notdef_fingerprint(str(path.resolve()), mtime_ns, size)
    if notdef is not None and fingerprint == notdef:
        return False

    width, height = fingerprint[0], fingerprint[1]
    return width > 1 and height > 1


def font_supports_sample(font_path: Path, require_hangul: bool = False) -> bool:
    path = Path(font_path)
    if not path.exists():
        return False
    hits = sum(1 for char in _PROBE_CHARS if font_has_glyph(path, char))
    if hits < 2:
        return False
    if require_hangul:
        return font_has_glyph(path, "가") and font_has_glyph(path, "한")
    return True


def missing_glyphs(text: str, font_path: Path) -> List[str]:
    missing: List[str] = []
    for char in unique_chars(text):
        if char.isspace():
            continue
        if not font_has_glyph(font_path, char):
            missing.append(char)
    return missing


def validate_text_coverage(text: str, font_path: Path) -> Tuple[bool, List[str]]:
    missing = missing_glyphs(text, font_path)
    return (not missing, missing)


def coverage_message_key(text: str, ok: bool, missing: Sequence[str]) -> str:
    if ok:
        if text_contains_hangul(text):
            return "text_coverage_ok_korean"
        return "text_coverage_ok"
    if text_contains_hangul(text):
        return "text_coverage_missing_korean"
    return "text_coverage_missing"


def _count_text_chars(text: str) -> int:
    return sum(1 for char in unique_chars(text) if not char.isspace())


def _fonts_for_recommendation(
    text: str,
    script: str | None,
    *,
    fonts: Sequence[DiscoveredFont] | None = None,
) -> Tuple[DiscoveredFont, ...]:
    if fonts:
        return tuple(fonts)
    target = script or SCRIPT_UNIVERSAL
    return discover_fonts_for_script_cached(target, deep_scan=True)


@dataclass(frozen=True)
class FontRecommendation:
    font: DiscoveredFont | None
    covered: int
    total: int

    @property
    def complete(self) -> bool:
        return self.font is not None and self.total > 0 and self.covered >= self.total

    @property
    def label(self) -> str | None:
        return self.font.label if self.font else None


def rank_fonts_for_text(
    text: str,
    script: str | None = None,
    *,
    limit: int = 12,
    fonts: Sequence[DiscoveredFont] | None = None,
) -> List[Tuple[DiscoveredFont, int, int]]:
    """Return fonts sorted by glyph coverage (best first)."""
    if not text.strip():
        return []
    total = _count_text_chars(text)
    if total <= 0:
        return []
    ranked: List[Tuple[DiscoveredFont, int, int]] = []
    candidates = tuple(fonts) if fonts is not None else _fonts_for_recommendation(text, script)
    for font in candidates:
        missing = missing_glyphs(text, font.path)
        covered = max(0, total - len(missing))
        ranked.append((font, covered, total))
    ranked.sort(key=lambda item: (-item[1], -item[0].score, item[0].display_name.lower()))
    return ranked[:limit]


def recommend_font_for_text(
    text: str,
    script: str | None = None,
    *,
    fonts: Sequence[DiscoveredFont] | None = None,
) -> FontRecommendation:
    total = _count_text_chars(text)
    if not text.strip() or total <= 0:
        return FontRecommendation(font=None, covered=0, total=0)
    ranked = rank_fonts_for_text(text, script, limit=1, fonts=fonts)
    if not ranked:
        return FontRecommendation(font=None, covered=0, total=total)
    font, covered, total = ranked[0]
    return FontRecommendation(font=font, covered=covered, total=total)


def recommend_font_label_for_text(
    text: str,
    script: str | None = None,
    *,
    fonts: Sequence[DiscoveredFont] | None = None,
) -> str | None:
    return recommend_font_for_text(text, script=script, fonts=fonts).label


def format_missing_chars(chars: Sequence[str], limit: int = 12) -> str:
    if not chars:
        return ""
    shown = "".join(chars[:limit])
    if len(chars) > limit:
        shown += f" (+{len(chars) - limit} more)"
    return shown
