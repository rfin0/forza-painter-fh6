from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from text_fonts import (
    SCRIPT_CHINESE,
    SCRIPT_UNIVERSAL,
    TEXT_SCRIPT_IDS,
    _name_looks_latin,
    missing_glyphs,
    rank_fonts_for_text,
    recommend_font_for_text,
    recommend_font_label_for_text,
    validate_text_coverage,
)


def test_name_looks_latin_rejects_icon_fonts() -> None:
    assert not _name_looks_latin("SegoeIcons (TrueType)")
    assert not _name_looks_latin("Segoe MDL2 Assets")
    assert not _name_looks_latin("Webdings")


def test_name_looks_latin_accepts_text_faces() -> None:
    assert _name_looks_latin("Segoe UI (TrueType)")
    assert _name_looks_latin("Arial (TrueType)")
    assert _name_looks_latin("Calibri")


def test_missing_glyphs_checks_latin_characters() -> None:
    fake_path = Path("C:/Windows/Fonts/example.ttf")

    def fake_has_glyph(_path: Path, char: str, size: int = 48) -> bool:
        return char.lower() != "x"

    with patch("text_fonts.font_has_glyph", side_effect=fake_has_glyph):
        missing = missing_glyphs("Phoenix", fake_path)

    assert missing == ["x"]


def test_validate_text_coverage_reports_latin_gaps() -> None:
    fake_path = Path("C:/Windows/Fonts/example.ttf")

    with patch("text_fonts.font_has_glyph", return_value=False):
        ok, missing = validate_text_coverage("Phoenix", fake_path)

    assert not ok
    assert "P" in missing


def test_recommend_font_label_for_text_prefers_covering_font(monkeypatch) -> None:
    from text_fonts import DiscoveredFont

    good = DiscoveredFont("Arial", Path("C:/Windows/Fonts/arial.ttf"), ("latin",), 100)
    bad = DiscoveredFont("Bad Font", Path("C:/Windows/Fonts/bad.ttf"), ("latin",), 50)

    monkeypatch.setattr(
        "text_fonts.rank_fonts_for_text",
        lambda text, script=None, limit=12, fonts=None: [(good, 7, 7), (bad, 3, 7)],
    )

    assert recommend_font_label_for_text("Phoenix", script=SCRIPT_UNIVERSAL) == good.label


def test_rank_fonts_for_text_orders_by_coverage(monkeypatch) -> None:
    from text_fonts import DiscoveredFont

    good = DiscoveredFont("Good", Path("C:/Windows/Fonts/good.ttf"), ("latin",), 100)
    partial = DiscoveredFont("Partial", Path("C:/Windows/Fonts/partial.ttf"), ("latin",), 90)

    def fake_fonts(_text: str, _script: str | None):
        return (partial, good)

    def fake_missing(text: str, path: Path):
        if path == good.path:
            return []
        return ["x"]

    monkeypatch.setattr("text_fonts._fonts_for_recommendation", fake_fonts)
    monkeypatch.setattr("text_fonts.missing_glyphs", fake_missing)

    ranked = rank_fonts_for_text("Phoenix", script=SCRIPT_UNIVERSAL)
    assert ranked[0][0] is good
    assert ranked[0][1] == ranked[0][2]


def test_recommend_font_for_text_returns_best(monkeypatch) -> None:
    from text_fonts import DiscoveredFont

    good = DiscoveredFont("Good", Path("C:/Windows/Fonts/good.ttf"), ("latin",), 100)

    monkeypatch.setattr(
        "text_fonts.rank_fonts_for_text",
        lambda text, script=None, limit=12, fonts=None: [(good, 7, 7)],
    )
    rec = recommend_font_for_text("Phoenix", script=SCRIPT_UNIVERSAL)
    assert rec.complete
    assert rec.label == good.label


def test_text_script_ids_exclude_kaomoji() -> None:
    from text_fonts import SCRIPT_JAPANESE, SCRIPT_KOREAN

    assert "kaomoji" not in TEXT_SCRIPT_IDS
    assert TEXT_SCRIPT_IDS == (SCRIPT_UNIVERSAL, SCRIPT_JAPANESE, SCRIPT_KOREAN, SCRIPT_CHINESE)


def test_rank_fonts_uses_provided_font_list(monkeypatch) -> None:
    from text_fonts import DiscoveredFont

    good = DiscoveredFont("Good", Path("C:/Windows/Fonts/good.ttf"), ("latin",), 100)

    monkeypatch.setattr("text_fonts.missing_glyphs", lambda _text, _path: [])

    ranked = rank_fonts_for_text("Hi", script=SCRIPT_UNIVERSAL, fonts=(good,))
    assert ranked[0][0] is good


def test_default_fonts_for_script_returns_entries() -> None:
    from text_fonts import default_fonts_for_script

    fonts = default_fonts_for_script(SCRIPT_UNIVERSAL)
    assert isinstance(fonts, tuple)
    if Path(r"C:\Windows\Fonts\arial.ttf").exists():
        assert fonts
        assert all(font.path.suffix.lower() in {".ttf", ".ttc", ".otf"} for font in fonts)


def test_open_system_font_settings_uses_windows_settings_uri() -> None:
    from text_fonts import WINDOWS_FONT_SETTINGS_URI, open_system_font_settings

    with patch("text_fonts.os.name", "nt"), patch("text_fonts.os.startfile") as startfile:
        open_system_font_settings()
    startfile.assert_called_once_with(WINDOWS_FONT_SETTINGS_URI)


def test_open_system_font_settings_falls_back_to_fonts_folder() -> None:
    from text_fonts import _fonts_directory, open_system_font_settings

    with patch("text_fonts.os.name", "nt"), patch(
        "text_fonts.os.startfile",
        side_effect=[OSError("blocked"), None],
    ) as startfile:
        open_system_font_settings()
    assert startfile.call_args_list[0][0][0] == "ms-settings:fonts"
    assert startfile.call_args_list[1][0][0] == _fonts_directory()
