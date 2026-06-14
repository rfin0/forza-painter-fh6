"""Load FH6 vinyl shape type codes from the bundled shape library CSV."""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Literal

from app_paths import RESOURCE_ROOT, ROOT

PreviewStyle = Literal["square", "circle", "ellipse", "triangle", "ring", "rect"]

TYPECODE_BASE = 0x100000
SHAPE_LIBRARY_DIRNAME = "shape library"
DEFAULT_CSV_FILENAME = "FH6 Shape Library Data - FH6 Shape Library Data.csv"
_ENV_CATALOG_PATH = "FORZA_PAINTER_SHAPE_CATALOG_CSV"

_LEGACY_FALLBACK_TYPE_CODES = frozenset(
    {
        1048677,  # Square (pixel art default)
        1048678,  # Hexagon (legacy whitelist mislabeled as Circle)
        1048679,  # Half Circle (legacy whitelist mislabeled as Triangle)
        1048688,  # Octagon (legacy whitelist mislabeled as Circle Border)
        1048712,  # Jellybean (legacy whitelist mislabeled as Ellipse)
    }
)


@dataclass(frozen=True)
class ShapeCatalogEntry:
    section: str
    tab_order: int
    family: str
    slot: int
    shape_name: str
    type_code: int
    shape_word: int
    page_byte: int
    low_byte: int
    confidence: str
    glyph: str = ""
    glyph_block: str = ""
    resource_path: str = ""


@dataclass(frozen=True)
class ShapeCatalog:
    path: Path
    entries_by_code: dict[int, ShapeCatalogEntry]
    entries_by_family_name: dict[tuple[str, str], ShapeCatalogEntry]
    known_type_codes: frozenset[int]
    duplicate_type_codes: tuple[int, ...]
    row_count: int

    def is_known(self, code: int) -> bool:
        return int(code) in self.known_type_codes

    def get(self, code: int) -> ShapeCatalogEntry | None:
        return self.entries_by_code.get(int(code))

    def get_by_family_name(self, family: str, shape_name: str) -> ShapeCatalogEntry | None:
        key = (str(family).strip(), str(shape_name).strip())
        return self.entries_by_family_name.get(key)

    def type_code_for(self, family: str, shape_name: str) -> int | None:
        entry = self.get_by_family_name(family, shape_name)
        return entry.type_code if entry is not None else None

    def describe(self, code: int) -> str:
        entry = self.get(code)
        if entry is None:
            return f"0x{int(code):x}"
        if entry.family and entry.shape_name:
            return f"{entry.family} / {entry.shape_name}"
        return entry.shape_name or f"0x{int(code):x}"

    @staticmethod
    def encoding_matches(type_code: int, shape_word: int, *, base: int = TYPECODE_BASE) -> bool:
        return int(type_code) == int(base) + (int(shape_word) & 0xFFFF)


def _parse_int(value: str, *, field: str, row_index: int) -> int:
    text = str(value).strip()
    if not text:
        raise ValueError(f"row {row_index}: missing {field}")
    if text.lower().startswith("0x"):
        return int(text, 16)
    return int(text, 10)


def _candidate_catalog_paths() -> Iterable[Path]:
    env_path = os.environ.get(_ENV_CATALOG_PATH, "").strip()
    if env_path:
        yield Path(env_path)
    relative = Path(SHAPE_LIBRARY_DIRNAME) / DEFAULT_CSV_FILENAME
    # Prefer install-dir CSV (beside exe) so users can update the catalog without rebuilding.
    yield ROOT / relative
    if RESOURCE_ROOT != ROOT:
        yield RESOURCE_ROOT / relative
    if ROOT.parent != ROOT:
        yield ROOT.parent / relative


def catalog_csv_path() -> Path:
    for path in _candidate_catalog_paths():
        if path.is_file():
            return path.resolve()
    searched = ", ".join(str(p) for p in _candidate_catalog_paths())
    raise FileNotFoundError(
        f"FH6 shape catalog CSV not found. Set {_ENV_CATALOG_PATH} or place "
        f"{DEFAULT_CSV_FILENAME!r} under {SHAPE_LIBRARY_DIRNAME!r}. Tried: {searched}"
    )


def load_catalog(*, path: Path | None = None, force_reload: bool = False) -> ShapeCatalog:
    if force_reload:
        load_catalog_cached.cache_clear()
    return load_catalog_cached() if path is None else _load_catalog_from_path(Path(path).resolve())


@lru_cache(maxsize=1)
def load_catalog_cached() -> ShapeCatalog:
    return _load_catalog_from_path(catalog_csv_path())


_LEGACY_PREVIEW_STYLES: dict[int, PreviewStyle] = {
    1048677: "square",
    1048678: "ellipse",
    1048679: "ellipse",
    1048688: "rect",
    1048712: "ellipse",
}


def _classify_preview_style(entry: ShapeCatalogEntry) -> PreviewStyle:
    name = entry.shape_name
    lower = name.lower()
    if name == "Square":
        return "square"
    if name == "Triangle":
        return "triangle"
    if name == "Circle":
        return "circle"
    if name == "Ellipse":
        return "ellipse"
    if "circle border" in lower or "circle half border" in lower:
        return "ring"
    if "triangle" in lower:
        return "triangle"
    if "ellipse" in lower or "jellybean" in lower:
        return "ellipse"
    if "half circle" in lower or "quarter circle" in lower or "quarter donut" in lower:
        return "ellipse"
    if "circle" in lower:
        return "circle"
    return "rect"


def preview_style_for_type_code(code: int, *, allow_fallback: bool = True) -> PreviewStyle:
    try:
        entry = load_catalog().get(int(code))
    except FileNotFoundError:
        if not allow_fallback:
            raise
        entry = None
    if entry is not None:
        return _classify_preview_style(entry)
    return _LEGACY_PREVIEW_STYLES.get(int(code), "rect")


def _load_catalog_from_path(path: Path) -> ShapeCatalog:
    entries_by_code: dict[int, ShapeCatalogEntry] = {}
    entries_by_family_name: dict[tuple[str, str], ShapeCatalogEntry] = {}
    duplicate_codes: list[int] = []
    row_count = 0

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"shape catalog CSV has no header: {path}")
        for row_index, row in enumerate(reader, start=2):
            section = (row.get("section") or "").strip()
            if not section:
                continue
            type_code = _parse_int(row["fh6_full_code_decimal"], field="fh6_full_code_decimal", row_index=row_index)
            shape_word = _parse_int(row["fh6_shape_word_decimal"], field="fh6_shape_word_decimal", row_index=row_index)
            if not ShapeCatalog.encoding_matches(type_code, shape_word):
                raise ValueError(
                    f"row {row_index}: type code {type_code} does not match "
                    f"0x{TYPECODE_BASE:x} + shape word {shape_word}"
                )
            entry = ShapeCatalogEntry(
                section=section,
                tab_order=_parse_int(row.get("tab_order") or "0", field="tab_order", row_index=row_index),
                family=(row.get("family") or "").strip(),
                slot=_parse_int(row.get("slot") or "0", field="slot", row_index=row_index),
                shape_name=(row.get("shape_name") or "").strip(),
                type_code=type_code,
                shape_word=shape_word,
                page_byte=_parse_int(row.get("fh6_page_byte_decimal") or "0", field="fh6_page_byte_decimal", row_index=row_index),
                low_byte=_parse_int(row.get("fh6_low_byte_decimal") or "0", field="fh6_low_byte_decimal", row_index=row_index),
                confidence=(row.get("confidence") or "").strip(),
                glyph=(row.get("glyph") or "").strip(),
                glyph_block=(row.get("glyph_block") or "").strip(),
                resource_path=(row.get("resource_path") or "").strip(),
            )
            row_count += 1
            if type_code in entries_by_code:
                duplicate_codes.append(type_code)
                continue
            entries_by_code[type_code] = entry
            if entry.family and entry.shape_name:
                name_key = (entry.family, entry.shape_name)
                entries_by_family_name.setdefault(name_key, entry)

    known = frozenset(entries_by_code)
    return ShapeCatalog(
        path=path,
        entries_by_code=entries_by_code,
        entries_by_family_name=entries_by_family_name,
        known_type_codes=known,
        duplicate_type_codes=tuple(sorted(set(duplicate_codes))),
        row_count=row_count,
    )


def known_type_codes(*, allow_fallback: bool = True) -> frozenset[int]:
    try:
        return load_catalog().known_type_codes
    except FileNotFoundError:
        if not allow_fallback:
            raise
        return _LEGACY_FALLBACK_TYPE_CODES


def is_known_type_code(code: int, *, allow_fallback: bool = True) -> bool:
    return int(code) in known_type_codes(allow_fallback=allow_fallback)


def get_square_type_code(*, allow_fallback: bool = True) -> int:
    try:
        catalog = load_catalog()
        code = catalog.type_code_for("Primitives", "Square")
        if code is not None:
            return code
    except FileNotFoundError:
        if not allow_fallback:
            raise
    return 1048677


def get_primitive_type_code(shape_name: str, *, allow_fallback: bool = True) -> int | None:
    try:
        return load_catalog().type_code_for("Primitives", shape_name)
    except FileNotFoundError:
        if not allow_fallback:
            raise
        return None
