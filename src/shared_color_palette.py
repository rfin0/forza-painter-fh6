"""Shared Bang/Forza color palette persisted across Tools and Create tabs."""

from __future__ import annotations

from typing import Any, Callable

from ui_preferences import load_ui_preferences, save_ui_preferences

MAX_SAVED_COLORS = 16

ColorListener = Callable[[tuple[int, int, int, int], str], None]


def _clamp_channel(value: int | str) -> int:
    return max(0, min(255, int(value)))


def _normalize_entry(entry: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(entry, dict):
        return None
    try:
        return (
            _clamp_channel(entry["r"]),
            _clamp_channel(entry["g"]),
            _clamp_channel(entry["b"]),
            _clamp_channel(entry.get("a", 255)),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _serialize_rgba(rgba: tuple[int, int, int, int]) -> dict[str, int]:
    r, g, b, a = rgba
    return {"r": r, "g": g, "b": b, "a": a}


def load_saved_colors() -> list[tuple[int, int, int, int]]:
    prefs = load_ui_preferences()
    raw = prefs.get("saved_colors")
    if not isinstance(raw, list):
        return []
    colors: list[tuple[int, int, int, int]] = []
    seen: set[tuple[int, int, int, int]] = set()
    for item in raw:
        rgba = _normalize_entry(item)
        if rgba is None or rgba in seen:
            continue
        seen.add(rgba)
        colors.append(rgba)
        if len(colors) >= MAX_SAVED_COLORS:
            break
    return colors


def get_last_color() -> tuple[int, int, int, int] | None:
    prefs = load_ui_preferences()
    rgba = _normalize_entry(prefs.get("last_color"))
    if rgba is not None:
        return rgba
    colors = load_saved_colors()
    return colors[0] if colors else None


def save_palette(colors: list[tuple[int, int, int, int]], *, last: tuple[int, int, int, int] | None) -> None:
    prefs = load_ui_preferences()
    trimmed = colors[:MAX_SAVED_COLORS]
    prefs["saved_colors"] = [_serialize_rgba(item) for item in trimmed]
    if last is not None:
        prefs["last_color"] = _serialize_rgba(last)
    save_ui_preferences(prefs)


class SharedColorPalette:
    """In-memory palette with disk persistence and cross-panel listeners."""

    def __init__(self) -> None:
        self._colors = load_saved_colors()
        self._listeners: list[ColorListener] = []

    def subscribe(self, callback: ColorListener) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unsubscribe(self, callback: ColorListener) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def saved_colors(self) -> list[tuple[int, int, int, int]]:
        return list(self._colors)

    def push(
        self,
        r: int,
        g: int,
        b: int,
        a: int = 255,
        *,
        notify: bool = True,
        persist: bool = True,
        source: str = "push",
    ) -> tuple[int, int, int, int]:
        rgba = (
            _clamp_channel(r),
            _clamp_channel(g),
            _clamp_channel(b),
            _clamp_channel(a),
        )
        self._colors = [item for item in self._colors if item != rgba]
        self._colors.insert(0, rgba)
        self._colors = self._colors[:MAX_SAVED_COLORS]
        if persist:
            save_palette(self._colors, last=rgba)
        if notify:
            self._notify(rgba, source)
        return rgba

    def recall(self, rgba: tuple[int, int, int, int], *, notify: bool = True) -> None:
        self.push(*rgba, notify=notify, source="recall")

    def _notify(self, rgba: tuple[int, int, int, int], source: str) -> None:
        for callback in list(self._listeners):
            try:
                callback(rgba, source)
            except Exception:
                pass
